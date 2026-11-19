from decimal import Decimal
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.payment_checkout import PaymentAttempt, PaymentCheckout
from test_razorpay_payments import api as razorpay_api, booking_api, checkout, refresh, verify as razor_verify, webhook as razor_webhook
from test_cashfree_payments import api as cashfree_api, verify as cash_verify, webhook as cash_webhook


@pytest.fixture(params=['razorpay', 'cashfree'])
def api(request):
    value = request.getfixturevalue(request.param + '_api')
    from app.routers.wallet import router
    value[0].app.include_router(router, prefix='/api/v1')
    return value


def balance(api):
    with Session(api[2]) as db:
        return Decimal(db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)))


def confirm(api, record, entity):
    return cash_verify(api, record) if record['provider'] == 'CASHFREE' else razor_verify(api, record, entity)


def webhook(api, record, entity):
    return cash_webhook(api, record) if record['provider'] == 'CASHFREE' else razor_webhook(api, entity)


def test_verified_recharge_once_history_and_duplicate_events(api):
    before = balance(api)
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500.25'})
    assert balance(api) == before
    assert record['booking_ids'] == [] and record['membership_id'] is None
    second = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500.25'}, key='new-browser-key')
    assert second['id'] == record['id']
    entity = api[3].pay(record)
    assert confirm(api, record, entity).json()['status'] == 'PAID'
    for _ in range(2):
        assert webhook(api, record, entity).status_code == 200
        assert refresh(api, record).json()['status'] == 'PAID'
    assert balance(api) == before + Decimal('500.25')
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.checkout_id == record['id'])) == 1
        assert db.scalar(select(func.count(PaymentAttempt.id))) == 1
    history = api[0].get('/api/v1/payments/history', headers=api[1][1]).json()
    row = history['items'][0]
    assert history['total'] == 1 and row['kind'] == 'WALLET_TOPUP'
    assert row['provider_order_id'] == record['gateway_order_id']
    assert row['attempts'][0]['transaction_id'] == row['transaction_id']
    assert len(row['wallet_entries']) == 1
    assert 'payment_session_id' not in str(row) and 'fixture-key-secret' not in str(row)
    assert api[0].get('/api/v1/payments/history', headers=api[1][4]).json()['items'] == []
    assert api[0].get('/api/v1/payments/history').status_code == 401


def test_failed_pending_attempts_never_credit_and_are_preserved(api):
    before = balance(api)
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '100'})
    states = ('FAILED', 'PENDING') if record['provider'] == 'CASHFREE' else ('failed', 'authorized')
    for state in states:
        api[3].pay(record, state)
        assert refresh(api, record).json()['status'] in {'FAILED', 'PENDING'}
        assert balance(api) == before
    response = api[0].get('/api/v1/payments/history', headers=api[1][1]).json()
    assert len(response['items'][0]['attempts']) == 2
    assert {r['status'] for r in response['items'][0]['attempts']} == {'FAILED', 'PENDING'}
    assert confirm(api, record, api[3].pay(record)).json()['status'] == 'PAID'
    assert balance(api) == before + 100


def test_recharge_validation_cancel_and_legacy_bypass(api):
    assert api[0].post('/api/v1/wallet/topup', headers=api[1][1], json={'amount': 500}).status_code == 409
    for amount in ('0', '-1', '0.50', '100000.01', '1.001'):
        response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'invalid-recharge'}, json={'kind': 'WALLET_TOPUP', 'amount': amount})
        assert response.status_code == 422
    before = balance(api)
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '100'})
    assert api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'checkout-0001'}, json={'kind': 'WALLET_TOPUP', 'amount': '200'}).status_code == 409
    # Open/unverified orders cannot be locally cancelled. A subsequent verified
    # capture remains a legitimate top-up, credited once rather than lost money.
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1]).status_code == 409
    assert balance(api) == before
    entity = api[3].pay(record)
    assert confirm(api, record, entity).json()['status'] == 'PAID'
    assert confirm(api, record, entity).json()['status'] == 'PAID'
    assert balance(api) == before + 100
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.checkout_id==record['id'])) == 1


