from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ClassSessionPublicResponse(BaseModel):
    id: int
    gym_id: int
    class_id: int
    class_name: str
    class_date: date
    start_time: str
    end_time: str
    maximum_capacity: int
    booked_capacity: int
    available_capacity: int
    price_per_person: str
    status: str
