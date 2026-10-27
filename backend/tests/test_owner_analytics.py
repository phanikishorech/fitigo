"""Real reporting endpoints over disposable data; no fabricated chart metrics."""
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from app.core.time import ist_day_bounds
from app.models.booking import Payment
from app.models.gym import Gym
from test_owner_dashboard_metrics import api, booking, checkin, paid_booking, summary, DAY, NOW
from test_owner_business_metrics import membership_sale

BASE = '/api/v1/gym-owner/analytics'


def get(api, suffix='', **params):
    response = api[0].get(BASE + suffix, headers=api[1][1], params={'date_from': str(DAY), 'date_to': str(DAY), **params})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def seed(api):
    with Session(api[2]) as db:
        for gid, amount in [(1, 100), (2, 200), (3, 900)]:
            row = booking(db, gid, day=DAY)
            paid_booking(db, row, amount)
            checkin(db, gid, booked=row)
        membership_sale(db, 1, 500)
        membership_sale(db, 2, 700)
        membership_sale(db, None, 9000)
        checkin(db, 1)
        checkin(db, 1, access_type='SINGLE_GYM')
        db.commit()


def test_overview_series_transactions_and_gym_revenue_reconcile(api):
    seed(api)
    data = get(api)
    assert data['summary'] == summary(api)
    assert data['series'] == [{'date': str(DAY), 'date_to': str(DAY), 'visits': 4, 'revenue': '1500.00'}]
    assert sum(Decimal(row['total']) for row in data['revenue_by_gym']) == Decimal(data['summary']['revenue']['total'])
    assert {r['gym_id'] for r in data['revenue_by_gym']} == {1, 2}
    records = get(api, '/transactions')
    assert records['total'] == 4
    assert sum(Decimal(row['recognized_amount']) for row in records['items']) == Decimal('1500')
    assert get(api, '/attendance')['total'] == 4
    for gid in (1, 2):
        selected = get(api, gym_id=gid)
        assert selected['summary'] == summary(api, gid)
        assert all(row['gym_id'] == gid for row in get(api, '/transactions', gym_id=gid)['items'])
        assert get(api, '/bookings', gym_id=gid)['total'] == 1


def test_daily_ist_boundaries_and_zero_days_then_weekly_buckets(api):
    start, end = ist_day_bounds(DAY)
    with Session(api[2]) as db:
        for moment in [start - timedelta(seconds=1), start, end - timedelta(seconds=1), end]:
            row = booking(db, 1)
            checkin(db, 1, booked=row, at=moment)
            paid_booking(db, row, 100, at=moment)
        db.commit()
    assert get(api)['series'][0]['visits'] == 2
    assert get(api)['series'][0]['revenue'] == '200.00'
    daily = get(api, date_from=str(DAY - timedelta(days=3)))
    assert daily['grouping'] == 'daily' and daily['series'][0]['visits'] == 0
    weekly = get(api, date_from=str(DAY - timedelta(days=100)))
    assert weekly['grouping'] == 'weekly'
    assert len(weekly['series']) == 15
    assert weekly['series'][-1]['date_to'] == str(DAY)
    assert sum(row['visits'] for row in weekly['series']) == weekly['summary']['visits']['total'] == 3
    assert sum(Decimal(row['revenue']) for row in weekly['series']) == Decimal(weekly['summary']['revenue']['total'])


def test_paginated_records_filter_in_database_not_in_loaded_page(api):
    with Session(api[2]) as db:
        for index in range(13):
            row = booking(db, 1, status='CANCELLED' if index % 2 else 'CONFIRMED')
            paid_booking(db, row, 100, status='FAILED' if index % 2 else 'PAID')
        db.commit()
    first, second = get(api, '/bookings', limit=10), get(api, '/bookings', limit=10, offset=10)
    assert first['total'] == second['total'] == 13
    assert len(first['items']) == 10 and len(second['items']) == 3
    assert not {r['id'] for r in first['items']} & {r['id'] for r in second['items']}
    cancelled = get(api, '/bookings', category='cancelled', limit=2)
    assert cancelled['total'] == 6 and len(cancelled['items']) == 2
    failed = get(api, '/transactions', payment_status='FAILED', category='individual_booking', limit=2)
    assert failed['total'] == 6 and len(failed['items']) == 2
    assert all(not r['included'] and Decimal(r['recognized_amount']) == 0 for r in failed['items'])


