from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.roles import ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.gym_service import GymService
from app.services.slot_service import SlotService


def test_owner_can_list_slots_for_own_gym():
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

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "SlotGym", "city": "X"})

        slot_svc = SlotService(db)
        slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "Morning", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 10, "price": "99"},
        )

        r = client.get(f"/api/v1/gym-owner/gyms/{gym.id}/slots", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "Morning"
        assert data[0]["gym_id"] == gym.id
    finally:
        db.close()
