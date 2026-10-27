"""Actual Cashfree adapter + HTTP transport mock + existing authenticated API/DB fixture."""
import base64
import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import User
from app.models.booking import Booking, Payment
from app.models.membership import UserMembership
from app.models.access import AccessQrToken
from app.models.payment_checkout import PaymentCheckout, PaymentWebhookReceipt
from app.services.cashfree_provider import CashfreeProvider
from test_razorpay_payments import api as razorpay_api, booking_api, checkout, create_booking, refresh, NOW


class CashfreeHTTP:
    def __init__(self):
        self.orders, self.attempts, self.refunds, self.calls = {}, {}, {}, []
        self.creations = 0
        self.timeout = False
        self.unavailable = False

    def __call__(self, request):
        self.calls.append(request)
        assert request.url.host == 'sandbox.cashfree.com'
        assert request.headers['x-api-version'] == '2026-01-01'
        assert request.headers['x-client-secret'] == 'fixture-cashfree-secret'
        if self.unavailable:
            raise httpx.ReadTimeout('mock timeout', request=request)
        path = request.url.path.removeprefix('/pg/').split('/')
        if request.method == 'POST':
            self.creations += 1
            body = json.loads(request.content)
            order_id = body['order_id']
            assert request.headers['x-idempotency-key'].replace('-', '') == order_id.removeprefix('fitigo_')
            assert body['customer_details']['customer_id'] == 'fitigo_user_1'
            self.orders[order_id] = {**body, 'order_status': 'ACTIVE', 'payment_session_id': 'session_fixture'}
            self.attempts[order_id], self.refunds[order_id] = [], []
            if self.timeout:
                raise httpx.ReadTimeout('mock lost response', request=request)
            return httpx.Response(200, json=self.orders[order_id])
        order_id = path[1]
        if order_id not in self.orders:
            return httpx.Response(404, json={'type': 'invalid_request_error', 'code': 'order_not_found'})
        value = self.orders[order_id] if len(path) == 2 else self.attempts[order_id] if path[2] == 'payments' else self.refunds[order_id]
        return httpx.Response(200, json=value)

    def pay(self, record, state='SUCCESS', **updates):
        order_id = record['gateway_order_id']
        row = {'cf_payment_id': len(self.attempts[order_id]) + 100, 'order_id': order_id,
            'payment_amount': float(record['amount']), 'payment_currency': record['currency'],
            'payment_status': state, 'is_captured': state == 'SUCCESS'}
        row.update(updates)
        self.attempts[order_id].append(row)
        if state == 'SUCCESS':
            self.orders[order_id]['order_status'] = 'PAID'
        return row


@pytest.fixture
def api(razorpay_api, monkeypatch):
    monkeypatch.setattr(settings, 'payment_gateway', 'cashfree')
    monkeypatch.setattr(settings, 'payment_env', 'sandbox')
    monkeypatch.setattr(settings, 'cashfree_client_id', 'fixture-cashfree-id')
    monkeypatch.setattr(settings, 'cashfree_client_secret', SecretStr('fixture-cashfree-secret'))
    monkeypatch.setattr(settings, 'cashfree_api_version', '2026-01-01')
    monkeypatch.setattr(settings, 'payment_return_url', 'http://localhost:5173/checkout')
    with Session(razorpay_api[2]) as db:
        db.get(User, 1).phone = '9999999999'
        db.commit()
    transport = CashfreeHTTP()
    client = httpx.Client
    monkeypatch.setattr('app.services.cashfree_provider.httpx.Client', lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(transport)))
    return *razorpay_api[:3], transport


def verify(api, record):
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/verify", headers=api[1][1], json={})


def webhook(api, record, event='PAYMENT_SUCCESS_WEBHOOK', *, tamper=False, timestamp='1793030400000'):
    raw = json.dumps({'type': event, 'data': {'order': {'order_id': record['gateway_order_id']},
        'payment': {'payment_status': 'SUCCESS', 'payment_amount': 100.00}}}, separators=(',', ':')).encode()
    signature = base64.b64encode(hmac.new(b'fixture-cashfree-secret', timestamp.encode() + raw, hashlib.sha256).digest()).decode()
    return api[0].post('/api/v1/payments/webhooks/cashfree', content=raw + (b' ' if tamper else b''),
        headers={'x-webhook-signature': signature, 'x-webhook-timestamp': timestamp, 'Content-Type': 'application/json'})


