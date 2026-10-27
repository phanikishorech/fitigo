from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.wallet import WalletAccount, WalletTransaction
from app.models.membership import UserMembership
from app.models.booking import Payment
from app.models.access import AccessQrToken
from test_cashfree_payments import api, razorpay_api, booking_api, source_for, checkout, refresh, NOW


def test_discounted_success_recorded_for_review_not_credit_and_does_not_block_new_topup(api):
    with Session(api[2]) as db:
        before = db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1))
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500'})
    api[3].pay(record, payment_amount=450, order_amount=500,
        payment_offers=[{'offer_redemption': {'redemption_status': 'SUCCESS', 'discount_amount': 50}}])
    result = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'new-amount-key'},
        json={'kind': 'WALLET_TOPUP', 'amount': '1000'})
    assert result.status_code == 200, result.text
    assert result.json()['id'] == record['id']
    assert result.json()['status'] == 'REVIEW_REQUIRED' and not result.json()['can_pay']
    assert api[3].creations == 1  # Recover first; no automatic replacement charge.
    result = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert result.json()['status'] == 'REVIEW_REQUIRED'  # Paid is never called cancelled.
    history = api[0].get('/api/v1/payments/history', headers=api[1][1]).json()['items'][0]
    assert history['attempts'][0]['amount'] == '450.00'
    assert history['attempts'][0]['status'] == 'SUCCESS'
    with Session(api[2]) as db:
        assert db.scalar(select(WalletAccount.balance).where(WalletAccount.user_id == 1)) == before
        assert db.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.checkout_id == record['id'])) == 0
    next_record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '1000'}, key='explicit-new-recharge')
    assert next_record['id'] != record['id'] and api[3].creations == 2


def test_discounted_failed_attempt_can_be_cancelled_and_does_not_hide_matching_success(api):
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500'})
    api[3].pay(record, 'FAILED', payment_amount=450)
    assert refresh(api, record).json()['status'] == 'FAILED'
    cancelled = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'CANCELLED'
    other = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '600'}, key='second-recharge')
    api[3].pay(other, 'USER_DROPPED', payment_amount=550)
    api[3].pay(other)
    assert refresh(api, other).json()['status'] == 'PAID'


def test_discounted_cart_does_not_block_a_new_cart_purchase(api):
    record = checkout(api, source_for(api, 'CART'))
    api[3].pay(record, 'FAILED', payment_amount=150)
    api[3].pay(record, payment_amount=150)
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    new = checkout(api, source_for(api, 'CART'), key='new-cart-after-review')
    assert new['id'] != record['id']


def test_history_excludes_wallet_and_dummy_payments_but_includes_gateway_recharges(api):
    from test_razorpay_payments import create_booking
    booked = create_booking(api)
    with Session(api[2]) as db:
        account = db.scalar(select(WalletAccount).where(WalletAccount.user_id == 1))
        db.add(WalletTransaction(account_id=account.id, user_id=1, direction='OUT', txn_type='PAYMENT', amount=100, currency='INR'))
        db.add(WalletTransaction(account_id=account.id, user_id=1, direction='IN', txn_type='TOPUP', amount=1000, currency='INR'))
        payment = db.scalar(select(Payment).where(Payment.booking_id == booked['id']))
        payment.provider, payment.status = 'WALLET', 'PAID'
        db.add(UserMembership(user_id=1, gym_id=1, membership_type='SINGLE_GYM', paid_amount=500,
            payment_provider='WALLET', payment_status='PAID', start_at=NOW, end_at=NOW))
        db.commit()
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500'})
    history = api[0].get('/api/v1/payments/history', headers=api[1][1]).json()
    assert history['total'] == 1 and history['items'][0]['checkout_id'] == record['id']
    assert history['items'][0]['provider'] == 'CASHFREE'
    assert api[0].get('/api/v1/payments/history?kind=WALLET_LEDGER', headers=api[1][1]).json()['total'] == 0


def test_paid_order_without_payment_details_cannot_be_cancelled(api):
    record = checkout(api, {'kind': 'WALLET_TOPUP', 'amount': '500'})
    api[3].orders[record['gateway_order_id']]['order_status'] = 'PAID'
    response = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert response.json()['status'] == 'REVIEW_REQUIRED'
    assert response.json()['failure_code'] == 'PAID_ORDER_PAYMENT_UNAVAILABLE'