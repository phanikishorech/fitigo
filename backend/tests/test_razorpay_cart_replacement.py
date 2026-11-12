"""Razorpay replacement is acknowledged local retirement, not gateway closure."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.booking import Booking, Payment
from app.models.payment_checkout import PaymentCheckout
from app.models.access import AccessQrToken
from test_cashfree_payments import razorpay_api, booking_api, checkout, source_for, refresh
from test_checkout_expiry_recovery import expire
from test_current_cart_checkout import current, create


def setup(api):
    old = checkout(api, source_for(api, 'CART'))
    expire(api, old)
    source_for(api, 'CART')
    return old, current(api)


@pytest.mark.parametrize('failed', [False, True])
def test_expired_razorpay_cart_can_be_explicitly_replaced(razorpay_api, failed):
    api = razorpay_api
    old, source = setup(api)
    if failed:
        api[3].pay(old, 'failed')
    response = create(api, source)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'RAZORPAY_REPLACEMENT_CONFIRMATION_REQUIRED'
    assert api[3].creations == 1
    source['confirm_razorpay_replacement'] = True
    response = create(api, source)
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh['id'] != old['id'] and fresh['can_pay'] and api[3].creations == 2
    assert create(api, source).json()['id'] == fresh['id']
    assert create(api, source, 'different-tab-key').json()['id'] == fresh['id']
    previous = refresh(api, old).json()
    assert previous['status'] == 'SUPERSEDED' and not previous['can_pay'] and not previous['replacement_safe']
    assert api[3].orders[old['razorpay_order_id']]['status'] == 'created'  # Not cancelled at provider.
    with Session(api[2]) as db:
        row = db.get(PaymentCheckout, old['id'])
        assert row.snapshot['superseded_by'] == fresh['id']
        assert db.get(Booking, old['booking_ids'][0]).status == 'CANCELLED'
    api[3].pay(fresh)
    assert refresh(api, fresh).json()['status'] == 'PAID'
    api[3].pay(old)
    assert refresh(api, old).json()['status'] == 'REVIEW_REQUIRED'
    with Session(api[2]) as db:
        assert db.get(Booking, old['booking_ids'][0]).status == 'CANCELLED'
        assert db.scalar(select(Payment.status).where(Payment.booking_id == old['booking_ids'][0])) == 'PAID'
        assert db.scalar(select(func.count(AccessQrToken.id))) == 2  # Only replacement access.


@pytest.mark.parametrize('case', ['authorized', 'created', 'captured', 'unknown_status', 'missing_attempts', 'timeout'])
def test_acknowledgment_never_bypasses_payment_checks(razorpay_api, monkeypatch, case):
    api = razorpay_api
    old, source = setup(api)
    source['confirm_razorpay_replacement'] = True
    if case in {'authorized', 'created', 'captured'}:
        api[3].pay(old, case)
    elif case == 'unknown_status':
        api[3].pay(old, 'unexpected')
    elif case == 'missing_attempts':
        api[3].orders[old['razorpay_order_id']]['attempts'] = 1
    else:
        def unavailable(_): raise HTTPException(503, 'Provider unavailable')
        monkeypatch.setattr(api[3], 'order', unavailable)
    response = create(api, source)
    assert response.status_code in {409, 503}, response.text
    assert api[3].creations == 1


def test_late_authorization_blocks_replacement_reopening(razorpay_api):
    api = razorpay_api
    old, source = setup(api)
    source['confirm_razorpay_replacement'] = True
    fresh = create(api, source).json()
    api[3].pay(old, 'authorized')
    response = refresh(api, fresh)
    assert response.status_code == 409
    assert api[3].creations == 2


def test_confirmation_schema_rejects_non_cart_and_coerced_values(razorpay_api):
    api = razorpay_api
    for source in [dict(kind='CART', confirm_razorpay_replacement=True),
                   dict(kind='CART', cart_item_ids=[1], confirm_razorpay_replacement='true')]:
        assert create(api, source).status_code == 422