"""Same-order recovery; disposable MySQL and mocked Razorpay only."""
from datetime import timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, balance, create
from test_membership_checkout_recovery import source, refresh
from app.models.checkout_funding import CheckoutFunding
from app.models.wallet import WalletTransaction
from app.models.payment_checkout import PaymentCheckout
import pytest


def expired(api):
    if hasattr(api[3], 'termination_state'):
        pytest.skip('Razorpay same-order recovery only')
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    api[3].pay(record, 'failed')
    with Session(api[2]) as db:
        db.get(CheckoutFunding, record['id']).expires_at -= timedelta(days=365)
        db.commit()
    return payload, record


def resume(api, record, user=1):
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/resume-membership", headers=api[1][user])


def test_expired_original_resumes_without_releasing_or_creating(api):
    payload, record = expired(api)
    current = refresh(api, record).json()
    assert current['can_resume_reserved_membership'] and not current['can_pay']
    assert resume(api, record, 4).status_code == 404
    for _ in range(2):
        response = resume(api, record)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['can_pay'] and result['wallet_status'] == 'HELD'
        for key in ['id', 'gateway_order_id', 'total_amount', 'wallet_amount', 'gateway_amount']:
            assert result[key] == record[key]
    assert api[3].creations == 1
    assert create(api, source(api, 'SINGLE_GYM'), 'blocked-switch-plan').status_code == 409
    same = create(api, payload, 'same-plan-retry')
    assert same.status_code == 200 and same.json()['id'] == record['id']
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0
        assert db.get(CheckoutFunding, record['id']).resolved_at is None


@pytest.mark.parametrize('state', ['processing', 'paid', 'incomplete', 'cancel_requested'])
def test_fresh_provider_evidence_prevents_unsafe_resume(api, state):
    _, record = expired(api)
    assert refresh(api, record).json()['can_resume_reserved_membership']
    if state == 'processing': api[3].pay(record, 'authorized')
    if state == 'paid': api[3].pay(record)
    if state == 'incomplete': api[3].orders[record['gateway_order_id']]['attempts'] += 1
    if state == 'cancel_requested':
        with Session(api[2]) as db:
            row = db.get(PaymentCheckout, record['id'])
            row.snapshot = {**row.snapshot, 'cancellation_requested': True}
            db.commit()
    result = resume(api, record).json()
    assert not result['can_pay'] and not result['can_resume_reserved_membership']
    assert result['wallet_status'] == ('DEBITED' if state == 'paid' else 'HELD')
    assert api[3].creations == 1