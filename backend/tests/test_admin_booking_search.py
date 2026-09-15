from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.core.roles import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.booking_service import BookingService
from app.services.gym_service import GymService
from app.services.slot_service import SlotService


client = TestClient(app)


def test_admin_can_search_bookings_by_gym_and_status():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        admin = auth.register_user(
            first_name="A",
            last_name="Admin",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_ADMIN,
        )
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"cust_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "AdminSearch Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 10, "price": "100.00"},
        )

        booking_svc = BookingService(db)
        b = booking_svc.create_booking(
            user_id=customer.id,
            gym_slot_id=slot.id,
            slot_date=date.today(),
            quantity=1,
            notes=None,
        )

        token = create_access_token(str(admin.id))
        r = client.get(
            "/api/v1/admin/bookings",
            params={"gym_id": gym.id, "status": "PENDING_PAYMENT"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert b.id in ids

    finally:
        db.close()
