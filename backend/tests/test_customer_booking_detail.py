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


def test_customer_can_get_own_booking_detail_and_not_others():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"own_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        c1 = auth.register_user(
            first_name="C1",
            last_name="Customer",
            email=f"c1_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )
        c2 = auth.register_user(
            first_name="C2",
            last_name="Customer",
            email=f"c2_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Cust Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 10, "price": "100.00"},
        )

        bsvc = BookingService(db)
        b = bsvc.create_booking(user_id=c1.id, gym_slot_id=slot.id, slot_date=date.today(), quantity=1, notes=None)

        t1 = create_access_token(str(c1.id))
        r = client.get(f"/api/v1/bookings/{b.id}", headers={"Authorization": f"Bearer {t1}"})
        assert r.status_code == 200
        assert r.json()["id"] == b.id

        t2 = create_access_token(str(c2.id))
        r2 = client.get(f"/api/v1/bookings/{b.id}", headers={"Authorization": f"Bearer {t2}"})
        assert r2.status_code == 404
    finally:
        db.close()
