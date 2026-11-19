"""Existing API/provider adapters with mocked gateways; no real payment calls."""
from decimal import Decimal
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_razorpay_payments import api as razorpay_api, booking_api, create_booking, verify as razor_verify, webhook as razor_webhook
from test_cashfree_payments import api as cashfree_api, verify as cash_verify, webhook as cash_webhook
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.booking import Booking, Payment
from app.models.checkout_funding import CheckoutFunding, BookingFunding
from app.models.membership import UserMembership
from app.models.access import AccessQrToken
from app.models.payment_checkout import PaymentCheckout
from app.models.slot import GymSlot


@pytest.fixture(params=['razorpay', 'cashfree'])
def api(request):
    result = request.getfixturevalue(request.param + '_api')
    from app.routers.wallet import router
    result[0].app.include_router(router, prefix='/api/v1')
    with Session(result[2]) as db:
        db.get(GymSlot, 1).price = 150
        db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1)).payment_mode = 'test'
        db.commit()
    # Reuse API/clock/provider fixtures but execute every split scenario on a
    # disposable MySQL schema (SQLite does not prove financial row locking).
    from test_database_guard import disposable_name
    from app.database.session import engine as runner
    from app.database.base import Base
    from app.database.session import get_db
    from sqlalchemy import create_engine, text
    name = disposable_name()
    control = create_engine(runner.url.set(database=None), isolation_level='AUTOCOMMIT')
    with control.connect() as db: db.execute(text(f'CREATE DATABASE `{name}`'))
    engine = create_engine(runner.url.set(database=name), pool_pre_ping=True)
    try:
        Base.metadata.create_all(engine)
        with result[2].connect() as original, engine.begin() as target:
            for table in Base.metadata.sorted_tables:
                rows = original.execute(select(table)).mappings().all()
                if rows: target.execute(table.insert(), [dict(row) for row in rows])
        def database():
            with Session(engine, autoflush=False) as db: yield db
        result[0].app.dependency_overrides[get_db] = database
        yield result[0], result[1], engine, result[3]
    finally:
        engine.dispose()
        with control.connect() as db: db.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


def balance(api, amount):
    with Session(api[2]) as db:
        db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1)).balance = amount; db.commit()


def source(api, use=True, amount=None):
    result = {'kind': 'BOOKING', 'booking_id': create_booking(api)['id'], 'use_wallet': use}
    if amount is not None: result['wallet_amount'] = amount
    return result


def create(api, payload, key='split-checkout-key'):
    return api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': key}, json=payload)


def verify(api, record, entity):
    return cash_verify(api, record) if record['provider'] == 'CASHFREE' else razor_verify(api, record, entity)


@pytest.mark.parametrize('wallet,use,requested,expected', [(0,True,None,0),(40,True,None,40),(150,True,None,150),(200,True,None,150),(40,False,None,0),(40,True,'20.00',20)])
def test_authoritative_amounts_wallet_only_and_split(api, wallet, use, requested, expected):
    balance(api, wallet); payload = source(api, use, requested)
    quote = api[0].post('/api/v1/payments/quote', headers=api[1][1], json=payload)
    assert quote.status_code == 200, quote.text
    assert Decimal(quote.json()['wallet_amount']) == expected
    response = create(api, payload); assert response.status_code == 200, response.text
    record = response.json()
    assert Decimal(record['total_amount']) == 150
    assert Decimal(record['wallet_amount']) + Decimal(record['gateway_amount']) == 150
    assert Decimal(record['amount']) == 150 - expected
    if expected == 150:
        assert api[3].creations == 0 and record['status'] == 'PAID'
    else:
        assert api[3].creations == 1 and record['status'] == 'PENDING'
        assert api[0].post(f"/api/v1/bookings/{payload['booking_id']}/qr", headers=api[1][1]).status_code == 400
        entity = api[3].pay(record)
        record = verify(api, record, entity).json(); assert record['status'] == 'PAID'
        assert verify(api, record, entity).json()['status'] == 'PAID'
        webhook = cash_webhook(api, record) if record['provider'] == 'CASHFREE' else razor_webhook(api, entity)
        assert webhook.status_code == 200
    with Session(api[2]) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == wallet - expected
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction == 'OUT')) == int(expected > 0)
        assert db.get(Booking, payload['booking_id']).status == 'CONFIRMED'
        assert db.scalar(select(Payment.amount)) == 150
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1


