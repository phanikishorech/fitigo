from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class AdminDailyBookingReportRow(BaseModel):
    mode: Literal['test', 'live']
    currency: str
    date_basis: str
    basis: str
    day: date
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    expired_bookings: int
    paid_amount_total: str
