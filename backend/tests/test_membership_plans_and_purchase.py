from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.gym_service import GymService


client = TestClient(app)


def test_owner_can_create_plan_and_customer_can_purchase_and_list_memberships():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"m_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"m_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "MemGym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        owner_token = create_access_token(str(owner.id))
        rp = client.post(
            f"/api/v1/memberships/gyms/{gym.id}/plans",
            json={"name": "Monthly", "duration_days": 30, "price": "999.00", "currency": "INR"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert rp.status_code == 200
        plan_id = rp.json()["id"]

        rcust = create_access_token(str(customer.id))
        rbuy = client.post(
            f"/api/v1/memberships/gyms/{gym.id}/purchase",
            json={"plan_id": plan_id},
            headers={"Authorization": f"Bearer {rcust}"},
        )
        assert rbuy.status_code == 200

        rlist = client.get(
            "/api/v1/memberships/me",
            headers={"Authorization": f"Bearer {rcust}"},
        )
        assert rlist.status_code == 200
        assert len(rlist.json()) >= 1
    finally:
        db.close()
