"""Conservative class policy through real services/routes, disposable SQLite only."""
from datetime import timedelta, time
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.class_booking import ClassSession, GymClass
from app.models.slot import GymSlot
from app.models.booking import Booking
from app.models.cart import CartItem
from app.services.slot_service import SlotService
from app.services import class_sync_service
from app.routers import gym_owner, gyms_public
from test_booking_access_qr import api as booking_api, NOW


@pytest.fixture
def api(booking_api, monkeypatch):
    monkeypatch.setattr(class_sync_service, 'ist_now', lambda: NOW)
    for router in [gym_owner.router, gyms_public.router]: booking_api[0].app.include_router(router, prefix='/api/v1')
    return booking_api


def schedule(api):
    with Session(api[2]) as db:
        slot = SlotService(db).create_slot(owner_user_id=2, gym_id=1, data={
            'name': 'Yoga', 'start_time': time(14), 'end_time': time(15), 'capacity': 10,
            'price': '100', 'specific_date': NOW.date()+timedelta(days=2)})
        sid = slot.id
        session = db.scalar(select(ClassSession).where(ClassSession.source_slot_id == sid))
        cid = session.id
        db.add(ClassSession(source_slot_id=sid, gym_class_id=session.gym_class_id,
            session_date=NOW.date()-timedelta(days=1), start_time=time(14), end_time=time(15),
            maximum_capacity=10, booked_capacity=3, price_per_person=100, status='CLOSED'))
        db.commit()
        return sid, cid


def test_future_unbooked_session_updates_atomically_without_rewriting_history(api):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        db.add(CartItem(user_id=1, gym_id=1, class_session_id=cid, booking_type='CLASS',
            booking_date=NOW.date()+timedelta(days=2), member_count=1, price_per_person=100, total_price=100))
        db.commit()
        SlotService(db).update_slot(owner_user_id=2, slot_id=sid,
            data={'name': 'Pilates', 'start_time': '16:00', 'end_time': '17:00', 'price': '150', 'capacity': 8})
        future = db.get(ClassSession, cid)
        past = db.scalar(select(ClassSession).where(ClassSession.source_slot_id == sid, ClassSession.id != cid))
        assert (future.start_time, future.end_time, future.price_per_person, future.maximum_capacity) == (time(16), time(17), Decimal('150'), 8)
        assert db.get(GymClass, future.gym_class_id).class_name == 'Pilates'
        assert (past.start_time, past.price_per_person, past.booked_capacity, past.status) == (time(14), Decimal('100'), 3, 'CLOSED')
        assert db.get(GymClass, past.gym_class_id).class_name == 'Yoga'
        assert db.scalar(select(CartItem.status)) == 'REMOVED'


@pytest.mark.parametrize('reserved', ['booked_capacity', 'payment_pending', 'confirmed_cart', 'booking_metadata'])
@pytest.mark.parametrize('deactivate', [False, True])
def test_reserved_session_blocks_entire_edit_or_deactivation(api, reserved, deactivate):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        future = db.get(ClassSession, cid)
        if reserved == 'booked_capacity': future.booked_capacity = 1
        elif reserved == 'booking_metadata':
            db.add(Booking(user_id=1, gym_id=1, gym_slot_id=1, slot_date=future.session_date,
                quantity=1, unit_price=100, total_price=100, status='PENDING_PAYMENT', expires_at=NOW,
                notes=f'class_session_id={cid}'))
        else:
            db.add(CartItem(user_id=1, gym_id=1, class_session_id=cid, booking_type='CLASS',
                booking_date=future.session_date, member_count=1, price_per_person=100, total_price=100,
                status='PAYMENT_PENDING' if reserved == 'payment_pending' else 'CONFIRMED'))
        # Include a second unbooked future session: no partial synchronization.
        db.add(ClassSession(source_slot_id=sid, gym_class_id=future.gym_class_id,
            session_date=future.session_date+timedelta(days=1), start_time=time(14), end_time=time(15),
            maximum_capacity=10, booked_capacity=0, price_per_person=100, status='AVAILABLE'))
        db.commit()
        with pytest.raises(HTTPException) as error:
            if deactivate: SlotService(db).deactivate_slot(owner_user_id=2, slot_id=sid)
            else: SlotService(db).update_slot(owner_user_id=2, slot_id=sid, data={'price': '150', 'capacity': 8})
        assert error.value.status_code == 409 and error.value.detail['code'] == 'CLASS_HAS_RESERVATIONS'
        assert db.get(GymSlot, sid).price == 100 and db.get(GymSlot, sid).is_active == 1
        assert all(s.price_per_person == 100 for s in db.scalars(select(ClassSession).where(ClassSession.source_slot_id == sid)))


