from __future__ import annotations

from pydantic import BaseModel


class AdminDashboardSummary(BaseModel):
    users: dict
    gyms: dict
    bookings: dict
    revenue: dict
