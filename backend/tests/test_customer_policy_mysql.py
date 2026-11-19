"""Concurrent financial/ownership checks on isolated InnoDB, never working data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time
from threading import Barrier
from uuid import uuid4
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_database_guard import disposable_name
from app.database.base import Base
from app.database.session import engine as runner_engine
from app.core.time import IST, stored_instant
from app.models.auth import User, UserRole, Role
from app.models.gym import Gym, GymOperatingHours
from app.models.slot import GymSlot
from app.models.booking import Booking, Payment
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.membership import UserMembership
from app.models.customer_policy import BookingCancellation, MembershipTransfer
from app.models.access import Checkin
from app.services import booking_cancellation as cancellation, membership_transfer as transfer, access_service, booking_access_service


@pytest.fixture
def database(monkeypatch):
    name = disposable_name()
    control = create_engine(runner_engine.url.set(database=None), isolation_level='AUTOCOMMIT')
    with control.connect() as connection: connection.execute(text(f'CREATE DATABASE `{name}`'))
    engine = create_engine(runner_engine.url.set(database=name), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 12, 15, tzinfo=IST)
    monkeypatch.setattr(cancellation, 'utcnow', lambda: now)
    monkeypatch.setattr(transfer, 'utcnow', lambda: now)
    monkeypatch.setattr(access_service, 'utcnow', lambda: now)
    monkeypatch.setattr(access_service, 'access_today', lambda: now.date())
    from app.services import membership_pause_service
    monkeypatch.setattr(membership_pause_service, 'utcnow', lambda: now)
    with Session(engine) as db:
        role = Role(name='CUSTOMER'); db.add(role); db.flush()
        for uid in (1, 2, 3):
            db.add(User(id=uid, first_name=f'Fixture {uid}', email=f'policy-{uid}@example.com', password_hash='unused', status='ACTIVE', is_email_verified=True))
            db.flush(); db.add(UserRole(user_id=uid, role_id=role.id))
        db.add(Gym(id=1, owner_user_id=3, name='Isolated policy gym', status='APPROVED', is_active=True, multi_gym_enabled=True))
        db.flush()
        db.add(GymOperatingHours(gym_id=1, day_of_week=now.weekday(), open_time=time(6), close_time=time(23), is_closed=False))
        db.add(GymSlot(id=1, gym_id=1, name='Policy visit', start_time=time(18), end_time=time(19), capacity=10, price=100, is_active=1))
        db.add(WalletAccount(id=1, user_id=1, balance=500, currency='INR', payment_mode='test')); db.flush()
        db.add(WalletTransaction(id=1, account_id=1, user_id=1, direction='OUT', txn_type='PAYMENT', amount=100, currency='INR')); db.flush()
        db.add(Booking(id=1, user_id=1, gym_id=1, gym_slot_id=1, slot_date=now.date(), quantity=1, unit_price=100,
            total_price=100, currency='INR', status='CONFIRMED', visitor_names=['Fixture visitor'], expires_at=stored_instant(now+timedelta(hours=10))))
        db.flush(); db.add(Payment(booking_id=1, provider='WALLET', status='PAID', amount=100, currency='INR', external_ref='WALLET_TXN:1'))
        db.add(UserMembership(id=1, user_id=1, membership_type='MULTI_GYM', status='ACTIVE', start_at=stored_instant(now-timedelta(days=1)),
            end_at=stored_instant(now+timedelta(days=20)), paid_amount=100, currency='INR', payment_provider='WALLET', payment_status='PAID'))
        db.commit()
    yield engine, now
    engine.dispose()
    with control.connect() as connection: connection.execute(text(f'DROP DATABASE `{name}`'))
    control.dispose()


def race(*operations):
    barrier = Barrier(len(operations))
    def run(operation):
        barrier.wait(timeout=15)
        try: return operation()
        except HTTPException: return 'rejected'
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        return [future.result(timeout=25) for future in futures]


def test_concurrent_cancellation_only_one_credit(database):
    engine, _ = database
    def cancel():
        with Session(engine) as db:
            cancellation.cancel(db, booking_id=1, actor_id=1, customer_id=1, reason='Concurrency test')
            return 'cancelled'
    assert sorted(race(cancel, cancel)) == ['cancelled', 'rejected']
    with Session(engine) as db:
        assert db.get(WalletAccount, 1).balance == 600
        assert db.scalar(select(func.count(BookingCancellation.id))) == 1
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction == 'IN')) == 1


def test_checkin_and_cancellation_serialize_on_booking(database, monkeypatch):
    engine, now = database
    # Deliberately overlap policy clocks to prove row locks, not merely disjoint windows.
    monkeypatch.setattr(booking_access_service, 'utcnow', lambda: now + timedelta(hours=3))
    with Session(engine) as db: qr = booking_access_service.BookingAccessService(db).issue(1, 1)['passes'][0]['qr_token']
    def cancel():
        with Session(engine) as db:
            cancellation.cancel(db, booking_id=1, actor_id=1, customer_id=1); return 'cancelled'
    def scan():
        with Session(engine) as db:
            access_service.AccessService(db).validate_checkin(gym_id=1, qr_token=qr, scanned_by=3); return 'scanned'
    result = race(cancel, scan)
    assert result in [['cancelled', 'rejected'], ['rejected', 'scanned']]
    with Session(engine) as db:
        assert db.scalar(select(func.count(Checkin.id))) + db.scalar(select(func.count(BookingCancellation.id))) == 1


def test_concurrent_transfer_only_one_recipient_and_qr_owner(database):
    engine, _ = database
    with Session(engine) as db:
        one = transfer.preview(db, 1, 1, 'policy-2@example.com')
        two = transfer.preview(db, 1, 1, 'policy-3@example.com')
        qr = access_service.AccessService(db).get_today_access(user_id=1)['qr_token']
    def execute(value, key):
        with Session(engine) as db:
            transfer.confirm(db, 1, 1, value['confirmation_token'], key); return 'transferred'
    assert sorted(race(lambda: execute(one, 'first-request'), lambda: execute(two, 'second-request'))) == ['rejected', 'transferred']
    with Session(engine) as db:
        assert db.scalar(select(func.count(MembershipTransfer.id))) == 1
        m = db.get(UserMembership, 1)
        assert m.user_id in (2, 3)
        with pytest.raises(HTTPException): access_service.AccessService(db).validate_checkin(gym_id=1, qr_token=qr)
        assert access_service.AccessService(db).get_today_access(user_id=m.user_id)['status'] == 'ACTIVE'


def test_transfer_and_scan_preserve_consumed_day(database):
    engine, _ = database
    with Session(engine) as db:
        value = transfer.preview(db, 1, 1, 'policy-2@example.com')
        qr = access_service.AccessService(db).get_today_access(user_id=1)['qr_token']
    def execute():
        with Session(engine) as db: transfer.confirm(db, 1, 1, value['confirmation_token'], 'scan-transfer'); return 'transferred'
    def scan():
        with Session(engine) as db: access_service.AccessService(db).validate_checkin(gym_id=1, qr_token=qr, scanned_by=3); return 'scanned'
    result = race(execute, scan)
    assert result[0] == 'transferred'
    with Session(engine) as db:
        assert access_service.AccessService(db).get_today_access(user_id=2)['status'] == ('USED' if result[1] == 'scanned' else 'ACTIVE')
        assert db.scalar(select(func.count(MembershipTransfer.id))) == 1


def test_mysql_upgrade_downgrade_preserves_original_records_and_refuses_audit_loss(database, monkeypatch):
    engine, _ = database
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/b24c5ef78046_customer_policies.py'
    spec = spec_from_file_location('policy_migration', path); migration = module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        migration.downgrade(); migration.upgrade()
        assert connection.scalar(text('SELECT COUNT(*) FROM user_memberships')) == 1
        assert connection.scalar(text('SELECT COUNT(*) FROM bookings')) == 1
    with Session(engine) as db: cancellation.cancel(db, booking_id=1, actor_id=1, customer_id=1)
    with engine.begin() as connection:
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError, match='audit'): migration.downgrade()
        assert connection.scalar(text('SELECT COUNT(*) FROM booking_cancellations')) == 1