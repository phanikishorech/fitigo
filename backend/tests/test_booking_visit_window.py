"""Quarter-hour scheduling and early-entry-to-closing policy, isolated database."""
from app.core.time import IST, stored_instant
from datetime import time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_booking_access_qr import api, NOW, create, qr, scan
from test_booking_time import snapshot
from app.models.access import Checkin
from app.models.booking import Booking
from app.models.cart import CartItem
from app.models.class_booking import GymSpecialHours
from app.models.gym import GymOperatingHours
from app.models.slot import GymSlot
from app.services import booking_access_service, access_service


def body(start="18:15", **extra):
    return {"gym_id": 1, "booking_date": NOW.date().isoformat(), "preferred_start_time": start,
            "member_count": 1, "visitor_names": ["David"], **extra}


@pytest.mark.parametrize("minute", ["00", "15", "30", "45"])
def test_server_calculates_one_hour_end_for_each_quarter(api, minute):
    client, headers, engine = api
    response = client.post("/api/v1/cart/items/gym", headers=headers[1], json=body(f"18:{minute}"))
    assert response.status_code == 200, response.text
    assert response.json()["preferred_end_time"] == f"19:{minute}:00"
    paid = client.post("/api/v1/cart/checkout/wallet", headers=headers[1])
    assert paid.status_code == 200, paid.text
    with Session(engine) as db:
        booking = db.get(Booking, paid.json()["booking_ids"][0])
        slot = db.get(GymSlot, booking.gym_slot_id)
        assert slot.start_time == time(18, int(minute)) and slot.end_time == time(19, int(minute))


@pytest.mark.parametrize("payload,code", [
    (body("18:01"), "INVALID_BOOKING_TIME"),
    (body("18:15:01"), "INVALID_BOOKING_TIME"),
    (body("18:15:00.100"), "INVALID_BOOKING_TIME"),
    (body("18:15+05:30"), "INVALID_BOOKING_TIME"),
    (body("18:15", preferred_end_time="18:45"), "INVALID_BOOKING_DURATION"),
    (body("18:15", preferred_end_time="20:15"), "INVALID_BOOKING_DURATION"),
    (body("23:15"), "INVALID_BOOKING_TIME"),
])
def test_forged_or_nonquarter_requests_fail_before_cart_or_debit(api, payload, code):
    client, headers, engine = api
    before = snapshot(engine)
    response = client.post("/api/v1/cart/items/gym", headers=headers[1], json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == code
    assert snapshot(engine) == before
    with Session(engine) as db:
        assert db.scalar(select(func.count(CartItem.id))) == 0


@pytest.mark.parametrize("checkout", ["/checkout", "/checkout/wallet"])
def test_old_custom_duration_cart_cannot_bypass_new_policy(api, checkout):
    client, headers, engine = api
    response = client.post("/api/v1/cart/items/gym", headers=headers[1], json=body())
    assert response.status_code == 200
    with Session(engine) as db:
        db.get(CartItem, response.json()["id"]).preferred_end_time = time(20, 15)
        db.commit()
    before = snapshot(engine)
    result = client.post("/api/v1/cart" + checkout, headers=headers[1])
    assert result.status_code == 400 and result.json()["detail"]["code"] == "INVALID_BOOKING_DURATION"
    assert snapshot(engine) == before


def configure_visit(api, start=time(18), opening=time(6), closing=time(22)):
    with Session(api[2]) as db:
        slot = db.get(GymSlot, 1)
        slot.start_time, slot.end_time = start, time(start.hour + 1, start.minute)
        hours = db.scalar(select(GymOperatingHours).where(GymOperatingHours.gym_id == 1,
            GymOperatingHours.day_of_week == NOW.weekday()))
        hours.open_time, hours.close_time = opening, closing
        db.commit()
    booking = create(api, ["David"])
    return booking, qr(api, booking)[0]


def set_scan_time(monkeypatch, at):
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: at)
    monkeypatch.setattr(access_service, "utcnow", lambda: at)


@pytest.mark.parametrize("at,expected", [(time(16, 59, 59), "OUTSIDE_BOOKING_WINDOW"),
    (time(17), "CHECKED_IN"), (time(18), "CHECKED_IN"), (time(19, 30), "CHECKED_IN"),
    (time(21, 59, 59), "CHECKED_IN"), (time(22), "BOOKING_EXPIRED")])
def test_entry_from_one_hour_early_until_closing(api, monkeypatch, at, expected):
    booking, token = configure_visit(api)
    assert token["valid_from"] == "2026-10-10T17:00:00+05:30"
    assert token["expires_at"] == "2026-10-10T22:00:00+05:30"
    detail = api[0].get(f"/api/v1/bookings/{booking['id']}", headers=api[1][1]).json()
    assert detail["access"]["valid_from"] == token["valid_from"]
    assert detail["access"]["expires_at"] == token["expires_at"]
    set_scan_time(monkeypatch, NOW.replace(hour=at.hour, minute=at.minute, second=at.second))
    assert scan(api, token["qr_token"])["status"] == expected
    if expected == "CHECKED_IN":
        assert scan(api, token["qr_token"])["status"] == "BOOKING_ALREADY_USED"


