"""Booking purchase policy, separate from the check-in/access window policy.

Slot and class dates/times are IST. Never use the server's local clock
or a client-supplied current time to authorize a reservation or debit.
"""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException

from app.core.time import utcnow, as_ist, IST


def gym_visit_end(start: time, supplied_end: time | None = None) -> time:
    """Quarter-hour starts, fixed one-hour visit. Current cart uses same-day hours."""
    if start.tzinfo is not None or start.minute % 15 or start.second or start.microsecond:
        raise HTTPException(status_code=400, detail={"code": "INVALID_BOOKING_TIME", "message": "Choose a start time at 00, 15, 30 or 45 minutes."})
    end = datetime.combine(date(2000, 1, 1), start) + timedelta(hours=1)
    if end.date() != date(2000, 1, 1):
        raise HTTPException(status_code=400, detail={"code": "INVALID_BOOKING_TIME", "message": "Choose a one-hour visit within the same day's opening hours."})
    if supplied_end is not None and supplied_end != end.time():
        raise HTTPException(status_code=400, detail={"code": "INVALID_BOOKING_DURATION", "message": "Gym visits have an automatic one-hour duration. Select the visit again."})
    return end.time()


def require_future_start(visit_date: date, start_time: time, *, now: datetime | None = None) -> None:
    current = now if now is not None else utcnow()
    current = as_ist(current)
    if start_time.tzinfo is not None:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_BOOKING_TIME", "message": "Choose a booking time in IST without a timezone offset."
        })
    start = datetime.combine(visit_date, start_time, tzinfo=IST)
    if start <= current:
        raise HTTPException(status_code=400, detail={
            "code": "BOOKING_TIME_PASSED",
            "message": "This visit's start time has passed. Choose a future date and time. No payment was taken.",
        })