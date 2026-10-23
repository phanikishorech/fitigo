"""Owner dashboard API regression tests using a disposable SQLite database."""
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, MetaData, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.core.time import IST, ist_day_bounds, stored_instant
from app.database.base import Base
from app.database.session import get_db
from app.models.access import AccessQrToken, Checkin, CustomerDailyAccess
from app.models.auth import Role, User, UserRole
from app.models.booking import Booking, Payment
from app.models.gym import Gym
from app.models.membership import UserMembership
from app.models.platform_membership import PlatformMembershipPlan  # Register referenced tables for the disposable schema.
from app.models.slot import GymSlot
from app.routers import gym_owner
from app.services import owner_dashboard_service


DAY = date(2026, 10, 19)
NOW = stored_instant(datetime(2026, 10, 19, 12, tzinfo=IST))
SUMMARY = "/api/v1/gym-owner/dashboard/summary"


def booking(db, gym_id, *, quantity=1, attended=False, source="BOOKING_ACCESS", day=DAY, status="CONFIRMED"):
    row = Booking(user_id=3, gym_id=gym_id, gym_slot_id=gym_id, slot_date=day,
                  quantity=quantity, unit_price=100, total_price=100 * quantity,
                  expires_at=NOW, status=status, access_source=source,
                  attendance_status="ATTENDED" if attended else None,
                  attendance_marked_at=NOW if attended else None)
    db.add(row)
    db.flush()
    return row


def checkin(db, gym_id, *, access_type="MULTI_GYM", at=NOW, status="SUCCESS", booked=None, visitor_index=0):
    daily = None
    if booked is None:
        membership = UserMembership(user_id=3, gym_id=gym_id if access_type == "SINGLE_GYM" else None,
                                    membership_type=access_type, start_at=NOW - timedelta(days=30),
                                    end_at=NOW - timedelta(days=1), status="EXPIRED", paid_amount=100)
        db.add(membership)
        db.flush()
        daily = CustomerDailyAccess(user_id=3, membership_id=membership.id, access_type=access_type,
                                    gym_id=gym_id if access_type == "SINGLE_GYM" else None,
                                    access_date=DAY, access_key=f"test:{membership.id}", status="USED")
        db.add(daily)
        db.flush()
    token = AccessQrToken(daily_access_id=daily.id if daily else None,
                          booking_id=booked.id if booked else None,
                          visitor_index=visitor_index if booked else None,
                          token_hash=f"booking:{booked.id}:{visitor_index}" if booked else f"daily:{daily.id}",
                          expires_at=NOW + timedelta(hours=1))
    db.add(token)
    db.flush()
    row = Checkin(user_id=3, gym_id=gym_id, qr_token_id=token.id,
                  daily_access_id=daily.id if daily else None,
                  membership_id=daily.membership_id if daily else None,
                  access_source="BOOKING_ACCESS" if booked else "MEMBERSHIP_ACCESS",
                  booking_id=booked.id if booked else None,
                  visitor_index=visitor_index if booked else None,
                  visitor_name=f"Visitor {visitor_index + 1}" if booked else None,
                  checkin_time=at, status=status)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        if "id" in clone.c and clone.c.id.type.python_type is int:
            clone.c.id.type = Integer()
    metadata.create_all(engine)
    monkeypatch.setattr(owner_dashboard_service, "ist_today", lambda: DAY)
    with Session(engine) as db:
        for role_id, name in enumerate(["GYM_OWNER", "CUSTOMER", "GYM_STAFF"], 1):
            db.add(Role(id=role_id, name=name))
        for user_id in range(1, 6):
            db.add(User(id=user_id, first_name=f"User {user_id}", email=f"dashboard-{user_id}@example.test",
                        password_hash="unused", status="ACTIVE"))
        db.flush()
        for user_id, role_id in [(1, 1), (2, 1), (3, 2), (4, 3), (5, 1)]:
            db.add(UserRole(user_id=user_id, role_id=role_id))
        for gym_id, owner in [(1, 1), (2, 1), (3, 2)]:
            db.add(Gym(id=gym_id, owner_user_id=owner, name=f"Gym {gym_id}", status="APPROVED"))
            db.flush()
            db.add(GymSlot(id=gym_id, gym_id=gym_id, name="Visit", start_time=time(9),
                           end_time=time(18), capacity=100, price=100))
        db.commit()
    app = FastAPI()
    app.include_router(gym_owner.router, prefix="/api/v1")
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    headers = {i: {"Authorization": f"Bearer {create_access_token(str(i))}"} for i in range(1, 6)}
    with TestClient(app) as client:
        yield client, headers, engine
    engine.dispose()


