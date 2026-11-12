"""Competing class edit and pending checkout using actual InnoDB row locks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, time
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.time import ist_today
from app.models.class_booking import ClassSession
from app.models.cart import CartItem
from app.services.class_sync_service import lock_cart_class_gyms
from app.services.slot_service import SlotService
from test_owner_dashboard_mysql import mysql_api, pytestmark


def test_edit_and_pending_payment_serialize_without_silent_move(mysql_api):
    engine = mysql_api[2]
    day = ist_today()+timedelta(days=2)
    with Session(engine) as db:
        slot = SlotService(db).create_slot(owner_user_id=1, gym_id=1, data={
            'name':'Concurrent class','start_time':time(14),'end_time':time(15),'capacity':10,'price':'100','specific_date':day})
        sid = slot.id
        session = db.scalar(select(ClassSession).where(ClassSession.source_slot_id == sid)); cid = session.id
        cart = CartItem(user_id=3,gym_id=1,class_session_id=cid,booking_type='CLASS',booking_date=day,
                        member_count=1,price_per_person=100,total_price=100,status='ACTIVE')
        db.add(cart); db.commit(); cart_id = cart.id
    barrier = Barrier(2)
    def edit():
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                SlotService(db).update_slot(owner_user_id=1,slot_id=sid,data={'price':'150'})
                return 'edited'
            except HTTPException as error:
                assert error.detail['code']=='CLASS_HAS_RESERVATIONS'
                return 'blocked'
    def checkout():
        with Session(engine) as db:
            barrier.wait(timeout=10)
            lock_cart_class_gyms(db,3)
            cart=db.scalar(select(CartItem).where(CartItem.id==cart_id).with_for_update().execution_options(populate_existing=True))
            if cart.status!='ACTIVE': return 'removed'
            session=db.scalar(select(ClassSession).where(ClassSession.id==cid).with_for_update())
            assert session.price_per_person==cart.price_per_person==100
            cart.status='PAYMENT_PENDING';db.commit();return 'pending'
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(edit),pool.submit(checkout);result=(a.result(),b.result())
    assert result in {('edited','removed'),('blocked','pending')}
    with Session(engine) as db:
        assert db.get(ClassSession,cid).price_per_person==(150 if result[0]=='edited' else 100)