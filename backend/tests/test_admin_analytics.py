"""Read-only admin aggregate tests; run through the isolated database runner."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Payment
from app.models.gym import Gym
from test_dashboard_date_ranges import api, owner_api, booking, paid_booking, get, DAY


def report(api, **params):
    return get(api, 'admin/analytics', {'date_from': str(DAY), 'date_to': str(DAY), **params}, actor=6)


def test_empty_report_keeps_catalog_and_zero_fills_dates(api):
    result = report(api, date_from=str(DAY - timedelta(days=2)))
    assert result['summary']['bookings'] == result['summary']['unique_customers'] == 0
    assert result['summary']['confirmation_rate'] is None
    assert len(result['gyms']) == 3 and len(result['series']) == 3
    assert all(row['bookings'] == 0 for row in result['series'])
    assert result['catalog'] == {'gyms': 3, 'active_gyms': 3, 'gyms_with_bookings': 0}
    assert result['previous']['date_from'] == str(DAY - timedelta(days=5))
    assert result['previous']['date_to'] == str(DAY - timedelta(days=3))


@pytest.mark.parametrize('grain', ['day', 'week', 'month'])
@pytest.mark.parametrize('mode', ['test', 'live'])
def test_grains_financial_scope_locations_and_previous_period(api, monkeypatch, grain, mode):
    monkeypatch.setattr(settings, 'payment_env', 'sandbox' if mode == 'test' else 'production')
    with Session(api[2]) as db:
        for identifier, state in [(1, 'State A'), (2, 'State B')]:
            gym = db.get(Gym, identifier)
            gym.city, gym.state, gym.country = ' Same city ', state, 'India'
        paid_booking(db, booking(db, 1, quantity=2, attended=True), 100, mode=mode)
        paid_booking(db, booking(db, 2, status='CANCELLED'), 200, mode=mode)
        paid_booking(db, booking(db, 1), 900, mode='live' if mode == 'test' else 'test')
        pending = booking(db, 1, status='PENDING_PAYMENT')
        db.add(Payment(booking_id=pending.id, status='FAILED', amount=100))
        reviewed = booking(db, 2)
        paid_booking(db, reviewed, 888, mode=mode).status = 'REVIEW_REQUIRED'
        reviewed.attendance_status = 'NO_SHOW'
        paid_booking(db, booking(db, 1, day=DAY - timedelta(days=1)), 50, mode=mode)
        paid_booking(db, booking(db, 1, day=DAY + timedelta(days=1)), 700, mode=mode)
        db.commit()
    result = report(api, grain=grain)
    s = result['summary']
    assert s['bookings'] == 5 and s['places'] == 6 and s['unique_customers'] == 1
    assert s['confirmed'] == 3 and s['cancelled'] == 1 and s['pending'] == 1
    assert s['attended'] == s['no_show'] == s['failed_payments'] == s['review_required'] == 1
    assert s['paid_bookings'] == 2 and Decimal(s['paid_amount']) == 300
    assert result['previous']['bookings'] == 1 and Decimal(result['previous']['paid_amount']) == 50
    assert result['scope']['mode'] == mode
    assert len(result['locations']) == 3  # identical city names do not merge across states
    assert sum(g['bookings'] for g in result['gyms']) == sum(g['bookings'] for g in result['locations']) == sum(g['bookings'] for g in result['series']) == 5
    assert sum(Decimal(g['paid_amount']) for g in result['gyms']) == Decimal(s['paid_amount'])
    assert result['series'][0]['date_from'] == result['series'][0]['date_to'] == str(DAY)
    assert report(api, state='State A')['summary']['bookings'] == 3
    assert report(api, state='State B', city='Same city')['summary']['bookings'] == 2
    assert report(api, city='')['catalog']['gyms'] == 1
    assert report(api, gym_id=999999)['catalog']['gyms'] == 0
    assert len(report(api, gym_id=1)['options']) == 3


def test_shared_cart_counts_allocations_not_checkout_totals_and_is_read_only(api):
    with Session(api[2]) as db:
        first = booking(db, 1, quantity=2)
        checkout = paid_booking(db, first, 100)
        second = booking(db, 2)
        second.checkout_id = checkout.id
        checkout.kind, checkout.amount = 'CART', 300
        db.add(Payment(booking_id=second.id, status='PAID', provider='RAZORPAY', amount=200))
        db.commit()
    writes = []
    def inspect_sql(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE')):
            writes.append(statement)
    event.listen(api[2], 'before_cursor_execute', inspect_sql)
    try:
        response = api[0].get('/api/v1/admin/analytics', params={'date_from': str(DAY), 'date_to': str(DAY)}, headers=api[1][6])
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['summary']['bookings'] == 2 and result['summary']['places'] == 3
        assert Decimal(result['summary']['paid_amount']) == 300
        assert response.headers['cache-control'] == 'no-store'
        assert writes == []
        assert 'email' not in response.text and 'gateway_payment_id' not in response.text
    finally:
        event.remove(api[2], 'before_cursor_execute', inspect_sql)


@pytest.mark.parametrize('params', [
    {'date_from': str(DAY)}, {'date_from': '2026-12-01', 'date_to': '2026-01-01'},
    {'date_from': '2025-01-01', 'date_to': '2026-01-02'}, {'grain': 'hour'},
    {'gym_id': 0}, {'date_from': '0001-01-02', 'date_to': '0001-01-05'}, {'city': 'x'*101}])
def test_invalid_filters_fail_closed(api, params):
    assert api[0].get('/api/v1/admin/analytics', params=params, headers=api[1][6]).status_code == 422


@pytest.mark.parametrize('actor', [1, 3, 4])
def test_non_admin_cannot_read_analytics(api, actor):
    assert api[0].get('/api/v1/admin/analytics', headers=api[1][actor]).status_code == 403
    assert api[0].get('/api/v1/admin/analytics').status_code == 401


def test_week_month_boundaries_zero_days_and_exact_366_day_limit(api):
    first = DAY.replace(day=1) - timedelta(days=2)
    result = report(api, date_from=str(first), grain='month')
    assert len(result['series']) == 2
    assert result['series'][0]['date_from'] == str(first)
    assert result['series'][-1]['date_to'] == str(DAY)
    result = report(api, date_from=str(DAY - timedelta(days=365)))
    assert len(result['series']) == 366