def test_hold_protects_balance_and_duplicate_does_not_reserve_twice(api):
    balance(api,40); payload=source(api)
    response=create(api,payload);assert response.status_code==200,response.text
    record=response.json()
    again=create(api,payload);assert again.status_code==200 and again.json()['id']==record['id']
    wallet=api[0].get('/api/v1/wallet/balance',headers=api[1][1]).json()
    assert Decimal(wallet['balance'])==40 and Decimal(wallet['available_balance'])==0 and Decimal(wallet['reserved_balance'])==40
    assert create(api,{**payload,'wallet_amount':'10.00'}).status_code==409
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(CheckoutFunding.checkout_id)))==1
        assert db.scalar(select(func.count(WalletTransaction.id)))==0


def test_failed_pending_expiry_and_delayed_success(api):
    balance(api,40);record=create(api,source(api)).json()
    api[3].pay(record,'PENDING' if record['provider']=='CASHFREE' else 'authorized')
    response=api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh",headers=api[1][1])
    assert response.status_code==200 and response.json()['wallet_status']=='HELD'
    with Session(api[2]) as db:
        db.get(CheckoutFunding,record['id']).expires_at-=timedelta(days=1);db.commit()
    response=api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh",headers=api[1][1])
    assert response.json()['wallet_status']=='HELD'
    entity=api[3].pay(record)
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==0


def test_definitive_failure_releases_hold_and_late_capture_does_not_debit(api):
    balance(api,40);record=create(api,source(api)).json()
    api[3].pay(record,'FAILED' if record['provider']=='CASHFREE' else 'failed')
    response=api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh",headers=api[1][1])
    assert response.status_code==200,response.text
    closed = record['provider'] == 'CASHFREE'
    assert response.json()['wallet_status']==('RELEASED' if closed else 'HELD')
    entity=api[3].pay(record)
    response=verify(api,record,entity)
    assert response.json()['status']==('REVIEW_REQUIRED' if closed else 'PAID')
    with Session(api[2]) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==(40 if closed else 0)
        assert db.scalar(select(func.count(WalletTransaction.id)))==(0 if closed else 1)


@pytest.mark.parametrize('wallet',[40,150])
def test_split_cancellation_credits_full_purchase_once(api,monkeypatch,wallet):
    from app.services import booking_cancellation
    from test_booking_access_qr import NOW
    monkeypatch.setattr(booking_cancellation,'utcnow',lambda:NOW.replace(hour=7))
    balance(api,wallet);payload=source(api);record=create(api,payload).json()
    if record['status']!='PAID': assert verify(api,record,api[3].pay(record)).json()['status']=='PAID'
    path=f"/api/v1/bookings/{payload['booking_id']}/cancel"
    response=api[0].post(path,headers=api[1][1],json={});assert response.status_code==200,response.text
    assert Decimal(response.json()['cancellation']['wallet_credit_amount'])==150
    assert api[0].post(path,headers=api[1][1],json={}).status_code==409
    with Session(api[2]) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==150
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction=='OUT'))==1


@pytest.mark.parametrize('kind',['SINGLE_GYM','MULTI_GYM'])
def test_membership_activation_uses_total_and_debits_once(api,kind):
    from test_cashfree_payments import source_for
    balance(api,40)
    if kind == 'SINGLE_GYM':
        terms = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
        payload = {'kind': kind, 'gym_id': 1, 'plan_id': 1, 'accepted_quote': terms['quote_token'], 'use_wallet': True}
    else: payload={**source_for(api,kind),'use_wallet':True}
    quote=api[0].post('/api/v1/payments/quote',headers=api[1][1],json=payload)
    assert quote.status_code==200,quote.text
    response=create(api,payload);assert response.status_code==200,response.text
    record=response.json();entity=api[3].pay(record)
    result=verify(api,record,entity);assert result.json()['status']=='PAID',result.text
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        m=db.scalar(select(UserMembership));assert m.paid_amount==Decimal(record['total_amount'])
        assert m.wallet_transaction_id is not None and m.gateway_checkout_id==record['id']
        assert db.scalar(select(func.count(UserMembership.id)))==1


