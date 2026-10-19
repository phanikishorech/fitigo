from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

# India has one civil timezone with no daylight-saving changes. Fixed offset
# avoids depending on an OS timezone database on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
BUSINESS_TIMEZONE = "Asia/Kolkata"


def utcnow() -> datetime:
    """Absolute clock for existing UTC audit storage, never a business date."""

    return datetime.now(timezone.utc)


def utc_today() -> date:
    return utcnow().date()


def as_ist(value: datetime) -> datetime:
    """Existing naive MySQL audit timestamps represent absolute UTC instants.

    DATE/TIME booking selections must instead be combined directly with IST.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def ist_now() -> datetime:
    return as_ist(utcnow())


def ist_today() -> date:
    return ist_now().date()


def stored_instant(value: datetime) -> datetime:
    """Normalize only at the legacy MySQL audit-storage boundary."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def ist_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=IST)
    return stored_instant(start), stored_instant(start + timedelta(days=1))
