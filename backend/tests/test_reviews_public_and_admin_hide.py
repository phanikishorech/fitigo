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


def test_customer_can_review_after_confirmed_booking_and_admin_can_hide():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        admin = auth.register_user(
            first_name="A",
            last_name="Admin",
            email=f"rev_admin_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_ADMIN,
        )
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"rev_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"rev_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "RevGym", "city": "X"})
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
        bsvc.pay_dummy(user_id=customer.id, booking_id=b.id)

        # Visit must be verified/completed by the gym (attendance marked).
        # Use the owner-facing attendance mark method (used by gym_owner router) to simulate a completed visit.
        bsvc.owner_mark_attendance(owner_user_id=owner.id, booking_id=b.id, attendance_status="ATTENDED", note="ok")

        cust_token = create_access_token(str(customer.id))
        rr = client.post(
            f"/api/v1/gyms/{gym.id}/reviews",
            json={"rating": 5, "comment": "great"},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert rr.status_code == 200
        review_id = rr.json()["id"]

        # visible publicly
        rpub = client.get(f"/api/v1/gyms/{gym.id}/reviews")
        assert rpub.status_code == 200
        assert any(x["id"] == review_id for x in rpub.json())

        admin_token = create_access_token(str(admin.id))
        rh = client.post(
            f"/api/v1/admin/reviews/{review_id}/hide",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rh.status_code == 200

        rpub2 = client.get(f"/api/v1/gyms/{gym.id}/reviews")
        assert rpub2.status_code == 200
        assert all(x["id"] != review_id for x in rpub2.json())
    finally:
        db.close()
