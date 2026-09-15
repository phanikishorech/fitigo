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


def test_owner_can_list_only_own_gym_bookings_and_read_details():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner1 = auth.register_user(
            first_name="O1",
            last_name="Owner",
            email=f"o1_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        owner2 = auth.register_user(
            first_name="O2",
            last_name="Owner",
            email=f"o2_{uuid.uuid4().hex[:8]}@example.com",
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
        g1 = gym_svc.create_gym(owner_user_id=owner1.id, data={"name": "Gym 1", "city": "X"})
        g2 = gym_svc.create_gym(owner_user_id=owner2.id, data={"name": "Gym 2", "city": "X"})
        g1.status = "APPROVED"
        g2.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        s1 = slot_svc.create_slot(
            owner_user_id=owner1.id,
            gym_id=g1.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 5, "price": "100.00"},
        )
        s2 = slot_svc.create_slot(
            owner_user_id=owner2.id,
            gym_id=g2.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 5, "price": "100.00"},
        )

        book_svc = BookingService(db)
        b1 = book_svc.create_booking(
            user_id=customer.id,
            gym_slot_id=s1.id,
            slot_date=date.today(),
            quantity=1,
            notes=None,
        )
        _ = book_svc.create_booking(
            user_id=customer.id,
            gym_slot_id=s2.id,
            slot_date=date.today(),
            quantity=1,
            notes=None,
        )

        owner1_token = create_access_token(str(owner1.id))

        r = client.get(
            f"/api/v1/gym-owner/gyms/{g1.id}/bookings",
            headers={"Authorization": f"Bearer {owner1_token}"},
        )
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["id"] == b1.id
        assert items[0]["customer"]["id"] == customer.id

        rd = client.get(
            f"/api/v1/gym-owner/bookings/{b1.id}",
            headers={"Authorization": f"Bearer {owner1_token}"},
        )
        assert rd.status_code == 200
        assert rd.json()["id"] == b1.id

        # Owner1 cannot access owner2 gym bookings
        r_forbidden = client.get(
            f"/api/v1/gym-owner/gyms/{g2.id}/bookings",
            headers={"Authorization": f"Bearer {owner1_token}"},
        )
        assert r_forbidden.status_code == 404
    finally:
        db.close()
