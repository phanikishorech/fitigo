"""Real services and disposable MySQL; gateway HTTP is always mocked."""
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, balance, create
from app.models.payment_checkout import PaymentCheckout
from app.models.checkout_funding import CheckoutFunding
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.membership import UserMembership


def source(api, kind='MULTI_GYM', wallet=True):
    if kind == 'SINGLE_GYM':
        quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
        return dict(kind=kind, gym_id=1, plan_id=1, accepted_quote=quote['quote_token'], use_wallet=wallet)
    order = api[0].post('/api/v1/memberships/orders', headers={**api[1][1], 'Idempotency-Key': 'recovery-membership-order'}, json={'plan_id': 1}).json()
    return dict(kind=kind, order_id=order['id'], accepted_quote=order['quote_token'], use_wallet=wallet)


def recover(api, payload, user=1):
    params = {key: value for key, value in payload.items() if key in {'kind', 'order_id', 'gym_id', 'plan_id'}}
    return api[0].get('/api/v1/payments/membership-checkout', params=params, headers=api[1][user])


def cancel(api, record):
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])


def refresh(api, record):
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh", headers=api[1][1])


@pytest.mark.parametrize('kind', ['SINGLE_GYM', 'MULTI_GYM'])
def test_restore_fixed_funding_and_conflicting_selection(api, kind):
    balance(api, 49)
    payload = source(api, kind)
    record = create(api, payload).json()
    calls = len(api[3].calls) if record['provider'] == 'CASHFREE' else api[3].creations
    restored = recover(api, payload)
    assert restored.status_code == 200, restored.text
    assert restored.headers['cache-control'] == 'no-store'
    assert restored.json()['checkout']['id'] == record['id']
    assert restored.json()['checkout']['wallet_amount'] == '49.00'
    assert restored.json()['matches_selection'] is True
    assert (len(api[3].calls) if record['provider'] == 'CASHFREE' else api[3].creations) == calls
    conflict = recover(api, source(api, 'SINGLE_GYM' if kind == 'MULTI_GYM' else 'MULTI_GYM')).json()
    assert conflict['checkout']['id'] == record['id'] and not conflict['matches_selection']
    assert create(api, {**payload, 'use_wallet': False}, 'different-funding-key').status_code == 409
    other = recover(api, payload, user=4)
    if kind == 'MULTI_GYM':
        assert other.status_code == 404
    else:
        assert other.json()['checkout'] is None
    assert api[3].creations == 1


@pytest.mark.parametrize('wallet', [False, True])
def test_cancel_then_fresh_checkout_and_idempotent_retry(api, wallet):
    balance(api, 49)
    payload = source(api, wallet=wallet)
    record = create(api, payload).json()
    response = cancel(api, record)
    if record['provider'] == 'RAZORPAY':
        assert response.status_code == 409
        assert recover(api, payload).json()['checkout']['id'] == record['id']
        return
    assert record['can_request_cancel'] and not record['can_cancel']
    assert response.status_code == 200, response.text
    closed = response.json()
    assert closed['status'] == 'CANCELLED' and closed['replacement_safe']
    assert closed['wallet_status'] == ('RELEASED' if wallet else 'NONE')
    assert cancel(api, record).json()['status'] == 'CANCELLED'
    assert recover(api, payload).json()['checkout'] is None
    quote = api[0].post('/api/v1/payments/quote', headers=api[1][1], json=payload)
    assert quote.status_code == 200, quote.text
    assert Decimal(quote.json()['available_wallet_balance']) == 49
    replacement = create(api, {**payload, 'use_wallet': not wallet}, 'replacement-funding-key')
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()['id'] != record['id']
    assert create(api, {**payload, 'use_wallet': not wallet}, 'replacement-funding-key').json()['id'] == replacement.json()['id']
    assert create(api, payload).json()['id'] == record['id']
    assert api[3].creations == 2
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0
        assert db.get(PaymentCheckout, record['id']).status == 'CANCELLED'


