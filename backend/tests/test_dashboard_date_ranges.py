"""Inclusive owner/admin reporting ranges, using only disposable SQLite data."""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.reporting_range import reporting_range
from app.core.security import create_access_token
from app.core.time import ist_day_bounds
from app.models.auth import Role, User, UserRole
from app.models.booking import Payment
from app.models.gym import Gym
from app.routers import admin
from app.services import admin_dashboard_service
from test_owner_dashboard_metrics import api as owner_api, booking, checkin, paid_booking, DAY, NOW


@pytest.fixture
def api(owner_api, monkeypatch):
    client, headers, engine = owner_api
    client.app.include_router(admin.router, prefix="/api/v1")
    monkeypatch.setattr(admin_dashboard_service, "ist_today", lambda: DAY)
    with Session(engine) as db:
        db.add(Role(id=4, name="ADMIN"))
        db.add(User(id=6, first_name="Admin", email="admin-range@example.test", password_hash="unused", status="ACTIVE"))
        db.flush()
        db.add(UserRole(user_id=6, role_id=4))
        db.commit()
    headers[6] = {"Authorization": f"Bearer {create_access_token('6')}"}
    return client, headers, engine


def get(api, path, params, actor=1):
    response = api[0].get(f"/api/v1/{path}", params=params, headers=api[1][actor])
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_range_includes_both_dates_and_scopes_visits_revenue_bookings_and_attendance(api):
    first, last = DAY - timedelta(days=2), DAY
    start, end = ist_day_bounds(first)[0], ist_day_bounds(last)[1]
    params = {"date_from": str(first), "date_to": str(last)}
    with Session(api[2]) as db:
        for at in [start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end]:
            checkin(db, 1, at=at)
        checkin(db, 2, access_type="SINGLE_GYM")
        checkin(db, 3)
        for day, amount in [(first - timedelta(days=1), 900), (first, 100), (last, 200), (last + timedelta(days=1), 800)]:
            row = booking(db, 1, day=day)
            # Owner revenue uses immutable purchase date, not scheduled date.
            paid_booking(db, row, amount, at=ist_day_bounds(day)[0])
            checkin(db, 1, booked=row, at=ist_day_bounds(day)[0])
        cancelled = booking(db, 1, day=first, status="CANCELLED")
        db.add(Payment(booking_id=cancelled.id, amount=400, status="REFUNDED"))
        other = booking(db, 2, day=last)
        paid_booking(db, other, 50)
        checkin(db, 2, booked=other)
        booking(db, 3, day=last)
        db.commit()
    selected = get(api, 'gym-owner/dashboard/summary', {**params, "gym_id": 1})
    overall = get(api, 'gym-owner/dashboard/summary', params)
    assert selected['date_from'] == str(first) and selected['date_to'] == str(last)
    assert selected['visits']['total'] == 4 and overall['visits']['total'] == 6
    assert selected['bookings']['in_period'] == 3 and selected['bookings']['confirmed_in_period'] == 2
    assert float(selected['revenue']['in_period']) == 300
    assert float(overall['revenue']['in_period']) == 350
    rows = get(api, 'gym-owner/gyms/1/bookings', params)
    assert len(rows) == 3 and all(first <= date.fromisoformat(row['slot_date']) <= last for row in rows)
    attendance = get(api, 'gym-owner/gyms/1/attendance', params)
    assert len(attendance) == 4 and all(row['gym_id'] == 1 for row in attendance)
    assert get(api, 'gym-owner/gyms/1/bookings', {**params, 'limit': 1, 'offset': 1}) == rows[1:2]