def test_refunds_test_sales_and_pending_records_visible_but_not_chart_income(api):
    with Session(api[2]) as db:
        for state in ['PAID', 'FAILED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'PENDING']:
            row = booking(db, 1)
            paid_booking(db, row, 100, status=state)
            checkin(db, 1, booked=row)
            membership_sale(db, 1, 500, state=state)
        paid_booking(db, booking(db, 1), 1000, mode='test')
        db.commit()
    data = get(api)
    assert data['series'][0]['revenue'] == data['summary']['revenue']['total'] == '600.00'
    assert get(api, '/transactions')['total'] == 10  # Test sale is outside live reporting scope.
    assert get(api, '/transactions', category='single_gym_membership')['total'] == 5
    assert get(api, '/transactions', payment_status='REFUNDED')['total'] == 2


def test_upcoming_visits_are_paid_future_places_not_upcoming_reservation_count(api):
    tomorrow = DAY + timedelta(days=1)
    with Session(api[2]) as db:
        valid = booking(db, 1, day=tomorrow, quantity=3)
        paid_booking(db, valid, 300)
        unpaid = booking(db, 1, day=tomorrow, quantity=4)
        db.add(Payment(booking_id=unpaid.id, amount=400, status='FAILED'))
        checked = booking(db, 1, day=tomorrow, quantity=2)
        paid_booking(db, checked, 200); checkin(db, 1, booked=checked)
        inactive = booking(db, 2, day=tomorrow)
        paid_booking(db, inactive, 100); db.get(Gym, 2).is_active = False
        cancelled = booking(db, 1, day=tomorrow, status='CANCELLED')
        paid_booking(db, cancelled, 100)
        current = booking(db, 1, day=DAY, quantity=5)  # window is open, but scheduled start already passed
        paid_booking(db, current, 500)
        db.commit()
    result = get(api, date_to=str(tomorrow))['summary']
    assert result['upcoming_visits'] == 3
    assert result['attendance']['upcoming'] == 4
    assert result['upcoming_visits'] == api[0].get('/api/v1/gym-owner/dashboard/summary', headers=api[1][1],
        params={'date_from': str(DAY), 'date_to': str(tomorrow)}).json()['upcoming_visits']


@pytest.mark.parametrize('suffix', ['', '/bookings', '/transactions', '/attendance'])
def test_empty_scope_authorization_and_invalid_dates(api, suffix):
    assert get(api, suffix) is not None
    for actor in (3, 4):
        assert api[0].get(BASE + suffix, headers=api[1][actor]).status_code == 403
    assert api[0].get(BASE + suffix).status_code == 401
    assert api[0].get(BASE + suffix, headers=api[1][1], params={'gym_id': 3}).status_code == 404
    assert api[0].get(BASE + suffix, headers=api[1][1], params={'date_from': str(DAY)}).status_code == 422
    assert api[0].get(BASE + suffix, headers=api[1][1], params={'date_from': '2020-01-01', 'date_to': '2026-10-19'}).status_code == 422


def test_invalid_table_filters_and_pagination(api):
    for suffix, params in [('/bookings', {'category': 'fake'}), ('/transactions', {'payment_status': 'fake'}),
        ('/attendance', {'limit': 101}), ('/transactions', {'offset': -1})]:
        assert api[0].get(BASE + suffix, headers=api[1][1], params=params).status_code == 422


@pytest.mark.parametrize('mode,environment,expected_mode', [
    ('test', None, 'test'), ('live', None, 'live'),
    ('live', 'sandbox', 'test'), ('test', 'production', 'live'),
])
def test_revenue_uses_existing_effective_payment_mode_everywhere(api, monkeypatch, mode, environment, expected_mode):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'payment_mode', mode)
    monkeypatch.setattr(settings, 'payment_env', environment)
    with Session(api[2]) as db:
        for sale_mode, amount in [('test', 100), ('live', 900)]:
            row = booking(db, 1)
            paid_booking(db, row, amount, mode=sale_mode)
            checkin(db, 1, booked=row)
            membership_sale(db, 1, amount * 2, mode=sale_mode)
            paid_booking(db, booking(db, 1), amount, mode=sale_mode, status='REFUNDED')
            paid_booking(db, booking(db, 1), amount, mode=sale_mode, status='PARTIALLY_REFUNDED')
            paid_booking(db, booking(db, 1), amount, mode=sale_mode, status='FAILED')
        db.commit()
    amount = Decimal(100 if expected_mode == 'test' else 900)
    overview = get(api)
    revenue = overview['summary']['revenue']
    assert revenue['mode'] == expected_mode
    assert Decimal(revenue['total']) == amount * 3
    assert revenue == summary(api)['revenue']
    assert Decimal(overview['series'][0]['revenue']) == amount * 3
    assert Decimal(overview['revenue_by_gym'][0]['total']) == amount * 3
    assert Decimal(revenue['fully_refunded_sales']) == amount
    assert revenue['partial_refund_count'] == 1
    transactions = get(api, '/transactions')
    assert transactions['total'] == 5
    assert {row['mode'] for row in transactions['items']} == {expected_mode}
    assert sum(Decimal(row['recognized_amount']) for row in transactions['items']) == amount * 3


