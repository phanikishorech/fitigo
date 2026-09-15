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


def test_admin_can_cancel_booking_and_daily_report_includes_day():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        admin = auth.register_user(
            first_name="A",
            last_name="Admin",
            email=f"admin_ops_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_ADMIN,
        )
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"owner_ops_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"cust_ops_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Ops Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 10, "price": "100.00"},
        )

        bsvc = BookingService(db)
        b = bsvc.create_booking(user_id=customer.id, gym_slot_id=slot.id, slot_date=date.today(), quantity=1, notes=None)

        token = create_access_token(str(admin.id))
        rc = client.post(
            f"/api/v1/admin/bookings/{b.id}/cancel",
            json={"reason": "support"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rc.status_code == 200

        rr = client.get(
            "/api/v1/admin/reports/bookings/daily",
            params={"gym_id": gym.id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rr.status_code == 200
        assert any(row["day"] == str(date.today()) for row in rr.json())
    finally:
        db.close()
