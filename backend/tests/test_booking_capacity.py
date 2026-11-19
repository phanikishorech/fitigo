from __future__ import annotations

from app.core.time import ist_today
from datetime import timedelta

from datetime import date
import uuid

from fastapi.testclient import TestClient

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.gym_service import GymService
from app.services.slot_service import SlotService


client = TestClient(app)


def test_booking_capacity_and_cancel_releases_capacity():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"cap_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"cap_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "Cap Gym", "city": "X"})
        gym_svc.submit_for_approval(owner_user_id=owner.id, gym_id=gym.id)
        # force approved for this isolated test (no admin flow here)
        gym.status = "APPROVED"
        gym.is_active = True  # Submission deliberately disables public booking until approval.
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={
                "name": "Morning",
                "start_time": "06:00:00",
                "end_time": "07:00:00",
                "capacity": 2,
                "price": "100.00",
            },
        )

        token = create_access_token(str(customer.id))
        # Book 2 -> ok
        r = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str((ist_today() + timedelta(days=1))), "quantity": 2},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        booking_id = r.json()["id"]

        # Book 1 more -> should fail
        r2 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str((ist_today() + timedelta(days=1))), "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 400

        # Pending purchases cannot use paid-booking cancellation or receive credit.
        assert client.post(f'/api/v1/bookings/{booking_id}/cancel', json={}, headers={'Authorization': f'Bearer {token}'}).status_code == 409
        from policy_fixtures import fund_wallet_booking
        db.rollback()  # End the pre-request MySQL snapshot before reading the committed booking.
        fund_wallet_booking(db, booking_id); db.commit()
        # Verified confirmed booking cancellation releases capacity and credits once.
        rc = client.post(
            f"/api/v1/bookings/{booking_id}/cancel",
            json={"reason": "changed mind"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rc.status_code == 200
        assert rc.json()["status"] == "CANCELLED"
        assert rc.json()['cancellation']['wallet_credit_amount'] == '200.00'

        # Book again -> ok
        r3 = client.post(
            "/api/v1/bookings",
            json={"gym_slot_id": slot.id, "slot_date": str((ist_today() + timedelta(days=1))), "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r3.status_code == 200
    finally:
        db.close()