@pytest.mark.parametrize('mode', ['test', 'live'])
def test_booking_revenue_requires_checkin_membership_does_not_and_group_does_not_multiply(api, monkeypatch, mode):
    from app.core.config import settings
    from app.models.booking import Booking
    monkeypatch.setattr(settings, 'payment_mode', mode)
    with Session(api[2]) as db:
        row = booking(db, 1, quantity=3)
        paid_booking(db, row, 450, mode=mode)
        member = membership_sale(db, 1, 500, mode=mode)
        row_id = row.id
        db.commit()
    before = get(api)
    assert before['summary']['revenue']['total'] == '500.00'
    assert before['summary']['revenue']['individual_booking'] == '0.00'
    pending = next(r for r in get(api, '/transactions')['items'] if r['booking_id'] == row_id)
    assert pending['payment_status'] == 'PAID' and not pending['included']
    assert pending['exclusion_reason'] == 'NO_ELIGIBLE_CHECKIN'
    with Session(api[2]) as db:
        row = db.get(Booking, row_id)
        checkin(db, 1, booked=row, visitor_index=0)
        db.commit()
    assert get(api)['summary']['revenue']['total'] == '950.00'
    with Session(api[2]) as db:
        row = db.get(Booking, row_id)
        checkin(db, 1, booked=row, visitor_index=1)
        checkin(db, 1, booked=row, visitor_index=2)
        checkin(db, 1, access_type='SINGLE_GYM')
        db.commit()
    after = get(api)
    assert after['summary']['revenue']['total'] == after['series'][0]['revenue'] == '950.00'
    assert after['summary']['revenue']['single_gym_membership'] == '500.00'
    assert after['revenue_by_gym'][0]['total'] == '950.00'
    assert sum(Decimal(r['recognized_amount']) for r in get(api, '/transactions')['items']) == Decimal('950')


@pytest.mark.parametrize('case', ['manual', 'rejected', 'cancelled', 'no_show', 'wrong_gym'])
def test_only_eligible_successful_checkin_releases_paid_booking_revenue(api, case):
    with Session(api[2]) as db:
        row = booking(db, 1, attended=case == 'manual', status='CANCELLED' if case == 'cancelled' else 'CONFIRMED')
        paid_booking(db, row, 150)
        if case == 'no_show':
            row.attendance_status = 'NO_SHOW'
        if case != 'manual':
            checkin(db, 2 if case == 'wrong_gym' else 1, booked=row, status='REJECTED' if case == 'rejected' else 'SUCCESS')
        db.commit()
    assert get(api)['summary']['revenue']['total'] == '0.00'


def test_later_checkin_unlocks_original_purchase_period_not_double_recognition(api):
    with Session(api[2]) as db:
        row = booking(db, 1, day=DAY + timedelta(days=1))
        paid_booking(db, row, 150)
        row_id = row.id
        db.commit()
    assert get(api)['summary']['revenue']['total'] == '0.00'
    from app.models.booking import Booking
    with Session(api[2]) as db:
        checkin(db, 1, booked=db.get(Booking, row_id), at=NOW + timedelta(days=1))
        db.commit()
    assert get(api)['summary']['revenue']['total'] == '150.00'
    tomorrow = str(DAY + timedelta(days=1))
    next_day = get(api, date_from=tomorrow, date_to=tomorrow)
    assert next_day['summary']['visits']['total'] == 1
    assert next_day['summary']['revenue']['total'] == '0.00'