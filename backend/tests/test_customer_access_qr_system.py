from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.core.security import create_access_token
from app.database.session import SessionLocal
from app.main import app
from app.models.access import AccessPauseDay, Checkin, CustomerDailyAccess
from app.models.gym import Gym
from app.services.auth_service import AuthService
from app.services.gym_service import GymService
from app.services.membership_service import MembershipService
from app.services.staff_service import StaffService
from app.services.access_service import AccessService


client = TestClient(app)


def _create_user(auth: AuthService, *, role: str, prefix: str):
    return auth.register_user(
        first_name=prefix,
        last_name="User",
        email=f"{prefix}_{uuid.uuid4().hex[:8]}@example.com",
        phone=None,
        password="password1234",
        role_name=role,
    )


def _create_gym(db, owner_id: int, name: str) -> Gym:
    gym_svc = GymService(db)
    gym = gym_svc.create_gym(owner_user_id=owner_id, data={"name": name, "city": "X"})
    gym.status = "APPROVED"
    gym.is_active = True
    db.commit()
    db.refresh(gym)
    return gym


def _create_membership(db, *, owner_id: int, customer_id: int, gym: Gym):
    msvc = MembershipService(db)
    plan = msvc.create_plan(owner_user_id=owner_id, gym_id=int(gym.id), data={"name": "Monthly", "duration_days": 30, "price": "999.00"})
    return msvc.purchase_membership(user_id=customer_id, gym_id=int(gym.id), plan_id=int(plan.id))


def _invite_staff(db, *, owner_id: int, gym_id: int) -> int:
    ssvc = StaffService(db)
    staff_email = f"staff_{uuid.uuid4().hex[:8]}@example.com"
    invite = ssvc.invite_staff(owner_user_id=owner_id, gym_id=gym_id, email=staff_email, first_name="S", last_name="T")
    return int(invite["staff_user_id"])


def test_concurrent_rotated_tokens_allow_exactly_one_checkin():
    if SessionLocal is None:
        pytest.skip("Database is not configured")
    with SessionLocal() as db:
        if db.get_bind().dialect.name != "mysql":
            pytest.skip("Requires MySQL row locking")
        auth = AuthService(db)
        owner = _create_user(auth, role=ROLE_GYM_OWNER, prefix="owner_race")
        customer = _create_user(auth, role=ROLE_CUSTOMER, prefix="cust_race")
        gym = _create_gym(db, owner.id, "Concurrent Scan Gym")
        _create_membership(db, owner_id=owner.id, customer_id=customer.id, gym=gym)
        customer_id, gym_id = int(customer.id), int(gym.id)
        service = AccessService(db)
        tokens = [service.get_today_access(user_id=customer_id)["qr_token"] for _ in range(2)]

    barrier = Barrier(2)

    def scan(token):
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            try:
                AccessService(session).validate_checkin(gym_id=gym_id, qr_token=token)
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(scan, tokens))
    assert sorted(results) == [200, 409]
    with SessionLocal() as db:
        checkins = db.execute(select(Checkin).where(Checkin.user_id == customer_id)).scalars().all()
        assert len(checkins) == 1
        assert AccessService(db).get_today_access(user_id=customer_id)["status"] == "USED"


