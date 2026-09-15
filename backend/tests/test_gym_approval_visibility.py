from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.roles import ROLE_ADMIN, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.gym_service import GymService


client = TestClient(app)


def test_unapproved_gym_not_visible_until_approved():
    if SessionLocal is None:
        # DB not configured
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)

        # Create users
        admin_email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
        owner_email = f"owner_{uuid.uuid4().hex[:8]}@example.com"

        admin = auth.register_user(
            first_name="A",
            last_name="Admin",
            email=admin_email,
            phone=None,
            password="password1234",
            role_name=ROLE_ADMIN,
        )
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=owner_email,
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )

        # Create gym and submit
        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": f"Gym {uuid.uuid4().hex[:6]}", "city": "X"})
        gym = gym_svc.submit_for_approval(owner_user_id=owner.id, gym_id=gym.id)
        assert gym.status == "PENDING_APPROVAL"

        # Public listing should not include it
        r = client.get("/api/v1/gyms")
        assert r.status_code == 200
        assert all(item["id"] != gym.id for item in r.json())

        # Approve as admin
        admin_token = create_access_token(str(admin.id))
        r2 = client.post(
            f"/api/v1/admin/gyms/{gym.id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r2.status_code == 200

        # Now public listing should include it
        r3 = client.get("/api/v1/gyms")
        assert r3.status_code == 200
        assert any(item["id"] == gym.id for item in r3.json())
    finally:
        db.close()
