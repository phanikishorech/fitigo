from test_database_guard import disposable_name
"""Opt-in real MySQL row locking + migration round trip in a disposable schema."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.skipif(os.getenv('FITIGO_MYSQL_ACCOUNT_TESTS') != '1', reason='Disposable MySQL account tests are opt-in')


@pytest.fixture
def account_db(monkeypatch):
    from app.core.config import settings
    from app.database.session import engine as application
    from app.models.auth import User, Role, UserRole
    from app.models.gym import Gym
    from app.services import account_delivery
    assert settings.environment == 'development' and application.url.host in {'localhost', '127.0.0.1', '::1'}
    name = disposable_name()
    control = create_engine(application.url.set(database=None), isolation_level='AUTOCOMMIT')
    engine, created = None, False
    try:
        with control.connect() as connection:
            connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')); created = True
        engine = create_engine(application.url.set(database=name))
        config = Config(str(Path(__file__).parents[1]/'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).parents[1]/'alembic'))
        # Do not let in-process Alembic logging disable application test loggers.
        config.config_file_name = None
        monkeypatch.setattr(settings, 'database_url', engine.url.render_as_string(hide_password=False))
        # Round-trip only this historical feature, not later forward-only finance.
        command.upgrade(config, 'bdf69ea12480')
        command.downgrade(config, 'acf58d9e1037')
        command.upgrade(config, 'head')
        monkeypatch.setattr(settings, 'smtp_host', 'smtp.fixture.test')
        monkeypatch.setattr(settings, 'smtp_from', 'sender@example.com')
        monkeypatch.setattr(settings, 'public_frontend_url', 'https://app.example.test')
        mail = []
        monkeypatch.setattr(account_delivery, 'send_email', lambda *args: mail.append(args))
        with Session(engine) as db:
            db.add(User(id=1, email='owner@example.com', password_hash='unused', status='ACTIVE'))
            db.add(Role(id=1, name='GYM_OWNER')); db.flush()
            db.add(UserRole(user_id=1, role_id=1))
            db.add(Gym(id=1, owner_user_id=1, name='Isolated invitation gym', status='APPROVED'))
            db.commit()
        yield engine, mail
    finally:
        if engine: engine.dispose()
        if created:
            with control.connect() as connection: connection.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


def test_concurrent_invitation_acceptance_grants_one_assignment(account_db):
    from app.services.staff_invitation_service import StaffInvitationService
    from app.models.staff import GymStaffAssignment
    engine, mail = account_db
    with Session(engine) as db:
        StaffInvitationService(db).invite(owner_user_id=1, gym_id=1, email='invitee@example.com')
    token = re.search(r'#token=([A-Za-z0-9_-]+)', mail[-1][2]).group(1)
    barrier = Barrier(2)
    def accept(index):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                StaffInvitationService(db).accept(token, 'Private test password 187!', None, f'fixture-{index}')
                return 200
            except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(accept, [1, 2]))
    assert sorted(results) == [200, 400]
    with Session(engine) as db: assert db.scalar(select(func.count(GymStaffAssignment.id))) == 1


def test_concurrent_otp_verification_issues_one_session(account_db):
    from app.services.otp_service import OtpService
    from app.models.auth import RefreshToken
    engine, mail = account_db
    with Session(engine) as db: OtpService(db).send_email_otp(email='owner@example.com')
    code = re.search(r'\b[0-9]{6}\b', mail[-1][2]).group()
    barrier = Barrier(2)
    def verify(index):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                OtpService(db).verify_email_otp(email='owner@example.com', otp=code, client_ip=f'fixture-{index}')
                return 200
            except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(verify, [1, 2]))
    assert sorted(results) == [200, 400]
    with Session(engine) as db: assert db.scalar(select(func.count(RefreshToken.id))) == 1