def test_gateway_refund_reverses_credit_once_even_if_spent(api):
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '100'})
    entity = api[3].pay(record)
    assert confirm(api, record, entity).json()['status'] == 'PAID'
    with Session(api[2]) as db:
        db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1)).balance = 20
        db.commit()
    if record['provider'] == 'CASHFREE':
        api[3].refunds[record['gateway_order_id']] = [{'cf_refund_id': '1', 'cf_payment_id': entity['cf_payment_id'], 'order_id': record['gateway_order_id'], 'refund_currency': 'INR', 'refund_amount': 100, 'refund_status': 'SUCCESS'}]
    else:
        api[3].entities[entity['id']].update(status='refunded', amount_refunded=10000)
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    assert balance(api) == 20
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    assert balance(api) == 20
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.txn_type == 'REFUND_REVERSAL')) == 0
        assert db.get(PaymentCheckout, record['id']).snapshot['wallet_refund_pending_minor'] == 10000
    assert Decimal(api[0].get('/api/v1/wallet/balance', headers=api[1][1]).json()['available_balance']) == 0


def test_wallet_mode_mismatch_fails_before_order(api):
    with Session(api[2]) as db:
        db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1)).payment_mode = 'live'
        db.commit()
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'mode-mismatch'}, json={'kind': 'WALLET_TOPUP', 'amount': 100})
    assert response.status_code == 409
    assert api[3].creations == 0


@pytest.mark.parametrize('restriction', ['none', 'migration', 'mode'])
def test_wallet_reads_preserve_balance_and_explain_spending_restriction(api, monkeypatch, restriction):
    from app.services import checkout_funding
    with Session(api[2]) as db:
        account = db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1))
        account.balance = Decimal('300.00')
        account.payment_mode = 'live' if restriction == 'mode' else 'test'
        db.commit()
    if restriction == 'migration':
        monkeypatch.setattr(checkout_funding, 'available', lambda db: False)
    for path in ('balance', 'transactions'):
        response = api[0].get('/api/v1/wallet/' + path, headers=api[1][1])
        assert response.status_code == 200, response.text
        data = response.json()
        assert Decimal(data['balance']) == 300
        assert Decimal(data['reserved_balance']) == 0
        assert Decimal(data['available_balance']) == (300 if restriction == 'none' else 0)
        if restriction == 'none': assert data['wallet_unavailable_reason'] is None
        else: assert ('migration' if restriction == 'migration' else 'environment') in data['wallet_unavailable_reason']
    assert balance(api) == 300


def test_history_filters_pagination_do_not_duplicate_booking_purchase(api):
    record = checkout(api)
    confirm(api, record, api[3].pay(record))
    result = api[0].get('/api/v1/payments/history?kind=BOOKING&limit=1', headers=api[1][1]).json()
    assert result['total'] == 1 and len(result['items'][0]['bookings']) == 1
    assert api[0].get('/api/v1/payments/history?kind=BOOKING&limit=1&offset=1', headers=api[1][1]).json()['items'] == []
    assert api[0].get('/api/v1/payments/history?status=FAILED', headers=api[1][1]).json()['items'] == []


def test_incremental_partial_refunds_reverse_only_the_new_amount(api):
    before = balance(api)
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '100'})
    entity = api[3].pay(record)
    assert confirm(api, record, entity).json()['status'] == 'PAID'
    def refunded(amount):
        if record['provider'] == 'CASHFREE':
            api[3].refunds[record['gateway_order_id']] = [{'cf_refund_id': 'partial', 'cf_payment_id': entity['cf_payment_id'], 'order_id': record['gateway_order_id'], 'refund_currency': 'INR', 'refund_amount': amount, 'refund_status': 'SUCCESS'}]
        else:
            api[3].entities[entity['id']].update(amount_refunded=amount * 100)
    refunded(40)
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    assert balance(api) == before + 60
    refresh(api, record)
    assert balance(api) == before + 60
    refunded(100)
    assert refresh(api, record).json()['status'] == 'REFUNDED'
    assert balance(api) == before
    attempts = api[0].get('/api/v1/payments/history?kind=WALLET_TOPUP', headers=api[1][1]).json()['items'][0]['attempts']
    assert attempts[0]['refunded_amount'] == '100.00'