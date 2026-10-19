"""Disposable API/transaction tests. Never connects to the configured database."""
from app.core.time import IST, stored_instant
from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.base import Base
from app.database.session import get_db
from app.models.access import AccessQrToken, Checkin, CustomerDailyAccess
from app.models.auth import Role, User, UserRole
from app.models.booking import Booking, Payment
from app.models.gym import Gym, GymOperatingHours
from app.models.slot import GymSlot
from app.models.staff import GymStaffAssignment
from app.models.wallet import WalletAccount
from app.models.platform_membership import PlatformMembershipPlan
from app.routers import bookings, cart, checkins, profile
from app.services import access_service, booking_access_service, booking_time
from app.services.booking_service import BookingService

NOW = datetime(2026, 10, 10, 12, tzinfo=IST)


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        if "id" in clone.c and clone.c.id.type.python_type is int:
            clone.c.id.type = Integer()
    metadata.create_all(engine)
    monkeypatch.setattr(access_service, "utcnow", lambda: NOW)
    monkeypatch.setattr(access_service, "access_today", lambda: NOW.date())
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: NOW)
    # Purchase before the visit, then validate QR at the frozen check-in time.
    monkeypatch.setattr(booking_time, "utcnow", lambda: NOW.replace(hour=9))
    monkeypatch.setattr(BookingService, "_now", lambda self: stored_instant(NOW.replace(hour=9)))
    with Session(engine) as db:
        for i, role_name in enumerate(["CUSTOMER", "GYM_OWNER", "GYM_STAFF", "CUSTOMER", "GYM_OWNER"], 1):
            role = db.scalar(select(Role).where(Role.name == role_name))
            if not role:
                role = Role(name=role_name); db.add(role); db.flush()
            db.add(User(id=i, first_name=f"User {i}", email=f"qr-{i}@example.test", password_hash="unused", status="ACTIVE"))
            db.flush(); db.add(UserRole(user_id=i, role_id=role.id))
        for i in [1, 2]:
            db.add(Gym(id=i, owner_user_id=2 if i == 1 else 5, name=f"Gym {i}", status="APPROVED", is_active=True, gym_price_per_person=100))
            db.flush()
            for day in range(7):
                db.add(GymOperatingHours(gym_id=i, day_of_week=day, open_time=time(0), close_time=time(23, 59), is_closed=False))
        db.add(GymStaffAssignment(gym_id=1, user_id=3))
        db.add(GymSlot(id=1, gym_id=1, name="Visit", start_time=time(10), end_time=time(14), capacity=50, price=100, is_active=1))
        db.add(WalletAccount(user_id=1, balance=10000, currency="INR"))
        db.commit()
    app = FastAPI()
    for router in (bookings.router, cart.router, checkins.router, profile.router):
        app.include_router(router, prefix="/api/v1")
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    headers = {i: {"Authorization": f"Bearer {create_access_token(str(i))}"} for i in range(1, 6)}
    with TestClient(app) as client:
        yield client, headers, engine
    engine.dispose()


def create(api, names=None, day=None, pay=True):
    client, headers, _ = api
    body = {"gym_slot_id": 1, "slot_date": (day or NOW.date()).isoformat(), "quantity": len(names) if names else 1}
    if names is not None:
        body["visitor_names"] = names
    response = client.post("/api/v1/bookings", headers=headers[1], json=body)
    assert response.status_code == 200, response.text
    booking = response.json()
    if pay:
        response = client.post(f"/api/v1/bookings/{booking['id']}/pay", headers=headers[1])
        assert response.status_code == 200, response.text
        booking = response.json()
    return booking


def qr(api, booking):
    client, headers, _ = api
    response = client.post(f"/api/v1/bookings/{booking['id']}/qr", headers=headers[1])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["passes"]


def scan(api, token, gym=1, actor=3):
    client, headers, _ = api
    response = client.post("/api/v1/checkins/validate", headers=headers[actor], json={"gym_id": gym, "qr_token": token})
    assert response.status_code == 200, response.text
    return response.json()


