"""Customer-isolated payment returns; authenticated APIs and mocked providers."""
from urllib.parse import parse_qs, urlsplit
from test_split_payment import api, razorpay_api, cashfree_api, booking_api, balance, create
from test_membership_checkout_recovery import source, recover
from app.core.config import settings
import pytest


def test_new_customer_has_no_other_customers_recovery(api):
    payload = source(api, wallet=False)
    record = create(api, payload).json()
    other = api[0].post('/api/v1/memberships/orders', headers={**api[1][4], 'Idempotency-Key': 'other-customer-order'}, json={'plan_id': 1})
    assert other.status_code == 200, other.text
    own_source = dict(kind='MULTI_GYM', order_id=other.json()['id'])
    result = recover(api, own_source, user=4)
    assert result.status_code == 200 and result.json()['checkout'] is None
    assert record['id'] not in result.text
    response = api[0].post(f"/api/v1/payments/checkouts/{record['id']}/verify", headers=api[1][4], json={})
    assert response.status_code == 404
    assert recover(api, payload, user=4).status_code == 404


def test_cashfree_return_carries_exact_reference_and_verify_is_authoritative(api, monkeypatch):
    if not hasattr(api[3], 'termination_state'): pytest.skip('Cashfree return contract')
    monkeypatch.setattr(settings, 'payment_return_url', 'http://localhost:5173/checkout?context=membership&payment_checkout_id=stale&order_id=stale')
    payload = source(api, wallet=False)
    record = create(api, payload).json()
    url = api[3].orders[record['gateway_order_id']]['order_meta']['return_url']
    parsed = urlsplit(url)
    assert parsed.path == '/checkout'
    assert parse_qs(parsed.query) == {'context': ['membership'], 'payment_checkout_id': [record['id']]}
    path = f"/api/v1/payments/checkouts/{record['id']}/verify"
    pending = api[0].post(path, headers=api[1][1], json={}).json()
    assert pending['status'] == 'PENDING' and pending['membership_id'] is None
    api[3].pay(record)
    paid = api[0].post(path, headers=api[1][1], json={}).json()
    assert paid['status'] == 'PAID' and paid['membership_id']
    assert paid['order_reference'] == payload['order_id']
    order = api[0].get(f"/api/v1/memberships/orders/{payload['order_id']}", headers=api[1][1]).json()
    assert order['payment_status'] == 'PAID' and order['membership_id'] == paid['membership_id']
    assert api[3].creations == 1