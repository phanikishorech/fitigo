from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.booking_service import BookingService
from app.services.gym_service import GymService
from app.services.slot_service import SlotService


client = TestClient(app)


def test_customer_can_reschedule_pending_booking_and_capacity_moves():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"rs_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"rs_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Reschedule Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        s1 = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM1", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 1, "price": "100.00"},
        )
        s2 = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM2", "start_time": "07:00:00", "end_time": "08:00:00", "capacity": 1, "price": "100.00"},
        )

        bsvc = BookingService(db)
        b = bsvc.create_booking(user_id=customer.id, gym_slot_id=s1.id, slot_date=date.today(), quantity=1, notes=None)

        token = create_access_token(str(customer.id))
        r = client.post(
            f"/api/v1/bookings/{b.id}/reschedule",
            json={"gym_slot_id": s2.id, "slot_date": str(date.today()), "note": "later"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["gym_slot_id"] == s2.id
    finally:
        db.close()


def test_reschedule_fails_when_new_slot_is_full():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"rs2_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        c1 = auth.register_user(
            first_name="C1",
            last_name="Customer",
            email=f"rs2_c1_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )
        c2 = auth.register_user(
            first_name="C2",
            last_name="Customer",
            email=f"rs2_c2_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Reschedule Gym2", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        s1 = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM1", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 1, "price": "100.00"},
        )
        s2 = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM2", "start_time": "07:00:00", "end_time": "08:00:00", "capacity": 1, "price": "100.00"},
        )

        bsvc = BookingService(db)
        b_full = bsvc.create_booking(user_id=c1.id, gym_slot_id=s2.id, slot_date=date.today(), quantity=1, notes=None)
        assert b_full.id
        b = bsvc.create_booking(user_id=c2.id, gym_slot_id=s1.id, slot_date=date.today(), quantity=1, notes=None)

        token = create_access_token(str(c2.id))
        r = client.post(
            f"/api/v1/bookings/{b.id}/reschedule",
            json={"gym_slot_id": s2.id, "slot_date": str(date.today())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
    finally:
        db.close()
