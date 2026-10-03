"""Opt-in concurrency verification in an isolated, uniquely named local MySQL database.

FITIGO_MYSQL_WALLET_TESTS=1 enables this suite. Application data is never written.
The temporary test database is removed only if this fixture created it.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(os.getenv('FITIGO_MYSQL_WALLET_TESTS') != '1', reason='Isolated MySQL test database is opt-in')


@pytest.fixture
def mysql_wallet():
    from app.main import app  # register existing models, no requests or schema mutation
    from app.core.config import settings
    from app.database.session import engine as application_engine
    from app.database.base import Base
    from app.models.auth import User
    from app.models.gym import Gym
    from app.models.platform_membership import PlatformMembershipPlan
    from app.models.wallet import WalletAccount
    assert settings.environment == 'development'
    assert application_engine.url.host in ('localhost','127.0.0.1','::1')
    name = 'fitigo_wallet_test_' + uuid4().hex[:12]
    control = create_engine(application_engine.url.set(database=None), isolation_level='AUTOCOMMIT')
    test_engine = None
    created = False
    try:
        with control.connect() as connection:
            connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
            created = True
        test_engine = create_engine(application_engine.url.set(database=name), pool_pre_ping=True)
        tables = [Base.metadata.tables[n] for n in ('users','gyms','gym_membership_plans','wallet_accounts','wallet_transactions','platform_membership_plans','platform_membership_offers','platform_membership_audit','user_memberships','platform_membership_orders')]
        Base.metadata.create_all(test_engine, tables=tables)
        with Session(test_engine) as db:
            user=User(email='isolated-mysql@example.test',password_hash='unused',status='ACTIVE')
            db.add(user);db.flush()
            db.add(Gym(owner_user_id=user.id,name='Isolated partner',status='APPROVED',is_active=True,multi_gym_enabled=True))
            db.add(WalletAccount(user_id=user.id,balance=Decimal('5000.00'),currency='INR'))
            plan=PlatformMembershipPlan(code='isolated',name='Isolated plan',duration_value=1,duration_unit='MONTH',base_price=Decimal('1200.00'),currency='INR',benefits=[],display_order=1,is_active=True)
            db.add(plan);db.commit()
            yield test_engine,user.id,plan.id
    finally:
        if test_engine is not None:
            test_engine.dispose()
        if created:
            with control.connect() as connection:
                connection.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


@pytest.mark.parametrize('same_order',[True,False])
def test_concurrent_payments_debit_once(mysql_wallet,same_order):
    from app.services.platform_membership_service import PlatformMembershipService
    from app.models.wallet import WalletAccount, WalletTransaction
    from app.models.membership import UserMembership
    engine,user_id,plan_id=mysql_wallet
    with Session(engine) as db:
        service=PlatformMembershipService(db)
        first=service.create_order(user_id=user_id,plan_id=plan_id,idempotency_key='mysql-order-001')
        second=first if same_order else service.create_order(user_id=user_id,plan_id=plan_id,idempotency_key='mysql-order-002')
    barrier=Barrier(2)
    def pay(record):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                result=PlatformMembershipService(db).pay_wallet(record.id,user_id=user_id,accepted_quote=record.quote_token)
                return result.membership_id
            except HTTPException as error:
                return error.detail['code']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(pay,[first,second]))
    with Session(engine) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==user_id))==Decimal('3800.00')
        assert db.scalar(select(func.count(WalletTransaction.id)))==1
        assert db.scalar(select(func.count(UserMembership.id)))==1
    if same_order:
        assert results[0]==results[1] and isinstance(results[0],int)
    else:
        assert 'MEMBERSHIP_ALREADY_ACTIVE' in results
        assert sum(isinstance(result,int) for result in results)==1