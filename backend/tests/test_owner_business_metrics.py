"""Reporting rules only; never connects to the configured application database."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session
from app.core.time import ist_day_bounds
from app.models.booking import Payment
from app.models.membership import UserMembership
from app.models.payment_checkout import PaymentCheckout
from test_owner_dashboard_metrics import api, booking, checkin, paid_booking, summary, DAY, NOW, SUMMARY
from test_booking_access_qr import api as scanner_api, create, qr, scan, NOW as SCAN_NOW
from app.services.owner_dashboard_service import OwnerDashboardService


def membership_sale(db, gym, amount, at=NOW, state='PAID', mode='live'):
    key = str(uuid4())
    checkout = PaymentCheckout(id=key, user_id=3, source_key=key, kind='SINGLE_GYM', mode=mode,
        key_id='fixture', amount=amount, currency='INR', snapshot={}, status=state,
        provider='CASHFREE', gateway_payment_id=f'cf_{key}', created_at=at)
    db.add(checkout); db.flush()
    member = UserMembership(user_id=3, gym_id=gym, membership_type='SINGLE_GYM' if gym else 'MULTI_GYM',
        gateway_checkout_id=key, paid_amount=amount, payment_status=state, payment_provider='CASHFREE',
        start_at=at, end_at=at + timedelta(days=30), created_at=at)
    db.add(member); db.flush()
    return member


def test_categories_are_disjoint_future_pending_manual_cancelled_and_no_show(api):
    with Session(api[2]) as db:
        future = booking(db, 1, day=DAY + timedelta(days=1))
        booking(db, 1, status='PENDING_PAYMENT')
        booking(db, 1, status='EXPIRED')
        booking(db, 1, day=DAY - timedelta(days=1), attended=True)  # Not scanned: unresolved.
        attended = booking(db, 1, quantity=4)
        checkin(db, 1, booked=attended, visitor_index=0)
        checkin(db, 1, booked=attended, visitor_index=1)
        cancelled = booking(db, 1, status='CANCELLED')
        checkin(db, 1, booked=cancelled)  # Inconsistent historical row must not inflate metrics.
        no_show = booking(db, 1)
        no_show.attendance_status = 'NO_SHOW'
        checkin(db, 1, booked=no_show)
        db.commit()
    params = {'date_from': str(DAY - timedelta(days=1)), 'date_to': str(DAY + timedelta(days=1)), 'gym_id': 1}
    data = api[0].get(SUMMARY, headers=api[1][1], params=params).json()
    assert data['visits']['individual_booking'] == data['visits']['total'] == 2
    assert data['attendance'] == dict(upcoming=1, attended=1, cancelled=1, no_show=1, pending_payment=1, expired=1, unresolved=1)
    assert sum(data['attendance'].values()) == data['bookings']['in_period'] == 7
    for category, count in data['attendance'].items():
        response = api[0].get('/api/v1/gym-owner/gyms/1/bookings', headers=api[1][1],
            params={**params, 'attendance_category': category})
        assert response.status_code == 200, response.text
        assert len(response.json()) == count
    assert summary(api, 1, DAY + timedelta(days=1))['attendance']['upcoming'] == 1
    assert summary(api, 1, DAY + timedelta(days=1))['visits']['total'] == 0


def test_revenue_counts_verified_sales_once_not_visits_and_scopes_owner(api):
    with Session(api[2]) as db:
        membership_sale(db, 1, 500)
        membership_sale(db, 2, 700)
        membership_sale(db, 3, 9000)  # Other owner.
        membership_sale(db, None, 8000)  # Platform sale is not gym income.
        group = booking(db, 1, quantity=3, day=DAY + timedelta(days=10))
        paid_booking(db, group, 250)
        checkin(db, 1, booked=group)
        other = booking(db, 2)
        paid_booking(db, other, 100)
        checkin(db, 2, booked=other)
        for _ in range(3):
            checkin(db, 1, access_type='SINGLE_GYM')
        db.commit()
    selected, overall = summary(api, 1), summary(api)
    assert selected['revenue']['single_gym_membership'] == '500.00'
    assert selected['revenue']['individual_booking'] == '250.00'
    assert selected['revenue']['total'] == '750.00'
    assert selected['visits']['single_gym_membership'] == 3
    assert overall['revenue']['total'] == '1550.00'
    assert Decimal(overall['revenue']['total']) == sum(Decimal(summary(api, gym)['revenue']['total']) for gym in (1, 2))
    assert summary(api, 1, DAY + timedelta(days=10))['revenue']['total'] == '0.00'


def test_failed_pending_refunds_test_and_legacy_payments_do_not_inflate_revenue(api):
    with Session(api[2]) as db:
        for state in ['FAILED', 'PENDING', 'REFUNDED', 'PARTIALLY_REFUNDED', 'REVIEW_REQUIRED']:
            paid_booking(db, booking(db, 1), 100, status=state)
            membership_sale(db, 1, 200, state=state)
        paid_booking(db, booking(db, 1), 300, mode='test')
        membership_sale(db, 1, 400, mode='test')
        legacy = booking(db, 1)
        db.add(Payment(booking_id=legacy.id, amount=900, status='PAID', provider='DUMMY', created_at=NOW))
        # Cancelled paid bookings must not contribute recognized booking revenue.
        paid_booking(db, booking(db, 1, status='CANCELLED'), 50)
        db.commit()
    result = summary(api, 1)['revenue']
    assert result['total'] == result['individual_booking'] == '0.00'
    assert result['single_gym_membership'] == '0.00'
    assert result['partial_refund_count'] == 2
    assert result['fully_refunded_sales'] == '300.00'
    assert result['excluded_paid_records'] == 2  # Other-mode sales are outside the report scope.


def test_purchase_date_ist_boundaries_are_identical_for_both_revenue_components(api):
    start, end = ist_day_bounds(DAY)
    with Session(api[2]) as db:
        for at in [start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end]:
            row = booking(db, 1)
            checkout = paid_booking(db, row, 100, at=at)
            checkin(db, 1, booked=row, at=at)
            checkout.updated_at = end + timedelta(days=10)  # Refresh must not move revenue.
            member = membership_sale(db, 1, 500, at=at)
            member.updated_at = end + timedelta(days=10)
        db.commit()
    revenue = summary(api, 1)['revenue']
    assert revenue['single_gym_membership'] == '1000.00'
    assert revenue['individual_booking'] == '200.00'
    assert revenue['total'] == '1200.00'


def test_invalid_category_and_other_owner_list_are_rejected(api):
    assert api[0].get('/api/v1/gym-owner/gyms/1/bookings?attendance_category=fake', headers=api[1][1]).status_code == 422
    assert api[0].get('/api/v1/gym-owner/gyms/3/bookings?attendance_category=attended', headers=api[1][1]).status_code == 404
    response = api[0].get(SUMMARY, headers=api[1][1])
    assert response.headers['cache-control'] == 'no-store'


def test_real_scanner_duplicate_does_not_increment_dashboard(scanner_api):
    booked = create(scanner_api, ['Visitor'])
    from app.models.booking import Booking
    from app.core.time import stored_instant
    # Attach a verified test checkout to the fixture's paid booking without
    # replacing the real scanner or creating another payment row.
    with Session(scanner_api[2]) as db:
        key = str(uuid4())
        db.add(PaymentCheckout(id=key, user_id=1, source_key=key, kind='BOOKING', mode='test',
            key_id='fixture', amount=100, currency='INR', snapshot={}, status='PAID',
            provider='RAZORPAY', gateway_payment_id=f'pay_{key}', created_at=stored_instant(SCAN_NOW)))
        db.flush()
        db.get(Booking, booked['id']).checkout_id = key
        db.commit()
    def visits():
        with Session(scanner_api[2]) as db:
            return OwnerDashboardService(db).summary(owner_user_id=2, gym_id=1, day=SCAN_NOW.date())['visits']
    def revenue():
        with Session(scanner_api[2]) as db:
            return OwnerDashboardService(db).summary(owner_user_id=2, gym_id=1, day=SCAN_NOW.date())['revenue']['total']
    assert visits()['total'] == 0
    assert revenue() == '0.00'
    token = qr(scanner_api, booked)[0]['qr_token']
    assert scan(scanner_api, token)['success']
    assert visits()['individual_booking'] == visits()['total'] == 1
    assert revenue() == '100.00'
    assert not scan(scanner_api, token)['success']
    assert visits()['total'] == 1
    assert revenue() == '100.00'