def test_deactivation_prevents_new_bookings_but_does_not_rewrite_past(api):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        SlotService(db).deactivate_slot(owner_user_id=2, slot_id=sid)
        assert db.get(ClassSession, cid).status == 'CANCELLED'
        assert db.scalar(select(ClassSession.status).where(ClassSession.source_slot_id == sid, ClassSession.id != cid)) == 'CLOSED'
    response = api[0].post('/api/v1/cart/items/class', headers=api[1][1], json={
        'booking_type': 'CLASS', 'gym_id': 1, 'class_session_id': cid,
        'booking_date': str(NOW.date()+timedelta(days=2)), 'member_count': 1, 'visitor_names': ['Test visitor']})
    assert response.status_code == 400
    with Session(api[2]) as db: assert db.scalar(select(func.count(CartItem.id))) == 0


def test_legacy_links_and_schedule_edits_fail_explicitly(api):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        db.get(GymSlot, sid).sync_kind = 'LEGACY'; db.commit()
        with pytest.raises(HTTPException) as error:
            SlotService(db).update_slot(owner_user_id=2, slot_id=sid, data={'price': '200'})
        assert error.value.detail['code'] == 'CLASS_LINK_RECONCILIATION_REQUIRED'
        assert db.get(ClassSession, cid).price_per_person == 100
        with pytest.raises(HTTPException) as error:
            SlotService(db).update_slot(owner_user_id=2, slot_id=sid, data={'repeat_days': [1]})
        assert error.value.status_code == 409


def test_owner_scope_duplicate_schedule_and_invalid_change_preserve_records(api):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        with pytest.raises(HTTPException) as error:
            SlotService(db).deactivate_slot(owner_user_id=5, slot_id=sid)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException):
            SlotService(db).update_slot(owner_user_id=2, slot_id=sid, data={'end_time': '13:00'})
        db.rollback()
        before = db.scalar(select(func.count(GymSlot.id)))
        with pytest.raises(HTTPException) as error:
            SlotService(db).create_slot(owner_user_id=2, gym_id=1, data={'name': 'Yoga',
                'start_time': '14:00', 'end_time': '15:00', 'capacity': 10, 'price': '100',
                'specific_date': NOW.date()+timedelta(days=2)})
        assert error.value.status_code == 409
        assert db.scalar(select(func.count(GymSlot.id))) == before
        assert db.get(ClassSession, cid).end_time == time(15)


def test_started_sessions_and_reactivation_never_rewrite_history(api):
    sid, cid = schedule(api)
    with Session(api[2]) as db:
        future = db.get(ClassSession, cid)
        started = ClassSession(source_slot_id=sid, gym_class_id=future.gym_class_id,
            session_date=NOW.date(), start_time=time(10), end_time=time(13), maximum_capacity=10,
            booked_capacity=1, price_per_person=100, status='AVAILABLE')
        db.add(started); db.commit(); started_id=started.id
        SlotService(db).deactivate_slot(owner_user_id=2, slot_id=sid)
        assert db.get(ClassSession,started_id).status=='AVAILABLE'
        assert db.get(ClassSession,cid).status=='CANCELLED'
        SlotService(db).update_slot(owner_user_id=2,slot_id=sid,data={'is_active':True})
        assert db.get(ClassSession,cid).status=='CANCELLED'
        assert db.get(ClassSession,started_id).price_per_person==100