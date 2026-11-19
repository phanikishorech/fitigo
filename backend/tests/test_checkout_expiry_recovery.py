"""Mocked gateway/API regressions; run only through the disposable DB runner."""
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment_checkout import PaymentCheckout
from app.services import payment_checkout_service
from test_cashfree_payments import api, razorpay_api, booking_api, checkout, refresh, source_for


def expire(api, record):
    with Session(api[2]) as db:
        for booking in db.scalars(select(Booking).where(Booking.checkout_id == record['id'])):
            booking.expires_at = payment_checkout_service.datetime.utcnow() - timedelta(seconds=1)
        db.commit()


def test_expired_booking_keeps_financial_state_and_returns_checkout_snapshot(api):
    record = checkout(api, source_for(api, 'CART'))
    source_for(api, 'CART')  # New cart items must not change the original amount.
    expire(api, record)
    calls = len(api[3].calls)
    result = api[0].get(f"/api/v1/payments/checkouts/{record['id']}", headers=api[1][1]).json()
    assert len(api[3].calls) == calls  # Serialization is read-only, no provider calls.
    assert result['status'] == 'PENDING' and not result['can_pay']
    assert result['payment_blocked_reason'] == 'BOOKING_EXPIRED'
    assert result['payment_expires_at'].endswith('Z')
    assert not result['can_cancel'] and not result['replacement_safe']
    assert len(result['items']) == len(result['cart_item_ids']) == 1
    assert result['items'][0]['amount'] == result['amount'] == '200.00'
    resumed = checkout(api, {'kind': 'CART'}, key='new-browser-key')
    assert resumed['id'] == record['id'] and api[3].creations == 1
    # Explicit cancellation now requests Cashfree termination, rather than
    # requiring a support operator to close the order beforehand.
    closed = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert closed.status_code == 200
    assert closed.json()['status'] == 'CANCELLED' and closed.json()['replacement_safe']
    assert any(call.method == 'PATCH' for call in api[3].calls)


@pytest.mark.parametrize('state', ['ACTIVE', 'TERMINATION_REQUESTED', 'EXPIRED'])
def test_processing_attempt_blocks_reopen_and_cancellation(api, state):
    record = checkout(api)
    api[3].pay(record, 'PENDING')
    api[3].orders[record['gateway_order_id']]['order_status'] = state
    result = refresh(api, record).json()
    assert result['payment_blocked_reason'] == 'PAYMENT_PROCESSING'
    assert not result['can_pay'] and not result['can_cancel']
    response = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1])
    assert response.status_code == 200
    assert response.json()['status'] != 'CANCELLED'
    assert not response.json()['replacement_safe'] and not response.json()['can_pay']
    assert response.json()['payment_blocked_reason'] == 'PAYMENT_PROCESSING'
    assert not any(call.method == 'PATCH' for call in api[3].calls)
    assert api[3].creations == 1


def test_closed_unpaid_requires_explicit_cancel_then_explicit_new_purchase(api):
    record = checkout(api, source_for(api, 'CART'))
    expire(api, record)
    source_for(api, 'CART')
    api[3].orders[record['gateway_order_id']]['order_status'] = 'EXPIRED'
    result = refresh(api, record).json()
    assert result['can_cancel'] and result['replacement_safe'] and not result['can_pay']
    assert checkout(api, {'kind': 'CART'}, key='not-yet-closed')['id'] == record['id']
    closed = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1]).json()
    assert closed['status'] == 'CANCELLED' and closed['replacement_safe']
    assert api[3].creations == 1
    other = checkout(api, {'kind': 'CART'}, key='explicit-new-purchase')
    assert other['id'] != record['id'] and api[3].creations == 2
    assert checkout(api, {'kind': 'CART'}, key='explicit-new-purchase')['id'] == other['id']
    assert api[3].creations == 2


def test_old_local_cancellation_does_not_authorize_replacement(api):
    record = checkout(api, source_for(api, 'CART'))
    with Session(api[2]) as db:
        db.get(PaymentCheckout, record['id']).status = 'CANCELLED'
        db.commit()
    source_for(api, 'CART')
    resumed = checkout(api, {'kind': 'CART'}, key='after-legacy-cancel')
    assert resumed['id'] == record['id']
    assert resumed['payment_blocked_reason'] == 'ORDER_UNRESOLVED'
    assert api[3].creations == 1


def test_timeout_or_late_success_never_authorizes_replacement(api):
    record = checkout(api, source_for(api, 'CART'))
    expire(api, record)
    api[3].unavailable = True
    assert api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1]).status_code == 503
    api[3].unavailable = False
    api[3].pay(record)
    result = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/cancel", headers=api[1][1]).json()
    assert result['status'] == 'REVIEW_REQUIRED' and not result['can_pay']
    assert api[3].creations == 1


def test_ambiguous_creation_cannot_be_cancelled(api):
    api[3].timeout = True
    source = source_for(api, 'CART')
    response = api[0].post('/api/v1/payments/checkouts', headers={**api[1][1], 'Idempotency-Key': 'unknown-create'}, json=source)
    assert response.status_code == 503
    api[3].orders.clear()
    with Session(api[2]) as db:
        identifier = db.scalar(select(PaymentCheckout.id))
    response = api[0].post(f'/api/v1/payments/checkouts/{identifier}/cancel', headers=api[1][1])
    assert response.status_code == 200
    assert response.json()['status'] == 'CREATING'
    assert not response.json()['replacement_safe'] and not response.json()['can_pay']
    assert response.json()['cancellation_requested']
    assert not any(call.method == 'PATCH' for call in api[3].calls)
    assert api[3].creations == 1


def test_missing_attempt_list_does_not_erase_known_processing_payment(api):
    record = checkout(api)
    api[3].pay(record, 'PENDING')
    assert refresh(api, record).json()['payment_blocked_reason'] == 'PAYMENT_PROCESSING'
    api[3].orders[record['gateway_order_id']]['order_status'] = 'EXPIRED'
    api[3].attempts[record['gateway_order_id']] = []
    result = refresh(api, record).json()
    assert not result['replacement_safe'] and not result['can_cancel']
    assert result['payment_blocked_reason'] == 'PAYMENT_PROCESSING'


def test_passed_visit_is_blocked_before_gateway_launch(api, monkeypatch):
    from app.services import booking_time
    from test_cashfree_payments import NOW
    record = checkout(api)
    monkeypatch.setattr(booking_time, 'utcnow', lambda: NOW.replace(hour=11))
    result = refresh(api, record).json()
    assert not result['can_pay'] and result['payment_blocked_reason'] == 'BOOKING_UNAVAILABLE'
    assert api[3].creations == 1