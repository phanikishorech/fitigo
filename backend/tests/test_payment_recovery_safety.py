"""Recovery boundaries on disposable MySQL; provider transport is mocked."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_membership_checkout_recovery import source, recover, refresh, cancel
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, balance, create
from app.models.checkout_funding import CheckoutFunding
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.membership import UserMembership
from app.services.payment_checkout_service import PaymentCheckoutService


def expire(api, record):
    with Session(api[2]) as db:
        db.get(CheckoutFunding, record['id']).expires_at -= timedelta(days=365)
        db.commit()


def test_expired_failed_order_retains_hold_without_terminal_evidence(api):
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    api[3].pay(record, 'FAILED' if record['provider'] == 'CASHFREE' else 'failed')
    if record['provider'] == 'CASHFREE': api[3].termination_state = 'TERMINATION_REQUESTED'
    expire(api, record)
    current = refresh(api, record).json()
    assert current['wallet_status'] == 'HELD' and not current['can_pay']
    assert current['recovery_status'] == ('CANCELLATION_PENDING' if record['provider'] == 'CASHFREE' else 'RESOLUTION_REQUIRED')
    assert current['can_contact_support'] and not current['replacement_safe']
    assert current['order_reference'] == payload['order_id']
    assert current['payment_reference']
    assert create(api, source(api, 'SINGLE_GYM'), 'conflicting-checkout-key').status_code == 409
    assert api[3].creations == 1
    with Session(api[2]) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == 49
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0


def test_release_boundary_rejects_unverified_local_close(api):
    balance(api, 49)
    record = create(api, source(api)).json()
    expire(api, record)
    with Session(api[2]) as db:
        service = PaymentCheckoutService(db)
        row = service.owned(record['id'], 1)
        with pytest.raises(HTTPException) as error:
            service.close_unpaid(row)
        assert error.value.status_code == 409
        db.rollback()
        assert db.get(CheckoutFunding, record['id']).state == 'HELD'


def test_concurrent_refresh_safe_closure_releases_exactly_once(api):
    if not hasattr(api[3], 'termination_state'): pytest.skip('Cashfree authoritative closure')
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    api[3].orders[record['gateway_order_id']]['order_status'] = 'TERMINATED'
    barrier = Barrier(2)
    def reconcile(_):
        with Session(api[2], autoflush=False) as db:
            barrier.wait(timeout=10)
            return PaymentCheckoutService(db).reconcile(record['id'], 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reconcile, range(2)))
    assert all(r['recovery_status'] == 'SAFELY_CLOSED' and r['wallet_status'] == 'RELEASED' for r in results)
    with Session(api[2]) as db:
        resolved = db.get(CheckoutFunding, record['id']).resolved_at
    for _ in range(2): assert cancel(api, record).json()['wallet_status'] == 'RELEASED'
    with Session(api[2]) as db:
        assert db.get(CheckoutFunding, record['id']).resolved_at == resolved
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == 49
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0
    assert recover(api, payload).json()['checkout'] is None
    fresh = create(api, payload, 'fresh-after-closure').json()
    assert fresh['id'] != record['id'] and fresh['wallet_amount'] == '49.00'


def test_expired_hold_delayed_success_duplicate_webhook_debits_once(api):
    balance(api, 49)
    record = create(api, source(api)).json()
    api[3].pay(record, 'FAILED' if record['provider'] == 'CASHFREE' else 'failed')
    with Session(api[2], autoflush=False) as db:
        assert PaymentCheckoutService(db).reconcile(record['id'], 1)['status'] == 'FAILED'
    expire(api, record)
    entity = api[3].pay(record)
    from test_cashfree_payments import webhook as cash_webhook
    from test_razorpay_payments import webhook as razor_webhook
    for _ in range(2):
        response = cash_webhook(api, record) if record['provider'] == 'CASHFREE' else razor_webhook(api, entity)
        assert response.status_code == 200, response.text
    result = refresh(api, record).json()
    assert result['recovery_status'] == 'PAID' and result['wallet_status'] == 'DEBITED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id))) == 1
        assert db.scalar(select(func.count(UserMembership.id))) == 1
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == 0


def test_incomplete_closure_evidence_preserves_processing_hold(api):
    if not hasattr(api[3], 'termination_state'): pytest.skip('Cashfree closure evidence')
    balance(api, 49)
    record = create(api, source(api)).json()
    api[3].pay(record, 'PENDING')
    assert refresh(api, record).json()['recovery_status'] == 'PROCESSING'
    api[3].orders[record['gateway_order_id']]['order_status'] = 'TERMINATED'
    api[3].attempts[record['gateway_order_id']] = []
    expire(api, record)
    current = refresh(api, record).json()
    assert current['wallet_status'] == 'HELD' and not current['replacement_safe']
    assert current['recovery_status'] == 'PROCESSING'
    assert not current['can_request_cancel']


def test_automatic_cancellation_timeout_persists_intent(api):
    if not hasattr(api[3], 'termination_state'): pytest.skip('Cashfree cancellation timeout')
    balance(api, 49)
    record = create(api, source(api)).json()
    expire(api, record)
    api[3].termination_timeout = True
    api[3].termination_state = 'TERMINATION_REQUESTED'
    assert refresh(api, record).status_code == 503
    current = api[0].get(f"/api/v1/payments/checkouts/{record['id']}", headers=api[1][1]).json()
    assert current['cancellation_requested'] and not current['can_pay']
    assert current['recovery_status'] == 'CANCELLATION_PENDING'
    assert current['wallet_status'] == 'HELD'


def test_refund_evidence_does_not_release_unresolved_wallet_hold(api):
    if record_provider(api) != 'RAZORPAY': pytest.skip('Razorpay refund evidence fixture')
    balance(api, 49)
    record = create(api, source(api)).json()
    api[3].pay(record, amount_refunded=record['amount_minor'])
    result = refresh(api, record).json()
    assert result['status'] == 'REVIEW_REQUIRED' and result['wallet_status'] == 'HELD'
    assert result['recovery_status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0


def record_provider(api):
    return 'CASHFREE' if hasattr(api[3], 'termination_state') else 'RAZORPAY'


def test_support_create_and_resolve_never_releases_reservation(api, monkeypatch):
    from app.core.config import settings
    from app.routers import support_requests
    from app.models.auth import User, UserRole, Role
    from app.models.support import SupportTicket
    from app.schemas.support import SupportStatusChange
    from app.services.support_service import SupportService
    monkeypatch.setattr(settings, 'support_workflows_enabled', True)
    monkeypatch.setattr(settings, 'operational_workflows_enabled', True)
    api[0].app.include_router(support_requests.router, prefix='/api/v1')
    balance(api, 49)
    record = create(api, source(api)).json()
    payload = dict(category='TECHNICAL', subject='Unresolved membership payment', body=f"Checkout: {record['id']}; wallet reserved: INR 49.00")
    headers = {**api[1][1], 'Idempotency-Key': 'recovery-support-request'}
    response = api[0].post('/api/v1/support/tickets', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    ticket = response.json()
    assert api[0].post('/api/v1/support/tickets', headers=headers, json=payload).json()['id'] == ticket['id']
    with Session(api[2]) as db:
        # The booking fixture has only customers/owners/staff. Add an isolated
        # administrator rather than assuming another fixture's role assignments.
        role = Role(name='ADMIN'); db.add(role); db.flush()
        db.add(UserRole(user_id=5, role_id=role.id)); db.commit()
        admin = db.get(User, 5)
        SupportService(db, admin, admin=True).change_status(ticket['id'], SupportStatusChange(status='RESOLVED', expected_version=ticket['version']))
        assert db.get(CheckoutFunding, record['id']).state == 'HELD'
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0
        assert db.scalar(select(func.count(SupportTicket.id))) == 1
    assert create(api, source(api, 'SINGLE_GYM'), 'after-support-resolved').status_code == 409