def summary(api, gym_id=None, day=DAY, actor=1):
    client, headers, _ = api
    params = {"date": day.isoformat()}
    if gym_id is not None:
        params["gym_id"] = gym_id
    response = client.get(SUMMARY, params=params, headers=headers[actor])
    assert response.status_code == 200, response.text
    return response.json()


def test_overall_equals_owned_gym_totals_and_group_scans_are_not_double_counted(api):
    with Session(api[2]) as db:
        checkin(db, 1)
        checkin(db, 1, access_type="SINGLE_GYM")
        group = booking(db, 1, quantity=5, attended=True)
        checkin(db, 1, booked=group, visitor_index=0)
        checkin(db, 1, booked=group, visitor_index=1)
        booking(db, 1, quantity=3, attended=True)
        booking(db, 1, quantity=10)  # Reservations are not visits.
        booking(db, 1, attended=True, source="MEMBERSHIP_ACCESS")
        booking(db, 1, attended=True, status="CANCELLED")
        checkin(db, 1, status="REJECTED")
        checkin(db, 2)
        booking(db, 2, quantity=2, attended=True)
        checkin(db, 3)  # A different owner's gym is never included.
        db.commit()
    first, second, overall = summary(api, 1), summary(api, 2), summary(api)
    assert first["visits"] == {"fitigo_member": 1, "single_gym_membership": 1, "individual_booking": 5, "total": 7}
    assert second["visits"] == {"fitigo_member": 1, "single_gym_membership": 0, "individual_booking": 2, "total": 3}
    for category in first["visits"]:
        assert overall["visits"][category] == first["visits"][category] + second["visits"][category]
    assert overall["gym_id"] is None and overall["gyms"]["total"] == 2
    assert first["gym_id"] == 1 and first["gyms"]["total"] == 1
    assert first["visits"]["total"] == sum(value for key, value in first["visits"].items() if key != "total")


def test_visit_dates_use_ist_midnight_and_actual_attendance_time(api):
    start, end = ist_day_bounds(DAY)
    with Session(api[2]) as db:
        for at in [start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end]:
            checkin(db, 1, at=at)
        booking(db, 1, attended=True, day=DAY - timedelta(days=1))
        old = booking(db, 1, attended=True)
        old.attendance_marked_at = start - timedelta(microseconds=1)
        db.commit()
    assert summary(api, 1)["visits"] == {"fitigo_member": 2, "single_gym_membership": 0, "individual_booking": 1, "total": 3}
    assert summary(api, 1, DAY - timedelta(days=1))["visits"]["total"] == 2
    assert summary(api, 1, DAY + timedelta(days=1))["visits"]["total"] == 1


def test_attendance_includes_memberships_and_visitors_sorted_without_booking_sample(api):
    with Session(api[2]) as db:
        for _ in range(55):
            booking(db, 1)
        attended = booking(db, 1, quantity=2, attended=True)
        checkin(db, 1, booked=attended, at=NOW + timedelta(minutes=3))
        checkin(db, 1, at=NOW + timedelta(minutes=2))
        checkin(db, 1, access_type="SINGLE_GYM", at=NOW + timedelta(minutes=1))
        manual = booking(db, 1, attended=True, quantity=3)
        checkin(db, 2, at=NOW + timedelta(minutes=10))
        checkin(db, 1, status="REJECTED", at=NOW + timedelta(minutes=10))
        db.commit()
        manual_id = manual.id
    client, headers, _ = api
    response = client.get("/api/v1/gym-owner/gyms/1/attendance", params={"date": str(DAY)}, headers=headers[1])
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 4 and all(row["gym_id"] == 1 for row in rows)
    assert [row["category"] for row in rows] == ["individual_booking", "fitigo_member", "single_gym_membership", "individual_booking"]
    assert rows[0]["customer_name"] == "Visitor 1"
    assert rows[1]["booking_id"] is None and rows[1]["customer_name"] == "User 3"
    assert rows[3]["booking_id"] == manual_id and rows[3]["visits"] == 3
    assert all(row["recorded_at"].endswith("+05:30") for row in rows)
    response = client.get("/api/v1/gym-owner/gyms/1/attendance", params={"date": str(DAY), "limit": 1}, headers=headers[1])
    assert response.json() == rows[:1]