def source_for(api, kind):
    if kind == 'BOOKING':
        return {'kind': kind, 'booking_id': create_booking(api)['id']}
    if kind == 'SINGLE_GYM':
        quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
        assert quote['payment_mode'] == 'CASHFREE'
        return {'kind': kind, 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']}
    if kind == 'MULTI_GYM':
        order = api[0].post('/api/v1/memberships/orders', headers={**api[1][1], 'Idempotency-Key': 'multi-order-1'}, json={'plan_id': 1}).json()
        return {'kind': kind, 'order_id': order['id'], 'accepted_quote': order['quote_token']}
    response = api[0].post('/api/v1/cart/items/gym', headers=api[1][1], json={'booking_type': 'GYM', 'gym_id': 1,
        'booking_date': str(NOW.date()), 'preferred_start_time': '10:00:00', 'preferred_end_time': '11:00:00',
        'member_count': 2, 'visitor_names': ['Guest One', 'Guest Two']})
    assert response.status_code == 200, response.text
    return {'kind': 'CART'}


@pytest.mark.parametrize('kind,amount', [('BOOKING', 100), ('SINGLE_GYM', 500), ('MULTI_GYM', 1000), ('CART', 200)])
def test_shared_pricing_fulfillment_and_duplicate_events(api, kind, amount):
    source = source_for(api, kind)
    record = checkout(api, source)
    assert Decimal(record['amount']) == amount
    assert record['provider'] == 'CASHFREE' and record['environment'] == 'sandbox'
    assert record['payment_session_id'] == 'session_fixture' and record['razorpay_order_id'] is None
    assert 'fixture-cashfree-secret' not in json.dumps(record)
    assert 'fixture-cashfree-id' not in json.dumps(record)
    assert checkout(api, source, key='different-browser-key')['id'] == record['id']
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(UserMembership.id))) == 0
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    api[3].pay(record)
    assert webhook(api, record).json()['status'] == 'processed'
    assert webhook(api, record).json()['status'] == 'duplicate'
    assert webhook(api, record, 'PAYMENT_FAILED_WEBHOOK').status_code == 200
    assert verify(api, record).json()['status'] == 'PAID'
    assert api[3].creations == 1
    with Session(api[2]) as db:
        if kind in {'SINGLE_GYM', 'MULTI_GYM'}:
            assert db.scalar(select(func.count(UserMembership.id))) == 1
            assert db.scalar(select(UserMembership.payment_provider)) == 'CASHFREE'
        else:
            assert db.scalar(select(func.count(Booking.id))) == 1
            assert db.scalar(select(Booking.status)) == 'CONFIRMED'
            assert db.scalar(select(Payment.provider)) == 'CASHFREE'
            assert db.scalar(select(func.count(AccessQrToken.id))) == (2 if kind == 'CART' else 1)


@pytest.mark.parametrize('kind', ['BOOKING', 'SINGLE_GYM', 'MULTI_GYM'])
@pytest.mark.parametrize('state', ['PENDING', 'FAILED', 'USER_DROPPED', 'NOT_ATTEMPTED'])
def test_unverified_states_never_grant_access_and_retry_reuses_order(api, kind, state):
    source = source_for(api, kind)
    record = checkout(api, source)
    api[3].pay(record, state)
    assert webhook(api, record).status_code == 200  # A signed SUCCESS claim still cannot override the API.
    result = verify(api, record).json()
    assert result['status'] in {'FAILED', 'PENDING'}
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(UserMembership.id))) == 0
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    assert checkout(api, source, key='retry-another-key')['id'] == record['id']
    api[3].pay(record)
    assert refresh(api, record).json()['status'] == 'PAID'
    assert api[3].creations == 1


@pytest.mark.parametrize('updates', [{'payment_amount': 1}, {'payment_currency': 'USD'}, {'order_id': 'other'}])
def test_wrong_amount_currency_or_order_fails_closed(api, updates):
    record = checkout(api)
    api[3].pay(record, **updates)
    response = verify(api, record)
    if 'payment_amount' in updates:
        assert response.status_code == 200
        assert response.json()['status'] == 'REVIEW_REQUIRED'
        assert response.json()['failure_code'] == 'PAYMENT_AMOUNT_MISMATCH'
    else:
        assert response.status_code == 409
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0


def test_raw_signature_timestamp_and_browser_assertions(api):
    record = checkout(api)
    assert webhook(api, record, tamper=True).status_code == 400
    assert webhook(api, record, timestamp='').status_code == 400
    assert api[0].post('/api/v1/payments/webhooks/cashfree', content=b'{}').status_code == 400
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/verify", headers=api[1][1], json={'status': 'PAID'}).status_code == 422
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/verify", headers=api[1][4], json={}).status_code == 404
    assert api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'forged-amount'}, json={'kind': 'BOOKING', 'booking_id': record['booking_ids'][0], 'amount': 1}).status_code == 422


