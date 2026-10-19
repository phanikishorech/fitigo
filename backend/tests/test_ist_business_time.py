"""IST is the civil clock; historical audit instants retain their meaning."""
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_booking_access_qr import api, NOW, create, qr, scan
from test_access_service_regressions import access
from app.core import time as clock
from app.core.time import IST, as_ist, ist_day_bounds, stored_instant
from app.models.access import AccessQrToken, CustomerDailyAccess
from app.models.booking import Booking
from app.models.gym import GymOperatingHours
from app.models.membership import MembershipPause
from app.models.slot import GymSlot
from app.schemas.access_booking import GymBookingOptionsResponse
from app.services import access_service, booking_access_service, booking_time, membership_pause_service
from app.services.booking_time import require_future_start
from app.services.membership_entitlement import active_memberships


def test_ist_calendar_rollover_not_server_timezone(monkeypatch):
    monkeypatch.setattr(clock, "utcnow", lambda: datetime(2026, 10, 31, 18, 29, 59, tzinfo=timezone.utc))
    assert clock.ist_today() == date(2026, 10, 31)
    monkeypatch.setattr(clock, "utcnow", lambda: datetime(2026, 10, 31, 18, 30, tzinfo=timezone.utc))
    assert clock.ist_today() == date(2026, 11, 1)
    start, end = ist_day_bounds(date(2026, 11, 1))
    assert start == datetime(2026, 10, 31, 18, 30)
    assert end == datetime(2026, 11, 1, 18, 30)


def test_selected_time_is_ist_not_utc():
    instant = datetime(2026, 10, 8, 18, 45, tzinfo=timezone.utc)  # 00:15 IST next day
    with pytest.raises(HTTPException):
        require_future_start(date(2026, 10, 9), time(0, 15), now=instant)
    require_future_start(date(2026, 10, 9), time(0, 30), now=instant)
    with pytest.raises(HTTPException):
        require_future_start(date(2026, 10, 8), time(23, 45), now=instant)
    # Naive audit timestamps and aware instants represent the same moment.
    require_future_start(date(2026, 10, 9), time(0, 30), now=instant.replace(tzinfo=None))


def test_booking_api_dates_and_qr_are_ist(api):
    booking = create(api, ["David"])
    assert booking["slot_date"] == "2026-10-10"
    for field in ["created_at", "updated_at", "expires_at"]:
        assert booking[field].endswith("+05:30")
    token = qr(api, booking)[0]
    assert token["valid_from"] == "2026-10-10T09:00:00+05:30"
    assert token["expires_at"] == "2026-10-10T23:59:00+05:30"
    result = scan(api, token["qr_token"])
    assert result["checkin_time"] == "2026-10-10T12:00:00+05:30"
    with Session(api[2]) as db:
        stored = db.get(AccessQrToken, token["qr_id"])
        assert stored.valid_from == datetime(2026, 10, 10, 3, 30)
        assert stored.used_at == datetime(2026, 10, 10, 6, 30)
        assert db.get(Booking, booking["id"]).slot_date == date(2026, 10, 10)


def test_same_day_booking_at_ist_midnight_does_not_get_wrong_date(api, monkeypatch):
    tomorrow = date(2026, 10, 11)
    with Session(api[2]) as db:
        slot = db.get(GymSlot, 1)
        slot.start_time, slot.end_time = time(0, 30), time(1, 30)
        db.commit()
    booking = create(api, ["David"], day=tomorrow)
    token = qr(api, booking)[0]
    assert token["valid_from"] == "2026-10-11T00:00:00+05:30"
    at = datetime(2026, 10, 10, 18, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(booking_access_service, "utcnow", lambda: at)
    monkeypatch.setattr(access_service, "utcnow", lambda: at)
    assert scan(api, token["qr_token"])["success"]


def test_membership_daily_reset_and_month_history_at_ist_midnight(access, monkeypatch):
    service, user, gym, membership = access
    before = datetime(2026, 9, 30, 18, 29, tzinfo=timezone.utc)  # Sep 30 23:59 IST
    after = before + timedelta(minutes=1)
    membership.end_at = datetime(2026, 11, 1)
    service.db.commit()
    monkeypatch.setattr(access_service, "utcnow", lambda: before)
    monkeypatch.setattr(access_service, "access_today", lambda: as_ist(access_service.utcnow()).date())
    first = service.get_today_access(user_id=user.id)
    assert first["expires_at"] == datetime(2026, 10, 1, tzinfo=IST)
    assert service.validate_checkin(gym_id=gym.id, qr_token=first["qr_token"])["success"]
    assert service.get_today_access(user_id=user.id)["status"] == "USED"
    monkeypatch.setattr(access_service, "utcnow", lambda: after)
    second = service.get_today_access(user_id=user.id)
    assert second["status"] == "ACTIVE"
    assert service.validate_checkin(gym_id=gym.id, qr_token=second["qr_token"])["success"]
    assert service.get_today_access(user_id=user.id)["status"] == "USED"
    september = service.calendar_month(user_id=user.id, year=2026, month=9)
    october = service.calendar_month(user_id=user.id, year=2026, month=10)
    assert september["days"][-1]["checkin_time"] == time(23, 59)
    assert october["days"][0]["checkin_time"] == time(0)
    assert october["days"][0]["status"] == "TODAY"
    assert {row.access_date for row in service.db.scalars(select(CustomerDailyAccess))} == {date(2026, 9, 30), date(2026, 10, 1)}


def test_membership_pause_begins_and_ends_at_ist_midnight(access):
    service, user, _, membership = access
    service.db.add(MembershipPause(membership_id=membership.id, request_key="ist-midnight", start_date=date(2026, 9, 17),
        end_date=date(2026, 9, 17), days=1, previous_end_at=membership.end_at, new_end_at=membership.end_at + timedelta(days=1)))
    service.db.commit()
    before = datetime(2026, 9, 16, 18, 29, 59, tzinfo=timezone.utc)
    start = before + timedelta(seconds=1)
    assert active_memberships(service.db, user.id, before)
    assert not active_memberships(service.db, user.id, start)
    assert membership_pause_service.membership_status(service.db, membership, start) == "PAUSED"
    assert active_memberships(service.db, user.id, start + timedelta(days=1))


def test_operating_hours_use_ist_clock_even_when_utc_date_differs(access):
    from app.models.gym import GymOperatingHours
    service, _, gym, _ = access
    service.db.add(GymOperatingHours(gym_id=gym.id, day_of_week=date(2026, 9, 17).weekday(),
        open_time=time(0), close_time=time(2), is_closed=False))
    service.db.commit()
    service._validate_checkin_time_window(gym_id=gym.id, at=datetime(2026, 9, 16, 19, tzinfo=timezone.utc))
    with pytest.raises(HTTPException):
        service._validate_checkin_time_window(gym_id=gym.id, at=datetime(2026, 9, 16, 21, tzinfo=timezone.utc))