"""Reuse the opt-in disposable strict-MySQL reporting fixture, never working data."""
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token
from app.models.auth import Role, UserRole
from app.routers import admin
from test_owner_dashboard_mysql import mysql_api, pytestmark, DAY
from test_owner_dashboard_metrics import booking, paid_booking


@pytest.mark.parametrize('mode', ['test', 'live'])
def test_admin_grouped_revenue_is_mode_scoped_on_strict_mysql(mysql_api, monkeypatch, mode):
    client, _, engine = mysql_api
    monkeypatch.setattr(settings, 'payment_mode', mode)
    client.app.include_router(admin.router, prefix='/api/v1')
    with Session(engine) as db:
        db.add(Role(id=2, name='ADMIN')); db.flush()
        db.add(UserRole(user_id=5, role_id=2))
        for gym, amount, row_mode in [(1, 100, mode), (2, 200, mode), (1, 900, 'live' if mode == 'test' else 'test')]:
            paid_booking(db, booking(db, gym, day=DAY), amount, mode=row_mode)
        db.commit()
    headers = {'Authorization': 'Bearer '+create_access_token('5')}
    params = {'date_from': str(DAY), 'date_to': str(DAY)}
    summary = client.get('/api/v1/admin/dashboard/summary', params=params, headers=headers)
    report = client.get('/api/v1/admin/reports/bookings/daily', params=params, headers=headers)
    assert summary.status_code == report.status_code == 200
    assert Decimal(summary.json()['revenue']['in_period']) == 0  # Paid but never checked in.
    assert Decimal(report.json()[0]['paid_amount_total']) == 300
    assert report.json()[0]['mode'] == mode
    selected = client.get('/api/v1/admin/reports/bookings/daily', params={**params, 'gym_id': 1}, headers=headers)
    assert selected.status_code == 200 and Decimal(selected.json()[0]['paid_amount_total']) == 100
    for grain in ['day', 'week', 'month']:
        analytics = client.get('/api/v1/admin/analytics', params={**params, 'grain': grain}, headers=headers)
        assert analytics.status_code == 200, analytics.text
        data = analytics.json()
        assert data['summary']['bookings'] == 3
        assert Decimal(data['summary']['paid_amount']) == 300
        assert sum(g['bookings'] for g in data['gyms']) == 3
        assert sum(Decimal(row['paid_amount']) for row in data['series']) == 300