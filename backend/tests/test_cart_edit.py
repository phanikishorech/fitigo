"""Unpaid visit edits are in-place, owner-scoped and transactional."""
from datetime import time
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_booking_access_qr import api
from test_booking_time import clock, gym_body, add_class, snapshot
from app.models.cart import CartItem
from app.models.gym import Gym, GymOperatingHours
from app.models.class_booking import ClassSession


def create(api, body=None, kind='gym'):
    response = api[0].post('/api/v1/cart/items/' + kind, headers=api[1][1], json=body or gym_body())
    assert response.status_code == 200, response.text
    return response.json()


def payload(item, **changes):
    body = dict(booking_type=item['booking_type'], gym_id=item['gym_id'], booking_date=item['booking_date'],
                member_count=item['member_count'], visitor_names=item['visitor_names'], expected_updated_at=item['updated_at'])
    if item['booking_type'] == 'GYM': body['preferred_start_time'] = item['preferred_start_time']
    else: body['class_session_id'] = item['class_session_id']
    return {**body, **changes}


def test_edit_in_place_reprices_changes_names_and_time_without_payment(api, clock):
    client, headers, engine = api
    item = create(api)
    before = snapshot(engine)
    with Session(engine) as db:
        db.get(Gym, 1).gym_price_per_person = 125; db.commit()
    response = client.put(f"/api/v1/cart/items/{item['id']}", headers=headers[1],
        json=payload(item, preferred_start_time='14:15', member_count=2, visitor_names=['Alice Example', 'Bob Example']))
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['id'] == item['id']
    assert updated['preferred_start_time'] == '14:15:00' and updated['preferred_end_time'] == '15:15:00'
    assert updated['visitor_names'] == ['Alice Example', 'Bob Example']
    assert updated['price_per_person'] == '125.00' and updated['total_price'] == '250.00'
    assert updated['can_edit'] is True and updated['updated_at'] != item['updated_at']
    assert snapshot(engine) == before
    assert client.get('/api/v1/cart/summary', headers=headers[1]).json() == {'count': 1}
    with Session(engine) as db: assert db.scalar(select(func.count(CartItem.id))) == 1


def test_auth_owner_scope_and_summary(api, clock):
    client, headers, _ = api; item = create(api); path = f"/api/v1/cart/items/{item['id']}"
    assert client.get(path).status_code == 401
    assert client.put(path, json=payload(item)).status_code == 401
    assert client.get('/api/v1/cart/summary').status_code == 401
    assert client.get(path, headers=headers[4]).status_code == 404
    assert client.put(path, headers=headers[4], json=payload(item)).status_code == 404
    assert client.get('/api/v1/cart/summary', headers=headers[4]).json()['count'] == 0


@pytest.mark.parametrize('status', ['PAYMENT_PENDING', 'CONFIRMED', 'REMOVED'])
def test_non_draft_cannot_be_edited_or_counted(api, clock, status):
    client, headers, engine = api; item = create(api)
    with Session(engine) as db:
        db.get(CartItem, item['id']).status = status; db.commit()
    path = f"/api/v1/cart/items/{item['id']}"
    assert client.get(path, headers=headers[1]).json()['can_edit'] is False
    assert client.put(path, headers=headers[1], json=payload(item)).status_code == 409
    assert client.get('/api/v1/cart/summary', headers=headers[1]).json()['count'] == 0


def test_checkout_link_blocks_even_active_item(api, clock):
    client, headers, engine = api; item = create(api)
    with Session(engine) as db:
        # SQLite fixture intentionally permits a synthetic checkout reference.
        db.get(CartItem, item['id']).checkout_id = 'test-pending-checkout'; db.commit()
    assert client.put(f"/api/v1/cart/items/{item['id']}", headers=headers[1], json=payload(item)).status_code == 409
    assert client.get('/api/v1/cart/summary', headers=headers[1]).json()['count'] == 0


@pytest.mark.parametrize('changes', [dict(preferred_start_time='11:00'), dict(preferred_start_time='13:13'),
    dict(preferred_end_time='16:00'), dict(visitor_names=['']), dict(member_count=2), dict(gym_id=2),
    dict(booking_type='CLASS', class_session_id=1), dict(total_price='1.00')])
def test_invalid_edits_leave_original_intact(api, clock, changes):
    client, headers, _ = api; item = create(api); path = f"/api/v1/cart/items/{item['id']}"
    response = client.put(path, headers=headers[1], json=payload(item, **changes))
    assert response.status_code in [400, 422], response.text
    assert client.get(path, headers=headers[1]).json() == item


def test_stale_edit_and_collision_are_rejected(api, clock):
    client, headers, _ = api; item = create(api); path = f"/api/v1/cart/items/{item['id']}"
    create(api, gym_body(start='14:00', end='15:00'))
    assert client.put(path, headers=headers[1], json=payload(item, preferred_start_time='14:00')).status_code == 409
    response = client.put(path, headers=headers[1], json=payload(item, visitor_names=['Changed name']))
    assert response.status_code == 200
    assert client.put(path, headers=headers[1], json=payload(item)).status_code == 409
    assert client.get(path, headers=headers[1]).json()['visitor_names'] == ['Changed name']


def test_closed_or_inactive_gym_cannot_be_saved(api, clock):
    client, headers, engine = api; item = create(api); path = f"/api/v1/cart/items/{item['id']}"
    with Session(engine) as db:
        for h in db.scalars(select(GymOperatingHours).where(GymOperatingHours.gym_id == 1)): h.is_closed = True
        db.commit()
    assert client.put(path, headers=headers[1], json=payload(item)).status_code == 400
    with Session(engine) as db: db.get(Gym, 1).is_active = False; db.commit()
    assert client.put(path, headers=headers[1], json=payload(item)).status_code == 409


def test_class_edit_switches_session_checks_capacity_without_reserving(api, clock):
    client, headers, engine = api
    first = add_class(api); item = create(api, first, 'class')
    second = add_class(api, start=time(16))
    response = client.put(f"/api/v1/cart/items/{item['id']}", headers=headers[1],
        json=payload(item, class_session_id=second['class_session_id'], member_count=2, visitor_names=['Alice', 'Bob']))
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['start_time'] == '16:00:00' and updated['total_price'] == '200.00'
    with Session(engine) as db:
        session = db.get(ClassSession, second['class_session_id'])
        assert session.booked_capacity == 0
        session.maximum_capacity = 1; db.commit()
    assert client.put(f"/api/v1/cart/items/{item['id']}", headers=headers[1], json=payload(updated)).status_code == 409