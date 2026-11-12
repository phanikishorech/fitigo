"""Explicit current-cart replacement, isolated transport and database only."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.models.payment_checkout import PaymentCheckout
from app.models.booking import Booking, Payment
from app.core.config import settings
from test_cashfree_payments import api, razorpay_api, booking_api, checkout, source_for
from test_checkout_expiry_recovery import expire
from test_cashfree_payments import NOW


def second_item(api):
    response = api[0].post('/api/v1/cart/items/gym', headers=api[1][1], json={
        'booking_type': 'GYM', 'gym_id': 2, 'booking_date': str(NOW.date()),
        'preferred_start_time': '10:00:00', 'preferred_end_time': '11:00:00',
        'member_count': 2, 'visitor_names': ['Guest One', 'Guest Two']})
    assert response.status_code == 200, response.text


def current(api):
    with Session(api[2]) as db:
        return {'kind': 'CART', 'cart_item_ids': list(db.scalars(select(CartItem.id).where(CartItem.status == 'ACTIVE')))}


def create(api, source, key='fresh-current-cart'):
    return api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': key}, json=source)


@pytest.mark.parametrize('state', ['booking_expired', 'failed', 'gateway_expired'])
def test_current_cart_replaces_old_unpaid_order_and_preserves_history(api, state):
    old = checkout(api, source_for(api, 'CART'))
    if state == 'booking_expired': expire(api, old)
    elif state == 'failed': api[3].pay(old, 'FAILED')
    else: api[3].orders[old['gateway_order_id']]['order_status'] = 'EXPIRED'
    source_for(api, 'CART'); second_item(api)
    source = current(api)
    response = create(api, source)
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh['id'] != old['id'] and fresh['amount'] == '400.00'
    assert fresh['cart_item_ids'] == source['cart_item_ids']
    assert fresh['can_pay'] and len(fresh['items']) == 2 and api[3].creations == 2
    assert create(api, source).json()['id'] == fresh['id']
    assert create(api, source, 'another-browser-key').json()['id'] == fresh['id']
    assert api[3].creations == 2
    with Session(api[2]) as db:
        previous = db.get(PaymentCheckout, old['id'])
        assert previous.status == 'CANCELLED' and previous.checkout_data['replacement_safe']
        assert previous.amount == 200 and previous.snapshot['cart_item_ids'] == old['cart_item_ids']
        assert db.get(Booking, old['booking_ids'][0]).status == 'CANCELLED'
        assert db.scalar(select(Payment.status).where(Payment.booking_id == old['booking_ids'][0])) != 'PAID'


@pytest.mark.parametrize('case', ['processing', 'unknown', 'closing', 'late_success', 'timeout'])
def test_unresolved_payment_never_creates_fresh_order(api, case):
    old = checkout(api, source_for(api, 'CART'))
    expire(api, old)
    source_for(api, 'CART')
    if case == 'processing': api[3].pay(old, 'PENDING')
    if case == 'unknown': api[3].unavailable = True
    if case == 'closing': api[3].termination_state = 'TERMINATION_REQUESTED'
    if case == 'late_success': api[3].success_on_termination = True
    if case == 'timeout': api[3].termination_timeout = True
    response = create(api, current(api))
    assert response.status_code in {409, 503}, response.text
    assert api[3].creations == 1
    with Session(api[2]) as db:
        assert len(list(db.scalars(select(PaymentCheckout)))) == 1
    if case == 'timeout':
        api[3].termination_timeout = False
        assert create(api, current(api)).status_code == 200
        assert api[3].creations == 2


def test_stale_cart_and_foreign_item_ids_fail_before_gateway_mutation(api):
    old = checkout(api, source_for(api, 'CART')); expire(api, old)
    source_for(api, 'CART')
    source = current(api)
    second_item(api)
    calls = len(api[3].calls)
    assert create(api, source).status_code == 409
    assert create(api, {'kind': 'CART', 'cart_item_ids': [99999]}).status_code == 409
    assert len(api[3].calls) == calls and api[3].creations == 1


def test_new_order_uses_current_provider_after_closing_old_cashfree(api, monkeypatch):
    old = checkout(api, source_for(api, 'CART')); expire(api, old)
    source_for(api, 'CART')
    monkeypatch.setattr(settings, 'payment_gateway', 'razorpay')
    response = create(api, current(api))
    assert response.status_code == 200, response.text
    assert response.json()['provider'] == 'RAZORPAY'
    assert api[3].orders[old['gateway_order_id']]['order_status'] == 'TERMINATED'


def test_current_cart_idempotency_rejects_different_items(api):
    source_for(api, 'CART')
    first = create(api, current(api))
    assert first.status_code == 200
    source_for(api, 'CART')
    assert create(api, current(api)).status_code == 409
    assert api[3].creations == 1