def test_lost_creation_and_status_timeout_do_not_create_another_order(api):
    source = source_for(api, 'BOOKING')
    api[3].timeout = True
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'lost-response'}, json=source)
    assert response.status_code == 503
    with Session(api[2]) as db:
        record = {'id': db.scalar(select(PaymentCheckout.id)), 'gateway_order_id': next(iter(api[3].orders))}
    assert webhook(api, record).status_code == 200
    record = refresh(api, record).json()
    api[3].unavailable = True
    assert refresh(api, record).status_code == 503
    api[3].unavailable = False
    api[3].pay(record)
    assert refresh(api, record).json()['status'] == 'PAID'
    assert api[3].creations == 1


def test_unknown_create_stays_creating_without_charge_retry(api):
    api[3].timeout = True
    source = source_for(api, 'BOOKING')
    assert api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'lost-request'}, json=source).status_code == 503
    api[3].orders.clear()
    with Session(api[2]) as db:
        record = {'id': db.scalar(select(PaymentCheckout.id))}
    assert refresh(api, record).json()['status'] == 'CREATING'
    assert api[3].creations == 1


def test_cancelled_checkout_late_success_requires_review(api):
    record = checkout(api)
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1]).json()['status'] == 'CANCELLED'
    api[3].pay(record)
    assert webhook(api, record).status_code == 200
    assert refresh(api, record).json()['status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
        assert db.scalar(select(Payment.status)) == 'PAID'


def test_switch_preserves_existing_provider_and_delayed_webhooks(api, monkeypatch):
    record = checkout(api)
    monkeypatch.setattr(settings, 'payment_gateway', 'razorpay')
    assert api[0].get('/api/v1/payments/config', headers=api[1][1]).json()['provider'] == 'RAZORPAY'
    api[3].pay(record)
    assert webhook(api, record).status_code == 200
    assert refresh(api, record).json()['provider'] == 'CASHFREE'
    assert refresh(api, record).json()['status'] == 'PAID'


def test_expired_provider_order_is_not_payable(api):
    record = checkout(api)
    api[3].orders[record['gateway_order_id']]['order_status'] = 'EXPIRED'
    result = refresh(api, record).json()
    assert result['status'] == 'FAILED' and not result['can_pay']


def test_missing_profile_phone_fails_before_creating_pending_purchase(api):
    with Session(api[2]) as db:
        db.get(User, 1).phone = None
        db.commit()
    source = source_for(api, 'SINGLE_GYM')
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'missing-phone'}, json=source)
    assert response.status_code == 409 and api[3].creations == 0
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(PaymentCheckout.id))) == 0


def test_cashfree_selection_blocks_legacy_bypasses(api):
    record = checkout(api)
    assert api[0].post(f"/api/v1/bookings/{record['booking_ids'][0]}/pay", headers=api[1][1]).status_code == 409
    from app.services.membership_wallet_service import wallet_enabled
    assert not wallet_enabled()


def test_dashboard_refund_reconciliation_and_cancel_never_fabricates_refund(api):
    record = checkout(api)
    payment = api[3].pay(record)
    assert verify(api, record).json()['status'] == 'PAID'
    response = api[0].post(f"/api/v1/bookings/{record['booking_ids'][0]}/cancel", headers=api[1][1], json={'reason': 'cancel'})
    assert response.json()['payment']['status'] == 'PAID'
    api[3].refunds[record['gateway_order_id']] = [{'cf_refund_id': '1', 'cf_payment_id': payment['cf_payment_id'],
        'order_id': record['gateway_order_id'], 'refund_currency': 'INR', 'refund_amount': 100, 'refund_status': 'SUCCESS'}]
    assert refresh(api, record).json()['status'] == 'REFUNDED'


def test_duplicate_success_webhook_rechecks_pending_provider_status(api):
    record = checkout(api)
    assert webhook(api, record).status_code == 200
    assert refresh(api, record).json()['status'] == 'PENDING'
    api[3].pay(record)
    assert webhook(api, record).json()['status'] == 'duplicate'
    assert refresh(api, record).json()['status'] == 'PAID'


@pytest.mark.parametrize('price', [0, Decimal('0.50')])
def test_free_and_below_minimum_purchase_do_not_create_external_orders(api, price):
    from app.models.membership import GymMembershipPlan
    with Session(api[2]) as db:
        db.get(GymMembershipPlan, 1).price = price
        db.commit()
    source = source_for(api, 'SINGLE_GYM')
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'minimum-payment'}, json=source)
    assert response.status_code == (200 if price == 0 else 409)
    assert api[3].creations == 0
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(PaymentCheckout.id))) == (1 if price == 0 else 0)