def test_payment_confirmation_creates_unique_access_and_shared_checkin(api):
    client, headers, engine = api
    booking = create(api, ["David"], pay=False)
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
    assert not booking["access"]["qr_available"]
    assert client.post(f"/api/v1/bookings/{booking['id']}/qr", headers=headers[1]).status_code == 400
    response = client.post(f"/api/v1/bookings/{booking['id']}/pay", headers=headers[1])
    assert response.json()["access"]["qr_available"]
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1
    token = qr(api, booking)[0]["qr_token"]
    assert "David" not in token and token.startswith("GYMACCESS:")
    result = scan(api, token)
    assert result["success"] and result["customer_name"] == "David" and result["access_label"] == "Booking"
    assert scan(api, token)["status"] == "BOOKING_ALREADY_USED"
    with Session(engine) as db:
        checkin = db.scalars(select(Checkin)).one()
        assert checkin.booking_id == booking["id"] and checkin.membership_id is None and checkin.daily_access_id is None
        assert checkin.user_id == 1 and checkin.visitor_name == "David" and checkin.scanned_by == 3
        assert checkin.access_source == "BOOKING_ACCESS"
        assert db.scalar(select(func.count(CustomerDailyAccess.id))) == 0
        assert db.get(Booking, booking["id"]).attendance_status == "ATTENDED"
    assert not client.get(f"/api/v1/bookings/{booking['id']}", headers=headers[1]).json()["access"]["qr_available"]


def test_group_visitors_have_independent_one_time_access(api):
    booking = create(api, ["David", "Mary"])
    passes = qr(api, booking)
    assert len({p["qr_token"] for p in passes}) == 2
    assert scan(api, passes[0]["qr_token"])["customer_name"] == "David"
    assert scan(api, passes[0]["qr_token"])["status"] == "BOOKING_ALREADY_USED"
    assert scan(api, passes[1]["qr_token"], actor=2)["customer_name"] == "Mary"
    with Session(api[2]) as db:
        assert db.scalar(select(func.count(Checkin.id))) == 2


@pytest.mark.parametrize("change,expected", [("cancel", "BOOKING_CANCELLED"), ("FAILED", "PAYMENT_NOT_COMPLETED"), ("REFUNDED", "PAYMENT_NOT_COMPLETED"), ("EXPIRED", "BOOKING_EXPIRED"), ("PENDING_PAYMENT", "BOOKING_NOT_CONFIRMED"), ("visitor", "INVALID_VISITOR"), ("inactive", "CUSTOMER_NOT_ELIGIBLE")])
def test_current_backend_state_overrides_previously_issued_qr(api, change, expected):
    client, headers, engine = api
    booking = create(api, ["David"])
    token = qr(api, booking)[0]["qr_token"]
    if change == "cancel":
        assert client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=headers[1], json={}).status_code == 200
    else:
        with Session(engine) as db:
            row = db.get(Booking, booking["id"])
            if change in {"FAILED", "REFUNDED"}:
                row.payment.status = change
            elif change == "visitor":
                row.visitor_names = ["Someone else"]
            elif change == "inactive":
                db.get(User, 1).status = "SUSPENDED"
            else:
                row.status = change
            db.commit()
    assert scan(api, token)["status"] == expected
    with Session(engine) as db:
        assert db.scalar(select(func.count(Checkin.id))) == 0
        if change == "cancel":
            assert db.scalars(select(AccessQrToken)).one().status == "REVOKED"


def test_wrong_gym_date_window_token_and_scanner_authorization(api, monkeypatch):
    booking = create(api, ["David"])
    token = qr(api, booking)[0]["qr_token"]
    assert scan(api, token, gym=2, actor=5)["status"] == "WRONG_GYM"
    assert scan(api, token, actor=5)["status"] == "GYM_NOT_ALLOWED"
    assert scan(api, "GYMACCESS:made-up-token")["status"] == "INVALID_QR"
    assert scan(api, "1")["status"] == "INVALID_QR"
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: NOW - timedelta(days=1))
    assert scan(api, token)["status"] == "WRONG_DATE"
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: NOW.replace(hour=8, minute=59))
    assert scan(api, token)["status"] == "OUTSIDE_BOOKING_WINDOW"
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: NOW.replace(hour=23, minute=59))
    assert scan(api, token)["status"] == "BOOKING_EXPIRED"


def test_ownership_rotation_and_legacy_visitor_assignment(api):
    client, headers, engine = api
    booking = create(api)
    assert booking["access"]["can_set_visitors"]
    path = f"/api/v1/bookings/{booking['id']}"
    assert client.post(path + "/qr", headers=headers[4]).status_code == 404
    assert client.post(path + "/visitors", headers=headers[4], json={"visitor_names": ["David"]}).status_code == 404
    assert client.post(path + "/visitors", headers=headers[1], json={"visitor_names": ["David"]}).status_code == 200
    assert client.post(path + "/visitors", headers=headers[1], json={"visitor_names": ["Mary"]}).status_code == 400
    first, second = qr(api, booking)[0]["qr_token"], qr(api, booking)[0]["qr_token"]
    assert first != second
    assert not scan(api, first)["success"]
    assert scan(api, second)["success"]
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1


