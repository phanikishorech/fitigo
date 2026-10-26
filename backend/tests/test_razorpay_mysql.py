"""Real row-locking tests in an automatically dropped, isolated MySQL database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.main import app  # register models only
from app.database.base import Base
from app.database.session import engine as application_engine
from app.core.config import settings
from app.models.auth import User
from app.models.gym import Gym
from app.models.membership import GymMembershipPlan, UserMembership
from app.models.payment_checkout import PaymentCheckout
from app.schemas.payment_checkout import CheckoutCreate
from app.services import payment_checkout_service
from app.services.membership_wallet_service import single_terms, quote_key
from test_razorpay_payments import FakeGateway

pytestmark = pytest.mark.skipif(os.getenv('FITIGO_MYSQL_PAYMENT_TESTS') != '1', reason='Isolated MySQL test is opt-in')


@pytest.fixture(params=['razorpay', 'cashfree'])
def database(monkeypatch, request):
    assert application_engine is not None and application_engine.url.host in ('localhost', '127.0.0.1', '::1')
    assert settings.environment == 'development'
    name = 'fitigo_payment_test_' + uuid4().hex[:12]
    control = create_engine(application_engine.url.set(database=None), isolation_level='AUTOCOMMIT')
    engine = None
    created = False
    try:
        with control.connect() as db:
            db.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
        created = True
        engine = create_engine(application_engine.url.set(database=name), pool_pre_ping=True)
        Base.metadata.create_all(engine)
        monkeypatch.setattr(settings, 'payment_gateway', None)
        monkeypatch.setattr(settings, 'payment_env', None)
        monkeypatch.setattr(settings, 'razorpay_enabled', True)
        monkeypatch.setattr(settings, 'payment_mode', 'test')
        monkeypatch.setattr(settings, 'razorpay_key_id', 'rzp_test_fixture')
        monkeypatch.setattr(settings, 'razorpay_key_secret', SecretStr('fixture-key-secret'))
        monkeypatch.setattr(settings, 'razorpay_webhook_secret', SecretStr('fixture-webhook-secret'))
        gateway = FakeGateway()
        monkeypatch.setattr('app.services.razorpay_provider.RazorpayGateway', lambda: gateway)
        with Session(engine) as db:
            user = User(email='payment-test@example.test', password_hash='unused', status='ACTIVE')
            db.add(user); db.flush()
            gym = Gym(owner_user_id=user.id, name='Payment test', status='APPROVED', is_active=True)
            db.add(gym); db.flush()
            plan = GymMembershipPlan(gym_id=gym.id, name='Test plan', duration_days=30, price=Decimal('100'))
            db.add(plan); db.flush()
            source = CheckoutCreate(kind='SINGLE_GYM', gym_id=gym.id, plan_id=plan.id, accepted_quote=quote_key(single_terms(db, gym.id, plan.id)))
            uid = user.id
            db.commit()
        if request.param == 'cashfree':
            import httpx
            from test_cashfree_payments import CashfreeHTTP
            monkeypatch.setattr(settings, 'payment_gateway', 'cashfree')
            monkeypatch.setattr(settings, 'cashfree_client_id', 'fixture-cashfree-id')
            monkeypatch.setattr(settings, 'cashfree_client_secret', SecretStr('fixture-cashfree-secret'))
            with Session(engine) as db:
                db.get(User, uid).phone = '9999999999'
                db.commit()
            gateway = CashfreeHTTP()
            real_client = httpx.Client
            monkeypatch.setattr('app.services.cashfree_provider.httpx.Client',
                lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(gateway)))
        yield engine, gateway, uid, source
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with control.connect() as db:
                db.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


def test_concurrent_new_keys_create_one_order_and_capture_activates_once(database):
    engine, gateway, uid, source = database
    barrier = Barrier(2)
    def create(key):
        with Session(engine, autoflush=False) as db:
            barrier.wait(timeout=10)
            return payment_checkout_service.PaymentCheckoutService(db).create(uid, source, key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(create, ['concurrent-key-1', 'concurrent-key-2']))
    assert first['id'] == second['id'] and gateway.creations == 1
    gateway.pay(first)
    barrier = Barrier(2)
    def reconcile(_):
        with Session(engine, autoflush=False) as db:
            barrier.wait(timeout=10)
            return payment_checkout_service.PaymentCheckoutService(db).reconcile(first['id'], uid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reconcile, range(2)))
    assert all(row['status'] == 'PAID' for row in results)
    with Session(engine) as db:
        assert db.scalar(select(func.count(PaymentCheckout.id))) == 1
        assert db.scalar(select(func.count(UserMembership.id))) == 1