@pytest.mark.parametrize('outcome', ['pending', 'timeout', 'processing', 'success'])
def test_ambiguous_cancellation_never_unlocks_new_payment(api, outcome):
    if not hasattr(api[3], 'termination_state'):
        pytest.skip('Cashfree termination contract')
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    if outcome == 'pending': api[3].termination_state = 'TERMINATION_REQUESTED'
    if outcome == 'timeout': api[3].termination_timeout = True
    if outcome == 'processing': api[3].pay(record, 'PENDING')
    if outcome == 'success': api[3].success_on_termination = True
    response = cancel(api, record)
    if outcome == 'timeout':
        assert response.status_code == 503
        current = api[0].get(f"/api/v1/payments/checkouts/{record['id']}", headers=api[1][1]).json()
    else:
        assert response.status_code == 200, response.text
        current = response.json()
    if outcome == 'success':
        assert current['status'] == 'PAID' and current['membership_id']
        assert current['wallet_status'] == 'DEBITED'
    else:
        assert not current['can_pay'] and not current['replacement_safe']
        assert current['wallet_status'] == 'HELD'
        assert current['cancellation_requested']
        assert create(api, {**payload, 'use_wallet': False}, 'blocked-replacement-key').status_code == 409
        assert recover(api, payload).json()['checkout']['id'] == record['id']
    assert api[3].creations == 1
    if outcome in {'pending', 'timeout'}:
        api[3].orders[record['gateway_order_id']]['order_status'] = 'TERMINATED'
        final = refresh(api, record).json()
        assert final['status'] == 'CANCELLED' and final['wallet_status'] == 'RELEASED'
        with Session(api[2]) as db:
            assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == 49
            assert db.scalar(select(func.count(WalletTransaction.id))) == 0


def test_legacy_unsafe_cancellation_blocks_replacement(api):
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    with Session(api[2]) as db:
        row = db.get(PaymentCheckout, record['id'])
        row.status = 'CANCELLED'
        row.checkout_data = {**(row.checkout_data or {}), 'replacement_safe': False}
        db.commit()
    assert recover(api, payload).json()['checkout']['id'] == record['id']
    assert create(api, payload, 'new-browser-key').status_code == 409
    assert api[3].creations == 1


def test_late_capture_after_close_preserves_history_and_blocks_replacement(api):
    if not hasattr(api[3], 'termination_state'):
        pytest.skip('Cashfree closure contract')
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    assert cancel(api, record).json()['status'] == 'CANCELLED'
    api[3].pay(record)
    response = create(api, payload, 'late-capture-replacement')
    assert response.status_code == 409, response.text
    assert recover(api, payload).json()['checkout']['status'] == 'REVIEW_REQUIRED'
    assert api[3].creations == 1
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(UserMembership.id))) == 0
        assert db.scalar(select(func.count(WalletTransaction.id))) == 0
        assert db.get(CheckoutFunding, record['id']).state == 'RELEASED'


def test_change_plan_after_closure_revalidates_price_and_preserves_original(api):
    if not hasattr(api[3], 'termination_state'):
        pytest.skip('Cashfree closure contract')
    from app.models.platform_membership import PlatformMembershipPlan
    balance(api, 49)
    payload = source(api)
    record = create(api, payload).json()
    with Session(api[2]) as db:
        db.add(PlatformMembershipPlan(id=2, code='annual-recovery', name='Annual', duration_value=1,
            duration_unit='YEAR', base_price=2000, currency='INR', benefits=[], is_active=True, version=1))
        db.commit()
    order = api[0].post('/api/v1/memberships/orders', headers={**api[1][1], 'Idempotency-Key': 'changed-plan-order'}, json={'plan_id': 2}).json()
    changed = dict(kind='MULTI_GYM', order_id=order['id'], accepted_quote=order['quote_token'], use_wallet=True)
    assert recover(api, changed).json()['matches_selection'] is False
    assert create(api, changed, 'changed-plan-payment').status_code == 409
    assert cancel(api, record).json()['replacement_safe']
    with Session(api[2]) as db:
        db.get(PlatformMembershipPlan, 2).base_price = 2100
        db.commit()
    assert create(api, changed, 'changed-plan-payment').status_code == 409
    current = api[0].get(f"/api/v1/memberships/orders/{order['id']}", headers=api[1][1]).json()
    changed['accepted_quote'] = current['quote_token']
    replacement = create(api, changed, 'changed-plan-payment')
    assert replacement.status_code == 200, replacement.text
    assert Decimal(replacement.json()['total_amount']) == 2100
    assert Decimal(replacement.json()['wallet_amount']) == 49
    with Session(api[2]) as db:
        assert db.get(PaymentCheckout, record['id']).snapshot['id'] == 1
        assert db.get(PaymentCheckout, replacement.json()['id']).snapshot['id'] == 2
    assert api[3].creations == 2


def test_gateway_only_pending_termination_closes_on_refresh(api):
    if not hasattr(api[3], 'termination_state'):
        pytest.skip('Cashfree termination contract')
    payload = source(api, wallet=False)
    record = create(api, payload).json()
    api[3].termination_state = 'TERMINATION_REQUESTED'
    current = cancel(api, record).json()
    assert not current['can_pay'] and not current['replacement_safe']
    assert recover(api, payload).json()['checkout']['id'] == record['id']
    api[3].orders[record['gateway_order_id']]['order_status'] = 'TERMINATED'
    assert refresh(api, record).json()['status'] == 'CANCELLED'
    assert recover(api, payload).json()['checkout'] is None