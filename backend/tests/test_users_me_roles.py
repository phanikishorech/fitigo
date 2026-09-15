from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.roles import ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import create_app
from app.services.auth_service import AuthService


def test_users_me_roles_returns_role_names():
    if SessionLocal is None:
        return

    app = create_app()
    client = TestClient(app)

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        token = create_access_token(str(owner.id))

        r = client.get("/api/v1/users/me/roles", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        roles = r.json()
        assert ROLE_GYM_OWNER in roles
    finally:
        db.close()
