"""Test-credit checkout in disposable SQLite. Never debits real accounts."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from test_platform_memberships import api, create, offer
from app.core.config import settings
from app.models.gym import Gym
from app.models.membership import UserMembership, GymMembershipPlan
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.platform_membership import PlatformMembershipOrder
from app.services.access_service import AccessService
from app.services.membership_entitlement import covers, active_memberships, included_ids
from app.services.membership_wallet_service import expiry


@pytest.fixture
def funded(api, monkeypatch):
    monkeypatch.setattr(settings, 'environment', 'development')
    client, headers, engine = api
    with Session(engine) as db:
        db.add(WalletAccount(user_id=2, balance=Decimal('5000.00'), currency='INR'))
        partner = Gym(owner_user_id=3, name='Test partner', status='APPROVED', is_active=True, multi_gym_enabled=True)
        other = Gym(owner_user_id=3, name='Test nonpartner', status='APPROVED', is_active=True, multi_gym_enabled=False)
        db.add_all([partner, other]); db.flush()
        db.add(GymMembershipPlan(gym_id=partner.id, name='Test Single', duration_days=30, price=Decimal('600.00'), currency='INR', is_active=True))
        db.commit()
    return api


def order(api, plan_id, key='wallet-order-001'):
    client, headers, _ = api
    response = client.post('/api/v1/memberships/orders', json={'plan_id':plan_id}, headers={**headers[1], 'Idempotency-Key':key})
    assert response.status_code == 200, response.text
    return response.json()


def pay(api, record, quote=None, identity=1, **extra):
    client, headers, _ = api
    return client.post(f"/api/v1/memberships/orders/{record['id']}/pay-wallet", headers=headers[identity], json={'accepted_quote':quote or record['quote_token'], **extra})


def balances(api):
    with Session(api[2]) as db:
        return db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id==2)), db.scalar(select(func.count(WalletTransaction.id))), db.scalar(select(func.count(UserMembership.id)))


def test_multi_wallet_atomic_activation_idempotency_and_daily_qr(funded):
    plan = create(funded)
    record = order(funded, plan['id'])
    assert record['payment_available'] is True
    result = pay(funded, record)
    assert result.status_code == 200, result.text
    paid = result.json()
    assert paid['payment_status'] == 'PAID' and paid['membership_id']
    assert balances(funded) == (Decimal('3800.00'), 1, 1)
    assert pay(funded, record).json()['membership_id'] == paid['membership_id']
    assert balances(funded) == (Decimal('3800.00'), 1, 1)
    client, headers, engine = funded
    mine = client.get('/api/v1/memberships/me', headers=headers[1])
    assert mine.status_code == 200, mine.text
    membership = mine.json()[0]
    assert membership['membership_type'] == 'MULTI_GYM' and membership['gym_id'] is None
    assert membership['terms_snapshot']['name'] == plan['name']
    summary = client.get('/api/v1/profile/membership', headers=headers[1])
    assert summary.status_code == 200, summary.text
    assert summary.json()['membership_scope'] == 'MULTI_GYM'
    assert summary.json()['plan_name'] == plan['name']
    assert summary.json()['pause_days_remaining'] == 0
    with Session(engine) as db:
        svc = AccessService(db)
        token = svc.get_today_access(user_id=2)
        assert token['status'] == 'ACTIVE' and token['access_type'] == 'MULTI_GYM'
        assert included_ids(db, 2, datetime.now(timezone.utc)) == {1}
        with pytest.raises(HTTPException): svc.validate_checkin(gym_id=2, qr_token=token['qr_token'])
        assert svc.validate_checkin(gym_id=1, qr_token=token['qr_token'])['success']
        assert svc.get_today_access(user_id=2)['status'] == 'USED'
        with pytest.raises(HTTPException): svc.validate_checkin(gym_id=1, qr_token=token['qr_token'])


def test_insufficient_balance_and_failed_insert_leave_no_partial_payment(funded):
    plan = create(funded, {'base_price':'6000.00'})
    record = order(funded, plan['id'])
    response = pay(funded, record)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'INSUFFICIENT_WALLET_BALANCE'
    assert balances(funded) == (Decimal('5000.00'), 0, 0)
    cheaper = create(funded, {'code':'cheaper'})
    record = order(funded, cheaper['id'], 'rollback-order-001')
    def reject_insert(mapper, connection, target): raise RuntimeError('test activation failure')
    event.listen(UserMembership, 'before_insert', reject_insert)
    try:
        with pytest.raises(RuntimeError, match='test activation failure'): pay(funded, record)
    finally: event.remove(UserMembership, 'before_insert', reject_insert)
    assert balances(funded) == (Decimal('5000.00'), 0, 0)
    assert pay(funded, record).status_code == 200
    assert balances(funded) == (Decimal('3800.00'), 1, 1)


def test_changed_offer_requires_new_acceptance_and_order_is_owner_only(funded):
    plan = create(funded); record = order(funded, plan['id'])
    assert pay(funded, record, identity=3).status_code == 404
    assert pay(funded, record, price='1.00').status_code == 422
    assert offer(funded, plan).status_code == 200
    response = pay(funded, record)
    assert response.status_code == 409 and response.json()['detail']['code'] == 'MEMBERSHIP_PRICE_CHANGED'
    assert balances(funded) == (Decimal('5000.00'), 0, 0)
    current = funded[0].get(f"/api/v1/memberships/orders/{record['id']}", headers=funded[1][1]).json()
    assert pay(funded, current).status_code == 200
    assert balances(funded) == (Decimal('3925.00'), 1, 1)
    duplicate = order(funded, plan['id'], 'different-order-001')
    response = pay(funded, duplicate)
    assert response.status_code == 409 and response.json()['detail']['code'] == 'MEMBERSHIP_ALREADY_ACTIVE'
    assert balances(funded) == (Decimal('3925.00'), 1, 1)


def test_partner_required_and_revocation_blocks_previously_minted_qr(funded):
    plan = create(funded); record = order(funded, plan['id'])
    client, headers, engine = funded
    endpoint = '/api/v1/admin/gyms/1/multi-gym-participation'
    assert client.put(endpoint, headers=headers[1], json={'enabled':False}).status_code == 403
    assert client.put(endpoint, headers=headers[0], json={'enabled':False}).status_code == 200
    assert pay(funded, record).json()['detail']['code'] == 'NO_ELIGIBLE_PARTNER_GYMS'
    assert balances(funded) == (Decimal('5000.00'), 0, 0)
    client.put(endpoint, headers=headers[0], json={'enabled':True})
    assert pay(funded, record).status_code == 200
    with Session(engine) as db:
        token = AccessService(db).get_today_access(user_id=2)['qr_token']
    client.put(endpoint, headers=headers[0], json={'enabled':False})
    with Session(engine) as db:
        with pytest.raises(HTTPException): AccessService(db).validate_checkin(gym_id=1, qr_token=token)


def test_single_wallet_replaces_dummy_and_enforces_price_and_retry(funded):
    client, headers, engine = funded
    qurl='/api/v1/memberships/gyms/1/plans/1/wallet-quote'
    url='/api/v1/memberships/gyms/1/purchase'
    quote=client.get(qurl, headers=headers[1]).json()
    auth={**headers[1], 'Idempotency-Key':'single-test-001'}
    assert client.post(url, headers=auth, json={'plan_id':1}).status_code == 422
    with Session(engine) as db:
        db.get(GymMembershipPlan,1).price=Decimal('650.00'); db.commit()
    body={'plan_id':1,'accepted_quote':quote['quote_token']}
    assert client.post(url, headers=auth, json=body).json()['detail']['code']=='MEMBERSHIP_PRICE_CHANGED'
    body['accepted_quote']=client.get(qurl, headers=headers[1]).json()['quote_token']
    response=client.post(url, headers=auth, json=body)
    assert response.status_code==200, response.text
    assert response.json()['payment_provider']=='WALLET'
    assert client.post(url, headers=auth, json=body).json()['id']==response.json()['id']
    assert balances(funded)==(Decimal('4350.00'),1,1)
    assert client.post(url, headers={**headers[1], 'Idempotency-Key':'single-test-002'}, json=body).json()['detail']['code']=='MEMBERSHIP_ALREADY_ACTIVE'
    with Session(engine) as db:
        active=active_memberships(db,2,datetime.now(timezone.utc))
        assert covers(active,db.get(Gym,1)) and not covers(active,db.get(Gym,2))


def test_production_and_external_payment_cannot_be_enabled(funded, monkeypatch):
    plan=create(funded); record=order(funded,plan['id'])
    client,headers,_=funded
    assert client.post(f"/api/v1/memberships/orders/{record['id']}/payment-session", headers=headers[1]).status_code==409
    monkeypatch.setattr(settings,'environment','production')
    assert pay(funded,record).json()['detail']['code']=='WALLET_MVP_DISABLED'
    assert client.get('/api/v1/memberships/plans').json()['checkout_available'] is False
    assert client.post('/api/v1/wallet/topup',headers=headers[1],json={'amount':'100.00','currency':'INR'}).status_code==403
    assert balances(funded)==(Decimal('5000.00'),0,0)


def test_duration_month_end_and_leap_year():
    assert expiry(datetime(2026,1,31,12),1,'MONTH')==datetime(2026,2,28,12)
    assert expiry(datetime(2024,2,29,12),1,'YEAR')==datetime(2025,2,28,12)
    assert expiry(datetime(2026,1,31,12),30,'DAY')==datetime(2026,3,2,12)


def test_paid_receipt_retains_charged_price_after_catalog_edit(funded):
    plan=create(funded); record=order(funded,plan['id'])
    paid=pay(funded,record).json()
    assert offer(funded,plan).status_code==200
    receipt=funded[0].get(f"/api/v1/memberships/orders/{record['id']}",headers=funded[1][1]).json()
    assert receipt['current_plan']['final_price']==paid['plan']['final_price']=='1200.00'
    assert receipt['requires_review'] is False and receipt['payment_available'] is False
    assert pay(funded,record).status_code==200
    assert balances(funded)==(Decimal('3800.00'),1,1)


def test_currency_mismatch_and_unavailable_plan_do_not_debit(funded):
    client, headers, engine=funded
    plan=create(funded); record=order(funded,plan['id'])
    with Session(engine) as db:
        db.scalars(select(WalletAccount).where(WalletAccount.user_id==2)).one().currency='USD'
        db.commit()
    assert pay(funded,record).json()['detail']['code']=='WALLET_CURRENCY_MISMATCH'
    assert balances(funded)==(Decimal('5000.00'),0,0)
    with Session(engine) as db:
        from app.models.platform_membership import PlatformMembershipPlan
        db.get(PlatformMembershipPlan,plan['id']).is_active=False
        db.commit()
    assert pay(funded,record).status_code==404
    assert balances(funded)==(Decimal('5000.00'),0,0)


def test_test_credit_topup_requires_identity_and_single_purchase_is_gated(funded, monkeypatch):
    client, headers, _=funded
    assert client.post('/api/v1/wallet/topup',json={'amount':'10.00','currency':'INR'}).status_code==401
    assert client.get('/api/v1/wallet/balance').status_code==401
    quote=client.get('/api/v1/memberships/gyms/1/plans/1/wallet-quote',headers=headers[1]).json()
    monkeypatch.setattr(settings,'environment','production')
    response=client.post('/api/v1/memberships/gyms/1/purchase',headers={**headers[1],'Idempotency-Key':'production-single-001'},json={'plan_id':1,'accepted_quote':quote['quote_token']})
    assert response.status_code==403
    assert response.json()['detail']['code']=='WALLET_MVP_DISABLED'
    assert balances(funded)==(Decimal('5000.00'),0,0)