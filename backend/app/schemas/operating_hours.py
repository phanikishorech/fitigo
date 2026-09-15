from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel


class OperatingHoursForDateResponse(BaseModel):
    gym_id: int
    date: date
    day_of_week: int
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False
    label: str | None = None