def test_early_entry_never_precedes_opening(api, monkeypatch):
    _, token = configure_visit(api, opening=time(17, 30))
    assert token["valid_from"] == "2026-10-10T17:30:00+05:30"
    set_scan_time(monkeypatch, NOW.replace(hour=17, minute=29))
    assert scan(api, token["qr_token"])["status"] == "OUTSIDE_BOOKING_WINDOW"
    set_scan_time(monkeypatch, NOW.replace(hour=17, minute=30))
    assert scan(api, token["qr_token"])["success"]


def test_special_hours_override_and_shrinking_window_rechecked(api, monkeypatch):
    booking, original = configure_visit(api)
    with Session(api[2]) as db:
        db.add(GymSpecialHours(gym_id=1, date=NOW.date(), open_time=time(17, 30), close_time=time(20), is_closed=False))
        db.commit()
    set_scan_time(monkeypatch, NOW.replace(hour=21))
    assert scan(api, original["qr_token"])["status"] == "BOOKING_EXPIRED"
    set_scan_time(monkeypatch, NOW)
    current = qr(api, booking)[0]
    assert current["valid_from"] == "2026-10-10T17:30:00+05:30"
    assert current["expires_at"] == "2026-10-10T20:00:00+05:30"


def test_closure_after_purchase_rejects_qr_and_booking_list_still_loads(api):
    booking, token = configure_visit(api)
    with Session(api[2]) as db:
        db.add(GymSpecialHours(gym_id=1, date=NOW.date(), is_closed=True))
        db.commit()
    assert scan(api, token["qr_token"])["status"] == "GYM_CLOSED"
    response = api[0].get(f"/api/v1/bookings/{booking['id']}", headers=api[1][1])
    assert response.status_code == 200
    assert response.json()["access"]["status"] == "GYM_CLOSED"


def test_missing_hours_fails_closed_without_crashing_detail(api):
    booking, token = configure_visit(api)
    with Session(api[2]) as db:
        row = db.scalar(select(GymOperatingHours).where(GymOperatingHours.gym_id == 1,
            GymOperatingHours.day_of_week == NOW.weekday()))
        db.delete(row); db.commit()
    assert scan(api, token["qr_token"])["status"] == "GYM_HOURS_UNAVAILABLE"
    response = api[0].get(f"/api/v1/bookings/{booking['id']}", headers=api[1][1])
    assert response.status_code == 200 and not response.json()["access"]["qr_available"]


def test_class_retains_scheduled_window(api, monkeypatch):
    booking, _ = configure_visit(api)
    with Session(api[2]) as db:
        db.get(Booking, booking["id"]).notes = "access_type_id=GROUP_CLASS\nclass_session_id=123"
        db.commit()
    token = qr(api, booking)[0]
    assert token["valid_from"] == "2026-10-10T18:00:00+05:30"
    assert token["expires_at"] == "2026-10-10T19:00:00+05:30"
    set_scan_time(monkeypatch, NOW.replace(hour=17))
    assert scan(api, token["qr_token"])["status"] == "OUTSIDE_BOOKING_WINDOW"
    set_scan_time(monkeypatch, NOW.replace(hour=19))
    assert scan(api, token["qr_token"])["status"] == "BOOKING_EXPIRED"


def test_new_access_window_does_not_extend_to_previous_or_next_date(api, monkeypatch):
    _, token = configure_visit(api)
    set_scan_time(monkeypatch, NOW - timedelta(days=1))
    assert scan(api, token["qr_token"])["status"] == "WRONG_DATE"
    set_scan_time(monkeypatch, NOW + timedelta(days=1))
    assert scan(api, token["qr_token"])["status"] == "BOOKING_EXPIRED"


def test_booking_must_fit_full_hour_before_closing(api):
    with Session(api[2]) as db:
        row = db.scalar(select(GymOperatingHours).where(GymOperatingHours.gym_id == 1,
            GymOperatingHours.day_of_week == NOW.weekday()))
        row.close_time = time(19)
        db.commit()
    client, headers, engine = api
    before = snapshot(engine)
    response = client.post("/api/v1/cart/items/gym", headers=headers[1], json=body("18:15"))
    assert response.status_code == 400
    assert snapshot(engine) == before
    response = client.post("/api/v1/cart/items/gym", headers=headers[1], json=body("18:00"))
    assert response.status_code == 200 and response.json()["preferred_end_time"] == "19:00:00"


def test_old_token_keeps_issued_expiry_until_customer_reopens_qr(api, monkeypatch):
    from app.models.access import AccessQrToken
    booking, token = configure_visit(api)
    with Session(api[2]) as db:
        record = db.get(AccessQrToken, token["qr_id"])
        record.valid_from = stored_instant(NOW.replace(hour=18))
        record.expires_at = stored_instant(NOW.replace(hour=19))
        db.commit()
    set_scan_time(monkeypatch, NOW.replace(hour=20))
    assert scan(api, token["qr_token"])["status"] == "BOOKING_EXPIRED"
    refreshed = qr(api, booking)[0]
    assert refreshed["expires_at"] == "2026-10-10T22:00:00+05:30"
    assert scan(api, refreshed["qr_token"])["success"]