def test_reject_tampered_amounts_and_wallet_recharge_loop(api):
    payload=source(api)
    for changes in [{'wallet_balance':'999'},{'gateway_amount':'1'},{'wallet_amount':'1.001'},{'wallet_amount':'-1'}]:
        assert create(api,{**payload,**changes}).status_code==422
    assert create(api,{'kind':'WALLET_TOPUP','amount':'100','use_wallet':True}).status_code==422


def test_fulfillment_failure_retries_without_second_gateway_order_or_debit(api,monkeypatch):
    from app.services.booking_access_service import BookingAccessService
    from fastapi import HTTPException
    balance(api,40); record=create(api,source(api)).json(); entity=api[3].pay(record)
    original=BookingAccessService.ensure_records
    def fail(*args): raise HTTPException(409,'Synthetic recoverable fulfillment failure')
    monkeypatch.setattr(BookingAccessService,'ensure_records',fail)
    response=verify(api,record,entity);assert response.json()['status']=='REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.get(CheckoutFunding,record['id']).state=='HELD'
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==40
        assert db.scalar(select(func.count(WalletTransaction.id)))==0
        assert db.scalar(select(Booking.status))=='PENDING_PAYMENT'
    monkeypatch.setattr(BookingAccessService,'ensure_records',original)
    assert verify(api,record,entity).json()['status']=='PAID'
    assert api[3].creations==1
    with Session(api[2]) as db:assert db.scalar(select(func.count(WalletTransaction.id)))==1


@pytest.mark.parametrize('kind',['gym','class'])
def test_cart_quote_is_read_only_and_split_class_capacity_confirms_once(api,kind):
    from test_booking_access_qr import NOW
    from app.models.gym import Gym
    from app.models.cart import CartItem
    from app.models.class_booking import GymClass,ClassSession
    from datetime import time
    balance(api,40)
    if kind=='gym':
        payload={'gym_id':1,'booking_date':str(NOW.date()),'preferred_start_time':'13:00','member_count':1,'visitor_names':['Guest']}
    else:
        with Session(api[2]) as db:
            db.get(Gym,1).has_classes=True
            group=GymClass(gym_id=1,class_name='Split class',is_active=True);db.add(group);db.flush()
            session=ClassSession(gym_class_id=group.id,session_date=NOW.date(),start_time=time(13),end_time=time(14),maximum_capacity=10,booked_capacity=0,price_per_person=150,status='AVAILABLE')
            db.add(session);db.commit();sid=session.id
        payload={'gym_id':1,'booking_date':str(NOW.date()),'class_session_id':sid,'member_count':1,'visitor_names':['Guest']}
    response=api[0].post('/api/v1/cart/items/'+kind,headers=api[1][1],json=payload)
    assert response.status_code==200,response.text
    item=response.json();selection={'kind':'CART','cart_item_ids':[item['id']],'use_wallet':True}
    quote=api[0].post('/api/v1/payments/quote',headers=api[1][1],json=selection);assert quote.status_code==200,quote.text
    with Session(api[2]) as db:
        assert db.get(CartItem,item['id']).status=='ACTIVE'
        assert db.scalar(select(func.count(PaymentCheckout.id)))==0
        assert db.scalar(select(func.count(Booking.id)))==0
    response=create(api,selection);assert response.status_code==200,response.text
    record=response.json();entity=api[3].pay(record)
    assert verify(api,record,entity).json()['status']=='PAID'
    assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        allocation=db.scalar(select(BookingFunding));assert allocation.wallet_amount==40
        assert allocation.wallet_amount+allocation.gateway_amount==allocation.total_amount
        if kind=='class':assert db.get(ClassSession,sid).booked_capacity==1


def test_mode_currency_and_minimum_remainder_validation(api):
    balance(api,40);payload=source(api)
    with Session(api[2]) as db:db.scalar(select(WalletAccount)).payment_mode='live';db.commit()
    assert create(api,payload).status_code==409
    with Session(api[2]) as db:db.scalar(select(WalletAccount)).payment_mode='test';db.scalar(select(WalletAccount)).currency='USD';db.commit()
    assert create(api,payload).status_code==409
    with Session(api[2]) as db:db.scalar(select(WalletAccount)).currency='INR';db.scalar(select(WalletAccount)).balance=150;db.commit()
    assert create(api,{**payload,'wallet_amount':'149.50'}).status_code==409


