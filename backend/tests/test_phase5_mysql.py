"""Owner duplicate transitions and read models on actual isolated MySQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.booking import Booking, Payment
from app.models.slot import SlotAvailability
from app.models.gym import GymStatusHistory
from app.services.booking_service import BookingService
from app.services.owner_member_service import OwnerMemberService
from app.routers import admin, workflow_capabilities
from test_owner_dashboard_mysql import mysql_api, booking, DAY, pytestmark


def test_concurrent_owner_cancel_releases_capacity_once_and_preserves_payment(mysql_api):
    engine=mysql_api[2]
    with Session(engine) as db:
        b=booking(db,1,day=DAY+timedelta(days=100));b.status='CONFIRMED';b.attendance_status=None
        db.add(Payment(booking_id=b.id,status='PAID',provider='DUMMY',amount=b.total_price,currency='INR'))
        av=SlotAvailability(gym_slot_id=b.gym_slot_id,slot_date=b.slot_date,booked_count=4,blocked_count=0,status='AVAILABLE')
        db.add(av);db.commit();bid=b.id;aid=av.id;quantity=b.quantity
    barrier=Barrier(2)
    def cancel(_):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            return BookingService(db).owner_cancel_booking(owner_user_id=1,booking_id=bid).status
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(cancel,range(2)))==['CANCELLED','CANCELLED']
    with Session(engine) as db:
        assert db.get(SlotAvailability,aid).booked_count==4-quantity
        assert db.get(Booking,bid).notes.count('Owner cancellation actor=')==1
        assert db.scalar(select(Payment.status).where(Payment.booking_id==bid))=='PAID'


def test_member_directory_and_audit_union_run_on_strict_mysql(mysql_api):
    client,headers,engine=mysql_api
    with Session(engine) as db:
        b=booking(db,1,day=DAY);db.add(GymStatusHistory(gym_id=1,old_status='DRAFT',new_status='APPROVED',changed_by_user_id=1))
        db.commit()
        service=OwnerMemberService(db,1,1)
        result=service.directory('',1,0);assert result['total']==1 and result['items'][0]['id']==3
        assert service.history(3,20,0)['booking_total']==1
    # Invoke the protected router through a test client with an actual admin role.
    from app.models.auth import Role,UserRole
    with Session(engine) as db:
        db.add(Role(id=99,name='ADMIN'));db.flush();db.add(UserRole(user_id=1,role_id=99));db.commit()
    client.app.include_router(admin.router,prefix='/api/v1')
    client.app.include_router(workflow_capabilities.router,prefix='/api/v1')
    assert client.get('/api/v1/admin/audit-logs',headers=headers[1]).status_code==200
    assert client.get('/api/v1/admin/settings',headers=headers[1]).status_code==200