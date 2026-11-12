from __future__ import annotations

import uuid
import re
from datetime import date, timedelta

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


def test_owner_can_invite_staff_and_staff_can_list_bookings_for_assigned_gym(monkeypatch):
    if SessionLocal is None:
        return
    from app.core.config import settings
    from app.services import account_delivery
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.fixture.test')
    monkeypatch.setattr(settings, 'smtp_from', 'sender@example.com')
    monkeypatch.setattr(settings, 'public_frontend_url', 'https://app.example.test')
    mail = []
    monkeypatch.setattr(account_delivery, 'send_email', lambda *args: mail.append(args))

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"staff_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"staff_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "StaffGym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        slot_svc = SlotService(db)
        slot = slot_svc.create_slot(
            owner_user_id=owner.id,
            gym_id=gym.id,
            data={"name": "AM", "start_time": "06:00:00", "end_time": "07:00:00", "capacity": 10, "price": "100.00"},
        )
        bsvc = BookingService(db)
        visit_date = date.today()+timedelta(days=1)
        _ = bsvc.create_booking(user_id=customer.id, gym_slot_id=slot.id, slot_date=visit_date, quantity=1, notes=None)

        owner_token = create_access_token(str(owner.id))
        staff_email = f"staff_{uuid.uuid4().hex[:8]}@example.com"
        r = client.post(
            f"/api/v1/gym-owner/gyms/{gym.id}/staff/invite",
            json={"email": staff_email, "first_name": "S", "last_name": "T"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert r.status_code == 200
        token = re.search(r'#token=([A-Za-z0-9_-]+)', mail[-1][2]).group(1)
        assert client.post('/api/v1/auth/staff-invitations/accept', json={'token': token, 'new_password': 'Staff chosen password 123!'}).status_code == 200
        login = client.post('/api/v1/auth/login', json={'email': staff_email, 'password': 'Staff chosen password 123!'})
        assert login.status_code == 200
        staff_token = login.json()['access_token']
        r2 = client.get(
            f"/api/v1/gym-staff/gyms/{gym.id}/bookings",
            params={"date": str(visit_date)},
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        assert r2.status_code == 200
        assert len(r2.json()) >= 1
    finally:
        db.close()
