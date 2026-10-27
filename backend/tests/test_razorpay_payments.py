"""No external payment calls or configured database access: deterministic gateway adapter tests."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.core.time import stored_instant
from app.models.access import AccessQrToken
from app.models.booking import Booking, Payment
from app.models.membership import GymMembershipPlan, UserMembership
from app.models.platform_membership import PlatformMembershipPlan
from app.models.payment_checkout import PaymentCheckout, PaymentWebhookReceipt
from app.models.gym import Gym
from app.routers import payments, memberships, platform_memberships
from app.services import payment_checkout_service
from app.services.razorpay_gateway import RazorpayGateway, configured
from test_booking_access_qr import api as booking_api, NOW


class FakeGateway:
    def __init__(self):
        self.orders, self.entities = {}, {}
        self.creations = 0
        self.timeout_after_create = False

    def create_order(self, checkout):
        self.creations += 1
        order = dict(id=f"order_{self.creations}", amount=int(checkout.amount * 100), currency=checkout.currency,
                     receipt=checkout.id, status="created", amount_paid=0, amount_due=int(checkout.amount * 100))
        self.orders[order['id']] = order
        if self.timeout_after_create:
            raise HTTPException(503, detail="Simulated ambiguous order creation")
        return dict(order)

    def find_order(self, receipt):
        return next((dict(row) for row in self.orders.values() if row['receipt'] == receipt), None)

    def order(self, order_id):
        return dict(self.orders[order_id])

    def payment(self, payment_id):
        return dict(self.entities[payment_id])

    def payments(self, order_id):
        return [dict(row) for row in self.entities.values() if row['order_id'] == order_id]

    def pay(self, checkout, status='captured', **updates):
        order = self.orders[checkout['razorpay_order_id']]
        entity = dict(id=f"pay_{len(self.entities) + 1}", order_id=order['id'], amount=order['amount'],
                      currency=order['currency'], status=status, captured=status == 'captured', amount_refunded=0)
        entity.update(updates)
        self.entities[entity['id']] = entity
        if status == 'captured':
            order.update(status='paid', amount_paid=order['amount'], amount_due=0)
        return entity


@pytest.fixture
def api(booking_api, monkeypatch):
    client, headers, engine = booking_api
    def database():
        with Session(engine, autoflush=False) as db:
            yield db
    client.app.dependency_overrides[get_db] = database
    for router in [payments.router, memberships.router, platform_memberships.router]:
        client.app.include_router(router, prefix='/api/v1')
    monkeypatch.setattr(settings, 'payment_gateway', None)
    monkeypatch.setattr(settings, 'payment_env', None)
    monkeypatch.setattr(settings, 'razorpay_enabled', True)
    monkeypatch.setattr(settings, 'payment_mode', 'test')
    monkeypatch.setattr(settings, 'razorpay_key_id', 'rzp_test_fixture')
    monkeypatch.setattr(settings, 'razorpay_key_secret', SecretStr('fixture-key-secret'))
    monkeypatch.setattr(settings, 'razorpay_webhook_secret', SecretStr('fixture-webhook-secret'))
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return stored_instant(NOW.replace(hour=9))
    monkeypatch.setattr(payment_checkout_service, 'datetime', Clock)
    gateway = FakeGateway()
    monkeypatch.setattr('app.services.razorpay_provider.RazorpayGateway', lambda: gateway)
    with Session(engine) as db:
        db.get(Gym, 1).multi_gym_enabled = True
        db.add(GymMembershipPlan(id=1, gym_id=1, name='Single', duration_days=30, price=500))
        db.add(PlatformMembershipPlan(id=1, code='multi', name='Multi', duration_value=1, duration_unit='MONTH', base_price=1000,
                                     currency='INR', is_active=True, benefits=[], display_order=0))
        db.commit()
    return client, headers, engine, gateway


def create_booking(api):
    response = api[0].post('/api/v1/bookings', headers={**api[1][1], 'Idempotency-Key': 'booking-0001'},
                          json={'gym_slot_id': 1, 'slot_date': str(NOW.date()), 'quantity': 1, 'visitor_names': ['Test Visitor']})
    assert response.status_code == 200, response.text
    return response.json()


def checkout(api, source=None, key='checkout-0001'):
    source = source or {'kind': 'BOOKING', 'booking_id': create_booking(api)['id']}
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': key}, json=source)
    assert response.status_code == 200, response.text
    return response.json()


def verify(api, record, entity, **updates):
    signature = hmac.new(b'fixture-key-secret', f"{record['razorpay_order_id']}|{entity['id']}".encode(), hashlib.sha256).hexdigest()
    body = dict(razorpay_order_id=record['razorpay_order_id'], razorpay_payment_id=entity['id'], razorpay_signature=signature)
    body.update(updates)
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/verify", headers=api[1][1], json=body)


def refresh(api, record):
    return api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh", headers=api[1][1])


def webhook(api, entity, event_id='evt-1', event='payment.captured', signature=None):
    raw = json.dumps({'event': event, 'payload': {'payment': {'entity': entity}}}, separators=(',', ':')).encode()
    sig = signature or hmac.new(b'fixture-webhook-secret', raw, hashlib.sha256).hexdigest()
    return api[0].post('/api/v1/payments/webhooks/razorpay', content=raw,
                      headers={'X-Razorpay-Signature': sig, 'X-Razorpay-Event-Id': event_id, 'Content-Type': 'application/json'})


def test_success_confirmation_qr_and_duplicate_callback(api):
    record = checkout(api)
    booking_id = record['booking_ids'][0]
    assert api[0].post(f'/api/v1/bookings/{booking_id}/qr', headers=api[1][1]).status_code == 400
    entity = api[3].pay(record)
    for _ in range(2):
        response = verify(api, record, entity)
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'PAID'
    assert api[0].post(f'/api/v1/bookings/{booking_id}/qr', headers=api[1][1]).status_code == 200
    with Session(api[2]) as db:
        assert db.get(Booking, booking_id).status == 'CONFIRMED'
        assert db.scalar(select(func.count(Payment.id))) == 1
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1
        assert db.scalar(select(Payment.external_ref)) == entity['id']


def test_failed_cancelled_and_authorized_only_do_not_grant_access_and_retry_reuses_order(api):
    record = checkout(api)
    failed = api[3].pay(record, status='failed')
    assert verify(api, record, failed).json()['status'] == 'FAILED'
    assert checkout(api, {'kind': 'BOOKING', 'booking_id': record['booking_ids'][0]}, key='another-key')['id'] == record['id']
    authorized = api[3].pay(record, status='authorized')
    assert verify(api, record, authorized).json()['status'] == 'PENDING'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
        assert db.get(Booking, record['booking_ids'][0]).status == 'PENDING_PAYMENT'
    api[3].entities[authorized['id']].update(status='captured', captured=True)
    api[3].orders[record['razorpay_order_id']].update(status='paid', amount_paid=record['amount_minor'], amount_due=0)
    assert refresh(api, record).json()['status'] == 'PAID'
    assert api[3].creations == 1


def test_interrupted_callback_webhooks_deduplicate_and_do_not_regress_on_old_failure(api):
    record = checkout(api)
    failed = api[3].pay(record, status='failed')
    captured = api[3].pay(record)
    assert webhook(api, captured).json()['status'] == 'processed'
    assert webhook(api, captured).json()['status'] == 'duplicate'
    assert webhook(api, failed, 'evt-2', 'payment.failed').status_code == 200
    assert refresh(api, record).json()['status'] == 'PAID'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(PaymentWebhookReceipt.id))) == 2
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1


@pytest.mark.parametrize('updates', [{'amount': 1}, {'currency': 'USD'}, {'order_id': 'order_other'}])
def test_wrong_amount_currency_or_order_rejected(api, updates):
    record = checkout(api)
    entity = api[3].pay(record, **updates)
    response = verify(api, record, entity)
    if 'amount' in updates:
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'REVIEW_REQUIRED'
    else:
        assert response.status_code == 409, response.text
    with Session(api[2]) as db:
        assert db.get(Booking, record['booking_ids'][0]).status == 'PENDING_PAYMENT'
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0


def test_bad_signatures_ownership_and_browser_amount_rejected(api):
    record = checkout(api); entity = api[3].pay(record)
    assert verify(api, record, entity, razorpay_signature='0' * 64).status_code == 400
    assert webhook(api, entity, signature='0' * 64).status_code == 400
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/refresh", headers=api[1][4]).status_code == 404
    assert api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'forged-key'}, json={'kind': 'BOOKING', 'booking_id': 1, 'amount': 1}).status_code == 422
    assert 'fixture-key-secret' not in json.dumps(record)
    assert 'fixture-webhook-secret' not in json.dumps(record)


def test_cancelled_booking_cannot_be_reactivated_by_late_capture(api):
    record = checkout(api); booking_id = record['booking_ids'][0]
    assert api[0].post(f'/api/v1/bookings/{booking_id}/cancel', headers=api[1][1], json={'reason': 'Changed mind'}).status_code == 200
    entity = api[3].pay(record)
    assert verify(api, record, entity).json()['status'] == 'REVIEW_REQUIRED'
    assert api[0].post(f'/api/v1/bookings/{booking_id}/qr', headers=api[1][1]).status_code == 400
    with Session(api[2]) as db:
        assert db.get(Booking, booking_id).status == 'CANCELLED'
        assert db.scalar(select(Payment.status)) == 'PAID'  # Captured funds are not falsely labelled refunded.


def test_explicit_checkout_cancel_and_late_capture(api):
    record = checkout(api)
    response = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert response.json()['status'] == 'CANCELLED'
    assert verify(api, record, api[3].pay(record)).json()['status'] == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('kind', ['SINGLE_GYM', 'MULTI_GYM'])
def test_membership_only_activates_after_capture_and_only_once(api, kind):
    if kind == 'SINGLE_GYM':
        quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
        source = {'kind': kind, 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']}
    else:
        order = api[0].post('/api/v1/memberships/orders', headers={**api[1][1], 'Idempotency-Key': 'multi-order-1'}, json={'plan_id': 1}).json()
        source = {'kind': kind, 'order_id': order['id'], 'accepted_quote': order['quote_token']}
    record = checkout(api, source)
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(UserMembership.id))) == 0
    entity = api[3].pay(record)
    result = verify(api, record, entity)
    assert result.status_code == 200, result.text
    assert result.json()['membership_id'] is not None
    assert webhook(api, entity).status_code == 200
    assert checkout(api, source)['membership_id'] == result.json()['membership_id']
    with Session(api[2]) as db:
        member = db.scalar(select(UserMembership))
        assert member.status == 'ACTIVE' and member.membership_type == kind
        assert member.payment_provider == 'RAZORPAY' and member.external_ref == entity['id']
        assert db.scalar(select(func.count(UserMembership.id))) == 1


def test_cart_repeated_submission_creates_one_booking_and_one_gateway_order(api):
    body = {'booking_type': 'GYM', 'gym_id': 1, 'booking_date': str(NOW.date()), 'preferred_start_time': '10:00', 'preferred_end_time': '11:00', 'member_count': 1, 'visitor_names': ['Visitor']}
    added = api[0].post('/api/v1/cart/items/gym', headers=api[1][1], json=body)
    assert added.status_code == 200, added.text
    record = checkout(api, {'kind': 'CART'})
    assert checkout(api, {'kind': 'CART'}, key='reloaded-key')['id'] == record['id']
    result = verify(api, record, api[3].pay(record))
    assert result.json()['status'] == 'PAID', result.text
    assert checkout(api, {'kind': 'CART'})['id'] == record['id']
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(Booking.id))) == 1
    assert api[3].creations == 1


def test_ambiguous_order_creation_recovers_by_receipt_without_duplicate(api):
    booking = create_booking(api)
    api[3].timeout_after_create = True
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'uncertain-key'}, json={'kind': 'BOOKING', 'booking_id': booking['id']})
    assert response.status_code == 503
    with Session(api[2]) as db:
        checkout_id = db.scalar(select(PaymentCheckout.id))
    response = api[0].post(f'/api/v1/payments/checkouts/{checkout_id}/refresh', headers=api[1][1])
    assert response.status_code == 200 and response.json()['razorpay_order_id'] == 'order_1'
    assert api[3].creations == 1


def test_legacy_dummy_and_wallet_bypasses_are_disabled(api):
    booking = create_booking(api)
    for path in [f"/bookings/{booking['id']}/pay", '/cart/checkout', '/cart/checkout/wallet']:
        assert api[0].post('/api/v1' + path, headers=api[1][1]).status_code == 409


def test_live_requires_explicit_configuration(api, monkeypatch):
    assert configured()
    monkeypatch.setattr(settings, 'payment_mode', 'live')
    assert not configured()
    monkeypatch.setattr(settings, 'razorpay_key_id', 'rzp_live_fixture')
    assert not configured()
    monkeypatch.setattr(settings, 'razorpay_live_enabled', True)
    monkeypatch.setattr(settings, 'environment', 'production')
    assert configured()


def test_expired_booking_receives_no_qr_and_captured_funds_need_review(api):
    record = checkout(api)
    with Session(api[2]) as db:
        db.get(Booking, record['booking_ids'][0]).expires_at = stored_instant(NOW) - timedelta(days=1)
        db.commit()
    assert verify(api, record, api[3].pay(record)).json()['status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0


def test_refund_reconciliation_revokes_access_without_duplicate_fulfillment(api):
    record = checkout(api); entity = api[3].pay(record)
    assert verify(api, record, entity).json()['status'] == 'PAID'
    api[3].entities[entity['id']].update(status='refunded', amount_refunded=record['amount_minor'])
    assert refresh(api, record).json()['status'] == 'REFUNDED'
    assert refresh(api, record).json()['status'] == 'REFUNDED'
    assert api[0].post(f"/api/v1/bookings/{record['booking_ids'][0]}/qr", headers=api[1][1]).status_code == 400


def test_paid_booking_cancel_does_not_claim_gateway_refund(api):
    record = checkout(api); entity = api[3].pay(record)
    assert verify(api, record, entity).json()['status'] == 'PAID'
    booking_id = record['booking_ids'][0]
    response = api[0].post(f'/api/v1/bookings/{booking_id}/cancel', headers=api[1][1], json={'reason': 'cancel'})
    assert response.status_code == 200, response.text
    assert response.json()['payment']['status'] == 'PAID'
    assert webhook(api, entity).status_code == 200
    assert api[0].post(f'/api/v1/bookings/{booking_id}/qr', headers=api[1][1]).status_code == 400


def test_webhook_raw_body_tampering_and_event_id_collision(api):
    record = checkout(api); entity = api[3].pay(record)
    raw = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': entity}}}).encode()
    sig = hmac.new(b'fixture-webhook-secret', raw, hashlib.sha256).hexdigest()
    assert api[0].post('/api/v1/payments/webhooks/razorpay', content=raw + b' ',
        headers={'X-Razorpay-Signature': sig, 'X-Razorpay-Event-Id': 'tampered'}).status_code == 400
    assert webhook(api, entity).status_code == 200
    assert webhook(api, entity, event='payment.authorized').status_code == 409


def test_unknown_order_creation_without_provider_result_never_creates_a_second_order(api):
    booking = create_booking(api)
    api[3].timeout_after_create = True
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'uncertain-key'}, json={'kind': 'BOOKING', 'booking_id': booking['id']})
    assert response.status_code == 503
    api[3].orders.clear()
    with Session(api[2]) as db:
        record_id = db.scalar(select(PaymentCheckout.id))
    assert refresh(api, {'id': record_id}).json()['status'] == 'CREATING'
    assert api[3].creations == 1


def test_webhook_recovers_order_when_create_response_was_lost(api):
    booking = create_booking(api)
    api[3].timeout_after_create = True
    assert api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'lost-response'}, json={'kind': 'BOOKING', 'booking_id': booking['id']}).status_code == 503
    with Session(api[2]) as db:
        record_id = db.scalar(select(PaymentCheckout.id))
    entity = api[3].pay({'razorpay_order_id': 'order_1'})
    assert webhook(api, entity).status_code == 200
    assert refresh(api, {'id': record_id}).json()['status'] == 'PAID'


def test_paid_amount_order_mismatch_and_failed_webhook_are_not_acknowledged_as_fulfilled(api):
    record = checkout(api); entity = api[3].pay(record)
    api[3].orders[record['razorpay_order_id']]['amount_paid'] = 1
    assert webhook(api, entity).status_code == 409
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(PaymentWebhookReceipt.id))) == 0
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    api[3].orders[record['razorpay_order_id']]['amount_paid'] = record['amount_minor']
    assert webhook(api, entity).status_code == 200


def test_duplicate_new_membership_keys_resume_pending_plan(api):
    quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
    source = {'kind': 'SINGLE_GYM', 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']}
    first = checkout(api, source)
    second = checkout(api, source, key='another-browser-key')
    assert first['id'] == second['id'] and api[3].creations == 1


def test_free_membership_never_opens_gateway_and_activates_once(api):
    with Session(api[2]) as db:
        db.get(GymMembershipPlan, 1).price = 0
        db.commit()
    quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
    record = checkout(api, {'kind': 'SINGLE_GYM', 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']})
    assert record['status'] == 'PAID' and record['membership_id'] and not record['can_pay']
    assert api[3].creations == 0


def test_cart_class_capacity_is_taken_only_after_capture(api):
    from datetime import time
    from app.models.class_booking import ClassSession, GymClass
    with Session(api[2]) as db:
        db.get(Gym, 1).has_classes = True
        db.add(GymClass(id=1, gym_id=1, class_name='Yoga', is_active=True)); db.flush()
        db.add(ClassSession(id=1, gym_class_id=1, session_date=NOW.date(), start_time=time(10), end_time=time(11),
                            maximum_capacity=2, booked_capacity=0, price_per_person=200, status='AVAILABLE'))
        db.commit()
    response = api[0].post('/api/v1/cart/items/class', headers=api[1][1], json={'booking_type': 'CLASS', 'gym_id': 1,
        'class_session_id': 1, 'booking_date': str(NOW.date()), 'member_count': 1, 'visitor_names': ['Guest']})
    assert response.status_code == 200, response.text
    record = checkout(api, {'kind': 'CART'})
    with Session(api[2]) as db:
        assert db.get(ClassSession, 1).booked_capacity == 0
    entity = api[3].pay(record)
    assert verify(api, record, entity).json()['status'] == 'PAID'
    assert webhook(api, entity).status_code == 200
    with Session(api[2]) as db:
        assert db.get(ClassSession, 1).booked_capacity == 1


def test_gateway_transport_uses_fixed_host_basic_auth_and_server_amount(api, monkeypatch):
    import httpx
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'id': 'order_transport'})
    real_client = httpx.Client
    monkeypatch.setattr('app.services.razorpay_gateway.httpx.Client', lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)))
    record = PaymentCheckout(id='receipt', amount=Decimal('123.45'), currency='INR')
    assert RazorpayGateway().create_order(record)['id'] == 'order_transport'
    assert str(calls[0].url) == 'https://api.razorpay.com/v1/orders'
    assert calls[0].headers['Authorization'].startswith('Basic ')
    assert json.loads(calls[0].content)['amount'] == 12345


def test_lost_order_cancelled_before_webhook_cannot_activate_membership(api):
    quote = api[0].get('/api/v1/memberships/gyms/1/plans/1/wallet-quote', headers=api[1][1]).json()
    api[3].timeout_after_create = True
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'cancel-lost-order'},
        json={'kind': 'SINGLE_GYM', 'gym_id': 1, 'plan_id': 1, 'accepted_quote': quote['quote_token']})
    assert response.status_code == 503
    with Session(api[2]) as db:
        record = db.scalar(select(PaymentCheckout)); record.status = 'CANCELLED'; record_id = record.id
        db.commit()
    assert webhook(api, api[3].pay({'razorpay_order_id': 'order_1'})).status_code == 200
    assert refresh(api, {'id': record_id}).json()['status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(UserMembership.id))) == 0