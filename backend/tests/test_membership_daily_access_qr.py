from __future__ import annotations

import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.gym_service import GymService
from app.services.membership_service import MembershipService
from app.services.staff_service import StaffService


client = TestClient(app)


def test_membership_daily_qr_and_scan_flow():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = auth.register_user(
            first_name="O",
            last_name="Owner",
            email=f"qr_owner_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_GYM_OWNER,
        )
        customer = auth.register_user(
            first_name="C",
            last_name="Customer",
            email=f"qr_customer_{uuid.uuid4().hex[:8]}@example.com",
            phone=None,
            password="password1234",
            role_name=ROLE_CUSTOMER,
        )

        gym_svc = GymService(db)
        gym = gym_svc.create_gym(owner_user_id=owner.id, data={"name": "QR Gym", "city": "X"})
        gym.status = "APPROVED"
        db.commit()

        # Create a plan + purchase membership (active)
        msvc = MembershipService(db)
        plan = msvc.create_plan(owner_user_id=int(owner.id), gym_id=int(gym.id), data={"name": "Monthly", "duration_days": 30, "price": "999.00"})
        _m = msvc.purchase_membership(user_id=int(customer.id), gym_id=int(gym.id), plan_id=int(plan.id))

        # Invite staff so they can scan
        staff_email = f"qr_staff_{uuid.uuid4().hex[:8]}@example.com"
        ssvc = StaffService(db)
        invite = ssvc.invite_staff(owner_user_id=int(owner.id), gym_id=int(gym.id), email=staff_email, first_name="S", last_name="T")
        staff_user_id = int(invite["staff_user_id"])

        cust_token = create_access_token(str(customer.id))

        # Calendar should load for current month
        month = datetime.utcnow().strftime("%Y-%m")
        rcal = client.get(
            "/api/v1/profile/membership/calendar",
            params={"gym_id": gym.id, "month": month},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert rcal.status_code == 200
        assert int(rcal.json()["gym_id"]) == int(gym.id)

        # QR for today should be available
        rqr = client.get(
            "/api/v1/profile/membership/daily-qr",
            params={"gym_id": gym.id},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert rqr.status_code == 200
        j = rqr.json()
        assert j["gym_id"] == gym.id
        assert j["scanned"] is False
        assert j["qr_payload"]
        assert j["qr_payload"].startswith("GYMACCESS:")
        assert rqr.headers["cache-control"] == "no-store"

        # Mint through the new API too; neither transport grants a second visit.
        headers = {"Authorization": f"Bearer {cust_token}"}
        modern = client.get("/api/v1/customer/access/today", headers=headers)
        assert modern.status_code == 200
        assert modern.headers["cache-control"] == "no-store"
        modern_qr = modern.json()["qr_token"]
        assert client.get("/api/v1/profile/membership/pass", headers=headers).json()["qr_payload"] is None

        staff_token = create_access_token(str(staff_user_id))
        rscan = client.post(
            "/api/v1/gym-staff/scan-membership-qr",
            json={"qr_payload": j["qr_payload"]},
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        assert rscan.status_code == 200
        assert rscan.json()["gym_id"] == gym.id
        assert rscan.json()["user_id"] == customer.id

        # Now QR should be marked scanned and not returned
        rqr2 = client.get(
            "/api/v1/profile/membership/daily-qr",
            params={"gym_id": gym.id},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert rqr2.status_code == 200
        j2 = rqr2.json()
        assert j2["scanned"] is True
        assert j2["qr_payload"] is None

        staff_headers = {"Authorization": f"Bearer {staff_token}"}
        replay = client.post("/api/v1/checkins/validate", headers=staff_headers,
                             json={"qr_token": modern_qr, "gym_id": gym.id})
        # The modern scanner preserves its structured HTTP-200 failure contract.
        assert replay.status_code == 200
        assert replay.json()["success"] is False
        assert replay.json()["status"] in {"QR_ALREADY_USED", "DAILY_ACCESS_ALREADY_USED"}
        legacy_replay = client.post("/api/v1/gym-staff/scan-membership-qr", headers=staff_headers,
                                    json={"qr_payload": modern_qr, "gym_id": gym.id})
        assert legacy_replay.status_code == 409
        assert client.get("/api/v1/customer/access/today", headers=headers).json()["status"] == "USED"

        calendar = client.get("/api/v1/customer/access-calendar", headers=headers,
                              params={"year": int(month[:4]), "month": int(month[5:])})
        today = next(day for day in calendar.json()["days"] if day["status"] == "TODAY")
        assert today["qr_status"] == "USED"
        assert today["gym_id"] == gym.id
        legacy_calendar = client.get("/api/v1/profile/membership/calendar", headers=headers,
                                     params={"gym_id": gym.id, "month": month})
        assert today["date"] in legacy_calendar.json()["accessed_dates"]
        visits = client.get("/api/v1/profile/bookings?status=past", headers=headers)
        assert visits.status_code == 200
        assert any(visit["gym_id"] == gym.id and visit["booking_id"] < 0 for visit in visits.json())

        # The former signed-token path cannot bypass central access validation.
        rejected = client.post("/api/v1/gym-staff/scan-membership-qr", headers=staff_headers,
                               json={"qr_payload": cust_token, "gym_id": gym.id})
        assert rejected.status_code == 400
        for invalid_month in ("oops", "abcd-12", "2026-00", "0000-01"):
            invalid = client.get("/api/v1/profile/membership/calendar", headers=headers,
                                 params={"gym_id": gym.id, "month": invalid_month})
            assert invalid.status_code == 400
    finally:
        db.close()