def test_booking_and_revenue_metrics_follow_gym_selection(api):
    with Session(api[2]) as db:
        for gym_id, amount in [(1, 100), (2, 200), (3, 900)]:
            row = booking(db, gym_id)
            db.add(Payment(booking_id=row.id, status="PAID", amount=amount))
        booking(db, 2, day=DAY + timedelta(days=1))
        db.commit()
    first, second, overall = summary(api, 1), summary(api, 2), summary(api)
    assert float(first["revenue"]["last_30d"]) == 100
    assert float(second["revenue"]["last_30d"]) == 200
    assert float(overall["revenue"]["last_30d"]) == 300
    assert first["bookings"] == {"today": 1, "on_date": 1, "upcoming": 1, "in_period": 1, "confirmed_in_period": 1}
    assert second["bookings"] == {"today": 1, "on_date": 1, "upcoming": 2, "in_period": 1, "confirmed_in_period": 1}
    assert summary(api, 2, DAY + timedelta(days=1))["bookings"]["on_date"] == 1


def test_empty_owner_and_empty_gym_return_zero_and_defaults_remain_compatible(api):
    client, headers, _ = api
    for data in [summary(api, actor=5), summary(api, 1)]:
        assert data["visits"] == {"fitigo_member": 0, "single_gym_membership": 0, "individual_booking": 0, "total": 0}
        assert data["bookings"] == {"today": 0, "on_date": 0, "upcoming": 0, "in_period": 0, "confirmed_in_period": 0}
    response = client.get(SUMMARY, headers=headers[1])
    assert response.status_code == 200 and response.json()["date"] == str(DAY)
    assert client.get("/api/v1/gym-owner/gyms/1/attendance", headers=headers[1]).json() == []


def test_legacy_manual_attendance_without_time_uses_visit_date_and_rejections_do_not_hide_it(api):
    with Session(api[2]) as db:
        manual = booking(db, 1, quantity=2, attended=True)
        manual.attendance_marked_at = None
        checkin(db, 1, booked=manual, status="REJECTED")
        missing = booking(db, 1)
        missing.attendance_status = "NO_SHOW"
        missing.attendance_marked_at = NOW
        db.commit()
    assert summary(api, 1)["visits"]["individual_booking"] == 2
    response = api[0].get("/api/v1/gym-owner/gyms/1/attendance", headers=api[1][1])
    assert len(response.json()) == 1
    assert response.json()[0]["recorded_at"] is None


def test_historical_scan_cannot_be_counted_again_as_manual_attendance_on_another_date(api):
    with Session(api[2]) as db:
        attended = booking(db, 1, quantity=4, attended=True)
        checkin(db, 1, booked=attended, at=NOW - timedelta(days=1))
        member = checkin(db, 1, access_type="SINGLE_GYM")
        member.daily_access_id = None  # Membership reference still identifies the category.
        db.commit()
    assert summary(api, 1)["visits"] == {"fitigo_member": 0, "single_gym_membership": 1, "individual_booking": 0, "total": 1}
    assert summary(api, 1, DAY - timedelta(days=1))["visits"]["individual_booking"] == 1


@pytest.mark.parametrize("gym_id", [3, 999])
def test_other_owners_and_missing_gyms_are_rejected(api, gym_id):
    client, headers, _ = api
    assert client.get(SUMMARY, params={"gym_id": gym_id}, headers=headers[1]).status_code == 404
    assert client.get(f"/api/v1/gym-owner/gyms/{gym_id}/attendance", headers=headers[1]).status_code == 404


@pytest.mark.parametrize("actor", [3, 4])
def test_customer_and_staff_cannot_read_owner_metrics(api, actor):
    client, headers, _ = api
    assert client.get(SUMMARY, headers=headers[actor]).status_code == 403
    assert client.get("/api/v1/gym-owner/gyms/1/attendance", headers=headers[actor]).status_code == 403


@pytest.mark.parametrize("path", [f"{SUMMARY}?gym_id=0", f"{SUMMARY}?date=invalid",
                                    "/api/v1/gym-owner/gyms/1/attendance?limit=101",
                                    "/api/v1/gym-owner/gyms/1/attendance?date=invalid"])
def test_invalid_dashboard_filters_are_rejected(api, path):
    assert api[0].get(path, headers=api[1][1]).status_code == 422