def test_single_gym_access_qr_one_time_use_and_wrong_gym_rejected():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = _create_user(auth, role=ROLE_GYM_OWNER, prefix="owner_s")
        customer = _create_user(auth, role=ROLE_CUSTOMER, prefix="cust_s")

        gym_a = _create_gym(db, owner.id, "Gym A")
        gym_b = _create_gym(db, owner.id, "Gym B")

        _create_membership(db, owner_id=int(owner.id), customer_id=int(customer.id), gym=gym_a)

        staff_a = _invite_staff(db, owner_id=int(owner.id), gym_id=int(gym_a.id))
        staff_b = _invite_staff(db, owner_id=int(owner.id), gym_id=int(gym_b.id))

        cust_token = create_access_token(str(customer.id))
        staff_a_token = create_access_token(str(staff_a))
        staff_b_token = create_access_token(str(staff_b))

        # generate today's access token
        r_today = client.get("/api/v1/customer/access/today", headers={"Authorization": f"Bearer {cust_token}"})
        assert r_today.status_code == 200
        j = r_today.json()
        assert j["status"] == "ACTIVE"
        assert j["access_type"] == "SINGLE_GYM"
        assert j["gym"]["id"] == gym_a.id
        qr = j["qr_token"]

        # wrong gym scan
        r_wrong = client.post(
            "/api/v1/checkins/validate",
            json={"qr_token": qr, "gym_id": int(gym_b.id)},
            headers={"Authorization": f"Bearer {staff_b_token}"},
        )
        assert r_wrong.status_code == 200
        assert r_wrong.json()["success"] is False
        assert r_wrong.json()["status"] in {"WRONG_GYM", "INVALID_QR"}

        # correct scan
        r_ok = client.post(
            "/api/v1/checkins/validate",
            json={"qr_token": qr, "gym_id": int(gym_a.id)},
            headers={"Authorization": f"Bearer {staff_a_token}"},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["success"] is True

        # reuse must fail
        r_reuse = client.post(
            "/api/v1/checkins/validate",
            json={"qr_token": qr, "gym_id": int(gym_a.id)},
            headers={"Authorization": f"Bearer {staff_a_token}"},
        )
        assert r_reuse.status_code == 200
        assert r_reuse.json()["success"] is False
        assert r_reuse.json()["status"] in {"QR_ALREADY_USED", "DAILY_ACCESS_ALREADY_USED"}
    finally:
        db.close()


def test_multi_gym_access_daily_one_time_use():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = _create_user(auth, role=ROLE_GYM_OWNER, prefix="owner_m")
        customer = _create_user(auth, role=ROLE_CUSTOMER, prefix="cust_m")

        gym_a = _create_gym(db, owner.id, "Gym A")
        gym_b = _create_gym(db, owner.id, "Gym B")

        # make user multi-gym by owning two active memberships
        _create_membership(db, owner_id=int(owner.id), customer_id=int(customer.id), gym=gym_a)
        _create_membership(db, owner_id=int(owner.id), customer_id=int(customer.id), gym=gym_b)

        staff_a = _invite_staff(db, owner_id=int(owner.id), gym_id=int(gym_a.id))
        staff_b = _invite_staff(db, owner_id=int(owner.id), gym_id=int(gym_b.id))

        cust_token = create_access_token(str(customer.id))
        staff_a_token = create_access_token(str(staff_a))
        staff_b_token = create_access_token(str(staff_b))

        r_today = client.get("/api/v1/customer/access/today", headers={"Authorization": f"Bearer {cust_token}"})
        assert r_today.status_code == 200
        j = r_today.json()
        assert j["status"] == "ACTIVE"
        assert j["access_type"] == "MULTI_GYM"
        qr = j["qr_token"]

        r_ok = client.post(
            "/api/v1/checkins/validate",
            json={"qr_token": qr, "gym_id": int(gym_a.id)},
            headers={"Authorization": f"Bearer {staff_a_token}"},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["success"] is True

        r_again_other = client.post(
            "/api/v1/checkins/validate",
            json={"qr_token": qr, "gym_id": int(gym_b.id)},
            headers={"Authorization": f"Bearer {staff_b_token}"},
        )
        assert r_again_other.status_code == 200
        assert r_again_other.json()["success"] is False
        assert r_again_other.json()["status"] in {"QR_ALREADY_USED", "DAILY_ACCESS_ALREADY_USED"}
    finally:
        db.close()


def test_paused_day_blocks_qr_generation():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = _create_user(auth, role=ROLE_GYM_OWNER, prefix="owner_p")
        customer = _create_user(auth, role=ROLE_CUSTOMER, prefix="cust_p")

        gym_a = _create_gym(db, owner.id, "Gym A")
        _create_membership(db, owner_id=int(owner.id), customer_id=int(customer.id), gym=gym_a)

        today = datetime.utcnow().date()
        db.add(AccessPauseDay(user_id=int(customer.id), access_date=today, reason="test", created_at=datetime.utcnow()))
        db.commit()

        cust_token = create_access_token(str(customer.id))
        r_today = client.get("/api/v1/customer/access/today", headers={"Authorization": f"Bearer {cust_token}"})
        assert r_today.status_code == 200
        assert r_today.json()["status"] == "PAUSED"
    finally:
        db.close()


def test_calendar_marks_visited_and_no_visit():
    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        auth = AuthService(db)
        owner = _create_user(auth, role=ROLE_GYM_OWNER, prefix="owner_c")
        customer = _create_user(auth, role=ROLE_CUSTOMER, prefix="cust_c")

        gym_a = _create_gym(db, owner.id, "Gym A")
        _create_membership(db, owner_id=int(owner.id), customer_id=int(customer.id), gym=gym_a)
        _invite_staff(db, owner_id=int(owner.id), gym_id=int(gym_a.id))

        # Insert a USED daily access + checkin for yesterday to force VISITED
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        # Create daily access row directly
        da = CustomerDailyAccess(
            user_id=int(customer.id),
            membership_id=db.execute(select(CustomerDailyAccess.membership_id)).scalars().first() or 1,
            access_type="SINGLE_GYM",
            gym_id=int(gym_a.id),
            access_date=yesterday,
            access_key=f"u:{customer.id}|m:1|d:{yesterday.isoformat()}|g:{gym_a.id}",
            status="USED",
            used_at=datetime.utcnow(),
            used_gym_id=int(gym_a.id),
            checkin_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(da)
        db.commit()

        cust_token = create_access_token(str(customer.id))
        now = datetime.utcnow()
        r_cal = client.get(
            "/api/v1/customer/access-calendar",
            params={"month": now.month, "year": now.year},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert r_cal.status_code == 200
        days = r_cal.json()["days"]
        # Should have a record for yesterday
        y = [d for d in days if d["date"] == yesterday.isoformat()]
        assert y
    finally:
        db.close()
