"""Payment ownership tests using existing isolated DB and test gateway fixtures."""
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment_checkout import PaymentCheckout
from test_razorpay_payments import api, booking_api, checkout, create_booking


def test_other_customer_cannot_read_verify_refresh_cancel_checkout(api):
    client, headers, engine, gateway = api
    record = checkout(api)
    url = '/api/v1/payments/checkouts/' + record['id']
    assert client.get(url, headers=headers[4]).status_code == 404
    for action in ('verify', 'refresh', 'cancel'):
        assert client.post(url+'/'+action, headers=headers[4], json={}).status_code == 404
    assert client.get('/api/v1/payments/checkouts?user_id=1', headers=headers[4]).json() == []
    assert client.get('/api/v1/payments/history?user_id=1', headers=headers[4]).json()['items'] == []
    assert gateway.creations == 1
    with Session(engine) as db:
        assert db.get(PaymentCheckout, record['id']).status == 'PENDING'
        assert db.get(Booking, record['booking_ids'][0]).status == 'PENDING_PAYMENT'


def test_checkout_source_owner_and_prices_cannot_be_supplied_by_browser(api):
    client, headers, _, gateway = api
    booking = create_booking(api)
    response = client.post('/api/v1/payments/checkouts', headers={**headers[4], 'Idempotency-Key': 'other-customer'},
                           json={'kind': 'BOOKING', 'booking_id': booking['id']})
    assert response.status_code == 404
    for extra in ({'user_id': 4}, {'owner_id': 2}, {'amount': 1}, {'role': 'ADMIN'}):
        response = client.post('/api/v1/payments/checkouts', headers={**headers[1], 'Idempotency-Key': 'tampered-purchase'},
                               json={'kind': 'BOOKING', 'booking_id': booking['id'], **extra})
        assert response.status_code == 422
    for uid in (2, 3, 5):
        assert client.get('/api/v1/payments/history', headers=headers[uid]).status_code == 403
    assert gateway.creations == 0


def test_platform_order_access_and_payment_session_are_customer_scoped(api):
    client, headers, _, gateway = api
    response = client.post('/api/v1/memberships/orders', headers={**headers[1], 'Idempotency-Key': 'security-order'},
                           json={'plan_id': 1})
    assert response.status_code == 200
    order = response.json()
    url = '/api/v1/memberships/orders/'+order['id']
    assert client.get(url, headers=headers[1]).status_code == 200
    assert client.get(url, headers=headers[4]).status_code == 404
    assert client.post(url+'/payment-session', headers=headers[4], json={'accepted_quote': order['quote_token']}).status_code == 404
    assert client.get('/api/v1/admin/membership-plans', headers=headers[1]).status_code == 403
    assert gateway.creations == 0