from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.models.booking import Booking
from app.services.auth_service import AuthService
from app.services.gym_service import GymService
from app.services.slot_service import SlotService


client = TestClient(app)


def test_booking_idempotency_key_returns_same_booking_and_does_not_double_reserve():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"idem_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"idem_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Idem Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={
                "name": "Evening",
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "capacity": 3,
                "price": "100.00",
            },
        )

        token = create_access_token(str(customer.id))
        idem = "test-" + uuid.uuid4().hex

        r1 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str(date.today()), "quantity": 2},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem},
        )
        assert r1.status_code == 200
        bid1 = r1.json()["id"]

        r2 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str(date.today()), "quantity": 2},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem},
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == bid1

    finally:
        db.close()


def test_expired_pending_booking_releases_capacity_on_next_booking_attempt():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"exp_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"exp_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Expiry Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={
                "name": "Morning",
                "start_time": "06:00:00",
                "end_time": "07:00:00",
                "capacity": 1,
                "price": "100.00",
            },
        )

        token = create_access_token(str(customer.id))
        r1 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str(date.today()), "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200
        bid = r1.json()["id"]

        # Force expire in DB
        # Ensure we can see the row committed by the API request (separate DB session).
        db.rollback()
        b = db.get(Booking, bid)
        if b is None:
            # Extremely defensive: in some MySQL isolation/autobegin scenarios,
            # the identity map may not refresh immediately. Re-query explicitly.
            b = db.execute(select(Booking).where(Booking.id == bid)).scalars().first()
        assert b is not None
        b.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        # Next booking should succeed because create_booking expires old one while holding the slot lock
        r2 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str(date.today()), "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200

    finally:
        db.close()
