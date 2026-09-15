from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class AdminDailyBookingReportRow(BaseModel):
    day: date
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    expired_bookings: int
    paid_amount_total: str
