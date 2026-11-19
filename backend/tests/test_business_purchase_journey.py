"""Real API -> disposable MySQL -> access -> both business dashboards.

Provider responses are mocked; no external payments or financial activation.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.access import Checkin
from app.models.membership import UserMembership
from app.models.wallet import WalletAccount, WalletTransaction
from app.services.admin_business import summary
from app.services.owner_dashboard_service import OwnerDashboardService
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, balance, create, verify
from test_cashfree_payments import source_for
from test_booking_access_qr import NOW, scan


@pytest.mark.parametrize('kind', ['BOOKING', 'SINGLE_GYM', 'MULTI_GYM'])
def test_verified_purchase_to_admission_and_business_reports(api, kind, monkeypatch):
    from app.routers.customer_access import router
    from app.core.config import settings
    from app.services import admin_business
    from app.core.time import stored_instant
    api[0].app.include_router(router, prefix='/api/v1')
    balance(api, 40)
    # Both fixture providers expose the same quote contract except its label.
    if kind == 'SINGLE_GYM':
        quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
        source = {'kind': kind, 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']}
    else:
        source = source_for(api, kind)
    response = create(api, {**source, 'use_wallet': True})
    assert response.status_code == 200, response.text
    record = response.json()
    entity = api[3].pay(record)
    paid = verify(api, record, entity)
    assert paid.status_code == 200 and paid.json()['status'] == 'PAID'
    assert verify(api, record, entity).json()['status'] == 'PAID'
    if kind == 'BOOKING':
        booking_id = source['booking_id']
        passes = api[0].post(f'/api/v1/bookings/{booking_id}/qr', headers=api[1][1]).json()['passes']
        token = passes[0]['qr_token']
    else:
        qr = api[0].get('/api/v1/customer/access/today', headers=api[1][1])
        assert qr.status_code == 200 and qr.json()['status'] == 'ACTIVE', qr.text
        token = qr.json()['qr_token']
    assert scan(api[:3], token)['success'] is True
    assert scan(api[:3], token)['success'] is False
    monkeypatch.setattr(admin_business, 'utcnow', lambda: NOW)
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(Checkin.id)).where(Checkin.status == 'SUCCESS')) == 1
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == 0
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.direction == 'OUT')) == 1
        if kind != 'BOOKING':
            member = db.scalar(select(UserMembership))
            assert member.status == 'ACTIVE' and member.payment_status == 'PAID'
            assert member.start_at <= stored_instant(NOW) < member.end_at
        data = summary(db, date_from=NOW.date(), date_to=NOW.date(), mode='test')
        owner = OwnerDashboardService(db).summary(owner_user_id=2, gym_id=1, date_from=NOW.date(), date_to=NOW.date())
        key = {'BOOKING': 'individual', 'SINGLE_GYM': 'single_gym', 'MULTI_GYM': 'multi_gym'}[kind]
        assert data['visits'][key] == data['overall']['visits'] == owner['visits']['total'] == 1
        # Gates remain off: no authoritative capture evidence is fabricated.
        assert data['collections']['total'] is None
        assert data['collections']['fitigo_commission'] is None
        assert data['visits']['no_shows'] == 0
        assert owner['revenue']['multi_gym_allocation'] == 'NOT_AVAILABLE'
        assert all(not getattr(settings, flag) for flag in ('source_evidence_enabled',
            'marketplace_allocations_enabled', 'marketplace_live_allocations_enabled', 'marketplace_payouts_enabled'))