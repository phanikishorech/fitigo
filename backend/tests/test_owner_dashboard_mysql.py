"""Real MySQL ONLY_FULL_GROUP_BY regression, in a disposable database only."""
import os
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.core.time import IST, stored_instant
from app.database.base import Base
from app.database.session import engine as application_engine, get_db
from app.models.auth import Role, User, UserRole
from app.models.gym import Gym
from app.models.slot import GymSlot
from app.routers import gym_owner
from app.services import owner_dashboard_service, owner_metric_rules
from test_owner_dashboard_metrics import booking, checkin, paid_booking, SUMMARY

pytestmark = pytest.mark.skipif(os.getenv('FITIGO_MYSQL_DASHBOARD_TESTS') != '1',
    reason='Disposable MySQL dashboard tests are opt-in')
DAY = date(2026, 10, 27)
NOW = datetime(2026, 10, 27, 12, tzinfo=IST)


@pytest.fixture
def mysql_api(monkeypatch):
    monkeypatch.setattr(settings, 'payment_mode', 'live')
    assert application_engine is not None
    assert application_engine.url.host in ('localhost', '127.0.0.1', '::1')
    assert settings.environment == 'development'
    name = 'fitigo_dashboard_test_' + uuid4().hex[:12]
    control = create_engine(application_engine.url.set(database=None), isolation_level='AUTOCOMMIT')
    engine, created = None, False
    try:
        with control.connect() as db:
            db.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
        created = True
        engine = create_engine(application_engine.url.set(database=name))

        @event.listens_for(engine, 'connect')
        def strict_mode(connection, _):
            with connection.cursor() as cursor:
                cursor.execute('SELECT @@SESSION.sql_mode')
                modes = set(filter(None, cursor.fetchone()[0].split(',')))
                modes.add('ONLY_FULL_GROUP_BY')
                cursor.execute('SET SESSION sql_mode = %s', (','.join(sorted(modes)),))

        Base.metadata.create_all(engine)
        monkeypatch.setattr(owner_dashboard_service, 'ist_today', lambda: DAY)
        monkeypatch.setattr(owner_dashboard_service, 'ist_now', lambda: NOW)
        monkeypatch.setattr(owner_metric_rules, 'ist_now', lambda: NOW)
        with Session(engine) as db:
            assert 'ONLY_FULL_GROUP_BY' in db.scalar(text('SELECT @@SESSION.sql_mode'))
            for uid in (1, 2, 3, 5):
                db.add(User(id=uid, email=f'owner-mysql-{uid}@example.test', password_hash='unused', status='ACTIVE'))
            db.add(Role(id=1, name='GYM_OWNER')); db.flush()
            for uid in (1, 2, 5):
                db.add(UserRole(user_id=uid, role_id=1))
            for gid, owner in ((1, 1), (2, 1), (3, 2)):
                db.add(Gym(id=gid, owner_user_id=owner, name=f'Gym {gid}', status='APPROVED')); db.flush()
                db.add(GymSlot(id=gid, gym_id=gid, name='Visit', start_time=time(9), end_time=time(18), capacity=100, price=100))
            db.commit()
        app = FastAPI()
        app.include_router(gym_owner.router, prefix='/api/v1')

        def database():
            with Session(engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        headers = {uid: {'Authorization': f'Bearer {create_access_token(str(uid))}'} for uid in (1, 2, 5)}
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, headers, engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with control.connect() as db:
                db.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


@pytest.mark.parametrize('populated', [False, True])
def test_summary_strict_mysql_categories_scope_and_booking_links(mysql_api, populated):
    client, headers, engine = mysql_api
    expected = dict(upcoming=0, attended=0, cancelled=0, no_show=0, pending_payment=0, expired=0, unresolved=0)
    if populated:
        with Session(engine) as db:
            for state in ('CONFIRMED', 'CANCELLED', 'PENDING_PAYMENT', 'EXPIRED'):
                booking(db, 1, status=state, day=DAY)
            no_show = booking(db, 1, day=DAY); no_show.attendance_status = 'NO_SHOW'
            attended = booking(db, 1, quantity=3, day=DAY)
            for index in (0, 1):
                checkin(db, 1, booked=attended, visitor_index=index, at=stored_instant(NOW))
            paid_booking(db, attended, 300, at=stored_instant(NOW))
            past = GymSlot(gym_id=1, name='Past window', start_time=time(7), end_time=time(8), capacity=10, price=100)
            db.add(past); db.flush()
            unresolved = booking(db, 1, day=DAY); unresolved.gym_slot_id = past.id
            booking(db, 2, day=DAY)
            booking(db, 3, day=DAY)  # Another owner must not leak into totals.
            booking(db, 1, day=DAY + timedelta(days=1))
            db.commit()
        expected = dict.fromkeys(expected, 1)
    params = {'date_from': str(DAY), 'date_to': str(DAY)}
    for gym_id in (None, 1, 2):
        response = client.get(SUMMARY, headers=headers[1], params={**params, **({'gym_id': gym_id} if gym_id else {})})
        assert response.status_code == 200, response.text
        data = response.json()
        counts = expected.copy() if gym_id != 2 else dict.fromkeys(expected, 0)
        if populated and gym_id != 1:
            counts['upcoming'] = 2 if gym_id is None else 1
        assert data['attendance'] == counts
        assert sum(counts.values()) == data['bookings']['in_period']
        assert data['visits']['individual_booking'] == (2 if populated and gym_id != 2 else 0)
        assert float(data['revenue']['total']) == (300 if populated and gym_id != 2 else 0)
    for category, count in expected.items():
        response = client.get('/api/v1/gym-owner/gyms/1/bookings', headers=headers[1],
            params={**params, 'attendance_category': category})
        assert response.status_code == 200, response.text
        assert len(response.json()) == count
    assert client.get(SUMMARY, headers=headers[1], params={**params, 'gym_id': 3}).status_code == 404
    empty = client.get(SUMMARY, headers=headers[5], params=params)
    assert empty.status_code == 200, empty.text
    assert sum(empty.json()['attendance'].values()) == 0


@pytest.mark.parametrize('mode', ['test', 'live'])
def test_analytics_strict_mysql_chart_and_records(mysql_api, monkeypatch, mode):
    monkeypatch.setattr(settings, 'payment_mode', mode)
    client, headers, engine = mysql_api
    with Session(engine) as db:
        row = booking(db, 1, day=DAY)
        paid_booking(db, row, 100, at=stored_instant(NOW), mode=mode)
        checkin(db, 1, booked=row, at=stored_instant(NOW))
        db.commit()
    for days in (0, 100):
        params = {'date_from': str(DAY - timedelta(days=days)), 'date_to': str(DAY)}
        for gym_id in (None, 1):
            scope = {**params, **({'gym_id': gym_id} if gym_id else {})}
            response = client.get('/api/v1/gym-owner/analytics', headers=headers[1], params=scope)
            assert response.status_code == 200, response.text
            data = response.json()
            assert sum(point['visits'] for point in data['series']) == 1
            assert sum(float(point['revenue']) for point in data['series']) == 100
            for suffix in ('bookings', 'transactions', 'attendance'):
                records = client.get(f'/api/v1/gym-owner/analytics/{suffix}', headers=headers[1], params=scope)
                assert records.status_code == 200, records.text
                assert records.json()['total'] == 1