def test_admin_new_users_gyms_bookings_revenue_and_chart_share_range(api):
    first, last = DAY - timedelta(days=1), DAY
    start, end = ist_day_bounds(first)[0], ist_day_bounds(last)[1]
    params = {"date_from": str(first), "date_to": str(last)}
    with Session(api[2]) as db:
        for user in db.query(User).all():
            user.created_at = start - timedelta(days=100)
        for gym in db.query(Gym).all():
            gym.created_at = start - timedelta(days=100)
        db.get(User, 1).created_at = start
        db.get(User, 2).created_at = end - timedelta(microseconds=1)
        db.get(User, 3).created_at = end
        db.get(Gym, 1).created_at = start
        db.get(Gym, 2).created_at = end
        db.get(Gym, 3).status = 'PENDING_APPROVAL'
        for gym, day, amount in [(1, first, 100), (2, last, 200), (3, first - timedelta(days=1), 999), (3, last + timedelta(days=1), 888)]:
            row = booking(db, gym, day=day)
            db.add(Payment(booking_id=row.id, amount=amount, status='PAID'))
        db.commit()
    summary = get(api, 'admin/dashboard/summary', params, actor=6)
    assert summary['users']['in_period'] == 2 and summary['users']['total'] == 6
    assert summary['gyms']['in_period'] == 1 and summary['gyms']['total'] == 3
    assert summary['gyms']['pending_approval'] == 1
    assert summary['bookings']['in_period'] == summary['bookings']['confirmed_in_period'] == 2
    assert float(summary['revenue']['in_period']) == 300
    rows = get(api, 'admin/bookings', params, actor=6)
    chart = get(api, 'admin/reports/bookings/daily', {**params, 'limit': 366}, actor=6)
    assert len(rows) == 2
    assert sum(row['total_bookings'] for row in chart) == summary['bookings']['in_period']
    assert sum(float(row['paid_amount_total']) for row in chart) == float(summary['revenue']['in_period'])
    assert get(api, 'admin/dashboard/summary', {"date_from": '2020-01-01', "date_to": '2020-01-01'}, actor=6)['bookings']['in_period'] == 0
    # No-filter callers retain their original fields.
    assert 'last_30d' in get(api, 'admin/dashboard/summary', {}, actor=6)['revenue']


@pytest.mark.parametrize('path,actor', [
    ('gym-owner/dashboard/summary', 1), ('gym-owner/gyms/1/attendance', 1),
    ('gym-owner/gyms/1/bookings', 1), ('admin/dashboard/summary', 6), ('admin/bookings', 6)
])
@pytest.mark.parametrize('params', [
    {'date_from': '2026-10-20', 'date_to': '2026-10-19'},
    {'date_from': '2026-10-19'}, {'date_to': '2026-10-19'},
    {'date_from': '2026-02-30', 'date_to': '2026-03-01'},
    {'date_from': '2025-01-01', 'date_to': '2026-01-02'},
    {'date_from': '9999-12-31', 'date_to': '9999-12-31'},
])
def test_invalid_ranges_are_rejected(api, path, actor, params):
    assert api[0].get(f'/api/v1/{path}', params=params, headers=api[1][actor]).status_code == 422


@pytest.mark.parametrize('path', ['gym-owner/dashboard/summary', 'gym-owner/gyms/1/attendance', 'gym-owner/gyms/1/bookings'])
def test_single_date_cannot_be_mixed_with_range(api, path):
    assert api[0].get(f'/api/v1/{path}', params={'date': str(DAY), 'date_from': str(DAY), 'date_to': str(DAY)}, headers=api[1][1]).status_code == 422


def test_ranges_keep_authorization_and_gym_ownership_checks(api):
    params = {'date_from': str(DAY), 'date_to': str(DAY)}
    for path in ['gym-owner/dashboard/summary?gym_id=3', 'gym-owner/gyms/3/attendance', 'gym-owner/gyms/3/bookings']:
        response = api[0].get(f'/api/v1/{path}', params={**params, **({'gym_id': 3} if 'summary' in path else {})}, headers=api[1][1])
        assert response.status_code == 404
    assert api[0].get('/api/v1/admin/dashboard/summary', params=params, headers=api[1][1]).status_code == 403
    assert api[0].get('/api/v1/gym-owner/dashboard/summary', params=params, headers=api[1][3]).status_code == 403


def test_leap_year_and_single_day_ranges_are_allowed():
    assert reporting_range(date(2024, 1, 1), date(2024, 12, 31)) == (date(2024, 1, 1), date(2024, 12, 31))
    assert reporting_range(DAY, DAY) == (DAY, DAY)