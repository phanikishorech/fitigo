"""Customer review eligibility and separated histories using disposable SQLite."""
from datetime import timedelta
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.access import AccessQrToken, Checkin, CustomerDailyAccess
from app.models.booking import Booking, Payment
from app.models.membership import UserMembership
from app.models.review import GymReview
from app.routers import gyms_public, customer_access
from app.services.review_service import ReviewService
from test_booking_access_qr import api as booking_api, create, qr, scan, NOW
from app.core.time import stored_instant


@pytest.fixture
def api(booking_api):
    client, headers, engine = booking_api
    client.app.include_router(gyms_public.router, prefix='/api/v1')
    client.app.include_router(customer_access.router, prefix='/api/v1')
    return client, headers, engine


def submit(api, booked, **values):
    return api[0].post(f"/api/v1/gyms/{booked['gym_id']}/reviews", headers=api[1][1],
        json={'rating': 5, 'comment': ' Great equipment and friendly staff. ', 'booking_id': booked['id'], **values})


def eligibility(api, booked):
    return api[0].get(f"/api/v1/profile/bookings/{booked['id']}/review", headers=api[1][1])


def test_rating_after_real_checkin_updates_one_review_and_public_average(api):
    booked = create(api, ['Customer'])
    assert not eligibility(api, booked).json()['can_review']
    assert submit(api, booked).status_code == 400
    assert scan(api, qr(api, booked)[0]['qr_token'])['success']
    context = eligibility(api, booked)
    assert context.status_code == 200 and context.json()['can_review']
    assert context.headers['cache-control'] == 'no-store'
    saved = submit(api, booked)
    assert saved.status_code == 200, saved.text
    assert saved.json()['comment'] == 'Great equipment and friendly staff.'
    review_id = saved.json()['id']
    updated = submit(api, booked, rating=4, comment='Updated feedback')
    assert updated.status_code == 200 and updated.json()['id'] == review_id
    assert eligibility(api, booked).json()['review']['rating'] == 4
    visits = api[0].get('/api/v1/profile/bookings?status=all&source=individual', headers=api[1][1]).json()
    assert len(visits) == 1 and visits[0]['can_review'] and visits[0]['review_rating'] == 4
    public = api[0].get('/api/v1/gyms/1/reviews').json()
    assert len(public) == 1 and public[0]['rating'] == 4
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(GymReview.id))) == 1
        assert ReviewService(db).get_gym_rating_summary(gym_id=1) == (4.0, 1)


@pytest.mark.parametrize('change', ['manual', 'pending', 'failed', 'refunded', 'cancelled', 'no_show', 'membership'])
def test_nonqualifying_visit_never_allows_review(api, change):
    booked = create(api, ['Customer'])
    if change != 'manual':
        assert scan(api, qr(api, booked)[0]['qr_token'])['success']
    with Session(api[2]) as db:
        b = db.get(Booking, booked['id'])
        p = db.scalar(select(Payment).where(Payment.booking_id == b.id))
        if change == 'manual': b.attendance_status = 'ATTENDED'
        if change in {'pending', 'failed', 'refunded'}: p.status = {'pending': 'INITIATED', 'failed': 'FAILED', 'refunded': 'REFUNDED'}[change]
        if change == 'cancelled': b.status = 'CANCELLED'
        if change == 'no_show': b.attendance_status = 'NO_SHOW'
        if change == 'membership': b.access_source = 'MEMBERSHIP_ACCESS'
        db.commit()
    assert eligibility(api, booked).json()['can_review'] is False
    assert submit(api, booked).status_code == 400
    assert api[0].post('/api/v1/gyms/1/reviews', headers=api[1][1], json={'rating': 5}).status_code == 400
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(GymReview.id))) == 0


def test_review_is_customer_owned_gym_scoped_and_validated(api):
    booked = create(api, ['Customer'])
    scan(api, qr(api, booked)[0]['qr_token'])
    assert api[0].get(f"/api/v1/profile/bookings/{booked['id']}/review", headers=api[1][4]).status_code == 404
    assert api[0].post('/api/v1/gyms/1/reviews', headers=api[1][4], json={'rating': 5, 'booking_id': booked['id']}).status_code == 400
    assert api[0].post('/api/v1/gyms/2/reviews', headers=api[1][1], json={'rating': 5, 'booking_id': booked['id']}).status_code == 400
    assert api[0].post('/api/v1/gyms/1/reviews', json={'rating': 5}).status_code == 401
    assert api[0].get('/api/v1/profile/bookings?source=individual').status_code == 401
    for rating in [0, 6, True, 3.5, '5']:
        assert submit(api, booked, rating=rating).status_code == 422
    assert submit(api, booked, comment='x' * 2001).status_code == 422
    assert submit(api, booked, user_id=4).status_code == 422


def test_customer_cannot_republish_moderated_review(api):
    booked = create(api, ['Customer'])
    scan(api, qr(api, booked)[0]['qr_token'])
    review_id = submit(api, booked).json()['id']
    with Session(api[2]) as db:
        ReviewService(db).set_review_visibility(review_id=review_id, published=False)
    changed = submit(api, booked, rating=4)
    assert changed.status_code == 200 and changed.json()['status'] == 'HIDDEN'
    assert api[0].get('/api/v1/gyms/1/reviews').json() == []
    with Session(api[2]) as db:
        assert ReviewService(db).get_gym_rating_summary(gym_id=1) == (0, 0)


def test_individual_bookings_and_membership_history_are_separate(api):
    booked = create(api, ['Customer'])
    scan(api, qr(api, booked)[0]['qr_token'])
    with Session(api[2]) as db:
        member = UserMembership(user_id=1, gym_id=1, membership_type='SINGLE_GYM', start_at=stored_instant(NOW - timedelta(days=2)), end_at=stored_instant(NOW + timedelta(days=20)), paid_amount=500)
        db.add(member); db.flush()
        membership_id = member.id
        daily = CustomerDailyAccess(user_id=1, membership_id=member.id, gym_id=1, access_type='SINGLE_GYM', access_date=NOW.date(), access_key='membership-history-fixture', status='USED')
        db.add(daily); db.flush()
        token = AccessQrToken(daily_access_id=daily.id, token_hash='history-token', expires_at=stored_instant(NOW + timedelta(hours=1)))
        db.add(token); db.flush()
        db.add(Checkin(user_id=1, gym_id=1, membership_id=member.id, daily_access_id=daily.id,
            qr_token_id=token.id, access_source='MEMBERSHIP_ACCESS', status='SUCCESS', checkin_time=stored_instant(NOW)))
        # Membership-backed booking must also stay out of My bookings.
        db.add(Booking(user_id=1, gym_id=1, gym_slot_id=1, slot_date=NOW.date(), quantity=1, unit_price=0,
            total_price=0, status='CONFIRMED', expires_at=stored_instant(NOW), access_source='MEMBERSHIP_ACCESS'))
        db.commit()
    visits = api[0].get('/api/v1/profile/bookings?status=all&source=individual', headers=api[1][1]).json()
    assert [v['booking_id'] for v in visits] == [booked['id']]
    response = api[0].get(f'/api/v1/profile/membership-visits?year={NOW.year}&month={NOW.month}', headers=api[1][1])
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 1 and response.json()['items'][0]['membership_id'] == membership_id
    assert api[0].get(f'/api/v1/profile/membership-visits?year={NOW.year}&month={NOW.month}', headers=api[1][4]).json()['total'] == 0
    assert api[0].get('/api/v1/profile', headers=api[1][1]).json()['has_membership_history']
    assert not api[0].get('/api/v1/profile', headers=api[1][4]).json()['has_membership_history']