def test_existing_wallet_checkout_carries_visitors_and_creates_access_atomically(api):
    client, headers, engine = api
    body = {"gym_id": 1, "booking_date": NOW.date().isoformat(), "preferred_start_time": "10:00", "preferred_end_time": "11:00", "member_count": 2, "visitor_names": ["David", "Mary"]}
    added = client.post("/api/v1/cart/items/gym", headers=headers[1], json=body)
    assert added.status_code == 200, added.text
    assert added.json()["visitor_names"] == ["David", "Mary"]
    with Session(engine) as db:
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
        db.scalar(select(WalletAccount)).balance = 0
        db.commit()
    assert client.post("/api/v1/cart/checkout/wallet", headers=headers[1]).status_code == 400
    with Session(engine) as db:
        assert db.scalar(select(func.count(Booking.id))) == 0
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
        db.scalar(select(WalletAccount)).balance = 1000
        db.commit()
    paid = client.post("/api/v1/cart/checkout/wallet", headers=headers[1])
    assert paid.status_code == 200, paid.text
    booking_id = paid.json()["booking_ids"][0]
    with Session(engine) as db:
        assert db.get(Booking, booking_id).visitor_names == ["David", "Mary"]
        assert db.scalar(select(func.count(AccessQrToken.id))) == 2
    assert scan(api, qr(api, {"id": booking_id})[0]["qr_token"])["success"]


def test_visitor_validation_and_no_anonymous_checkout(api):
    client, headers, _ = api
    assert client.post("/api/v1/cart/checkout/wallet").status_code == 401
    response = client.post("/api/v1/bookings", headers=headers[1], json={"gym_slot_id": 1, "slot_date": NOW.date().isoformat(), "quantity": 2, "visitor_names": ["David"]})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_VISITORS"


def test_membership_covered_booking_cannot_bypass_daily_membership_rules(api):
    with Session(api[2]) as db:
        booking = BookingService(db).create_booking(user_id=1, gym_slot_id=1, slot_date=NOW.date(), quantity=1,
            notes=None, unit_price_override=0, auto_confirm_if_free=True, access_source="MEMBERSHIP_ACCESS")
        assert booking.status == "CONFIRMED"
        assert db.scalar(select(func.count(AccessQrToken.id))) == 0
        assert booking_access_service.BookingAccessService(db).summary(booking)["status"] == "MEMBERSHIP_ACCESS_REQUIRED"


def test_reschedule_rotates_old_qr_and_used_booking_cannot_be_rescheduled(api):
    client, headers, engine = api
    booking = create(api, ["David"])
    old = qr(api, booking)[0]["qr_token"]
    path = f"/api/v1/bookings/{booking['id']}/reschedule"
    response = client.post(path, headers=headers[1], json={"gym_slot_id": 1, "slot_date": (NOW.date() + timedelta(days=1)).isoformat()})
    assert response.status_code == 200, response.text
    assert not scan(api, old)["success"]
    assert scan(api, qr(api, booking)[0]["qr_token"])["status"] == "WRONG_DATE"
    assert client.post(path, headers=headers[1], json={"gym_slot_id": 1, "slot_date": NOW.date().isoformat()}).status_code == 200
    assert scan(api, qr(api, booking)[0]["qr_token"])["success"]
    assert client.post(path, headers=headers[1], json={"gym_slot_id": 1, "slot_date": (NOW.date() + timedelta(days=1)).isoformat()}).status_code == 409


def test_admin_confirmation_and_owner_cancellation_use_same_access_records(api):
    from app.services.admin_booking_ops_service import AdminBookingOpsService
    booking = create(api, ["David"], pay=False)
    with Session(api[2]) as db:
        AdminBookingOpsService(db).update_payment_status(booking_id=booking["id"], new_status="PAID")
        assert db.scalar(select(func.count(AccessQrToken.id))) == 1
    token = qr(api, booking)[0]["qr_token"]
    with Session(api[2]) as db:
        BookingService(db).owner_cancel_booking(owner_user_id=2, booking_id=booking["id"])
        assert db.scalars(select(AccessQrToken)).one().status == "REVOKED"
    assert scan(api, token)["status"] == "BOOKING_CANCELLED"


def test_booking_scan_is_not_counted_as_membership_calendar_usage(api):
    booking = create(api, ["David"])
    assert scan(api, qr(api, booking)[0]["qr_token"])["success"]
    client, headers, engine = api
    visits = client.get("/api/v1/profile/bookings?status=all", headers=headers[1])
    assert visits.status_code == 200, visits.text
    assert len(visits.json()) == 1 and visits.json()[0]["booking_id"] == booking["id"]
    with Session(engine) as db:
        calendar = access_service.AccessService(db).calendar_month(user_id=1, year=2026, month=10)
        assert not any(day.get("gym_id") for day in calendar["days"])