def test_gateway_reporting_counts_remainder_not_purchase(api):
    from app.services.admin_revenue import gateway_booking_amount,eligible_admin_payment
    from app.core.config import settings
    balance(api,40);payload=source(api);record=create(api,payload).json()
    assert verify(api,record,api[3].pay(record)).json()['status']=='PAID'
    with Session(api[2]) as db:
        total=db.scalar(select(func.sum(gateway_booking_amount(db))).select_from(Payment).join(Booking,Booking.id==Payment.booking_id).where(eligible_admin_payment()))
        assert total==110
        assert db.scalar(select(BookingFunding.total_amount))==150
        checkout=db.get(PaymentCheckout,record['id']);checkout.mode='live';db.commit()
        assert db.scalar(select(func.coalesce(func.sum(gateway_booking_amount(db)),0)).select_from(Payment).join(Booking,Booking.id==Payment.booking_id).where(eligible_admin_payment()))==0


def test_expiry_worker_reconciles_unpaid_order_and_releases_once(api):
    from app.services.wallet_hold_recovery import recover_due
    balance(api,40);record=create(api,source(api)).json()
    with Session(api[2]) as db:
        db.get(CheckoutFunding,record['id']).expires_at-=timedelta(days=1);db.commit()
        closed = record['provider'] == 'CASHFREE'
        result=recover_due(db);assert result=={'checked':1,'unresolved':0 if closed else 1}
        assert db.get(CheckoutFunding,record['id']).state==('RELEASED' if closed else 'HELD')
        assert recover_due(db)==({'checked':0,'unresolved':0} if closed else {'checked':1,'unresolved':1})
        if not closed:
            checkout = db.get(PaymentCheckout,record['id'])
            assert checkout.failure_code == 'WALLET_HOLD_REQUIRES_PROVIDER_CLOSURE'
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==40
        assert db.scalar(select(func.count(WalletTransaction.id)))==0


def test_creation_timeout_preserves_hold_and_recovers_original_order(api):
    balance(api,40);payload=source(api)
    if hasattr(api[3], 'timeout'): api[3].timeout=True
    else: api[3].timeout_after_create=True
    response=create(api,payload);assert response.status_code==503,response.text
    with Session(api[2]) as db:
        checkout=db.scalar(select(PaymentCheckout));cid=checkout.id
        assert checkout.status=='CREATING'
        assert db.get(CheckoutFunding,cid).state=='HELD'
    if hasattr(api[3], 'timeout'): api[3].timeout=False
    else: api[3].timeout_after_create=False
    response=create(api,payload);assert response.status_code==200,response.text
    assert response.json()['id']==cid and api[3].creations==1
    entity=api[3].pay(response.json())
    assert verify(api,response.json(),entity).json()['status']=='PAID'


def test_wallet_ledger_reconciles_without_reservation_charge(api):
    from sqlalchemy import case
    balance(api,40)
    with Session(api[2]) as db:
        account=db.scalar(select(WalletAccount).where(WalletAccount.user_id==1))
        db.add(WalletTransaction(account_id=account.id,user_id=1,direction='IN',txn_type='TOPUP',amount=40,currency='INR',reference='fixture-opening-credit'));db.commit()
    record=create(api,source(api)).json()
    with Session(api[2]) as db:assert db.scalar(select(func.count(WalletTransaction.id)))==1
    entity=api[3].pay(record);assert verify(api,record,entity).json()['status']=='PAID'
    with Session(api[2]) as db:
        ledger=db.scalar(select(func.sum(case((WalletTransaction.direction=='IN',WalletTransaction.amount),else_=-WalletTransaction.amount))))
        assert ledger==db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==1))==0


def test_funding_migration_preserves_existing_data_and_refuses_loss(api,monkeypatch):
    from pathlib import Path
    from importlib.util import spec_from_file_location,module_from_spec
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    path=Path(__file__).resolve().parents[1]/'alembic/versions/c35d6fa89157_checkout_funding.py'
    spec=spec_from_file_location('funding_migration',path);migration=module_from_spec(spec);spec.loader.exec_module(migration)
    balance(api,40)
    with api[2].begin() as connection:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        migration.downgrade();migration.upgrade()
        assert connection.scalar(text('SELECT balance FROM wallet_accounts WHERE user_id=1'))==40
    record=create(api,source(api)).json()
    with api[2].begin() as connection:
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError,match='evidence'):migration.downgrade()
        assert connection.scalar(text('SELECT COUNT(*) FROM checkout_funding'))==1