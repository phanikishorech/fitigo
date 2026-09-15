from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field


class GymSlotCreateRequest(BaseModel):
    # NOTE: In owner portal we treat slots as class sessions (not gym access time windows).
    # Name becomes a class name (either selected existing class, or custom).
    name: str = Field(min_length=2, max_length=100)
    start_time: time
    end_time: time
    capacity: int = Field(ge=1, le=500)
    price: str = Field(pattern=r"^\d+(\.\d{1,2})?$")

    # Scheduling
    # - If specific_date is provided, it is an occasional class.
    # - Otherwise, repeat_days (0=Mon..6=Sun) indicates a repeating class schedule.
    specific_date: date | None = None
    repeat_days: list[int] = Field(default_factory=list)


class GymSlotUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    start_time: time | None = None
    end_time: time | None = None
    capacity: int | None = Field(default=None, ge=1, le=500)
    price: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")
    is_active: bool | None = None

    specific_date: date | None = None
    repeat_days: list[int] | None = None


class SlotAvailabilityResponse(BaseModel):
    slot_date: date
    status: str
    capacity_total: int
    booked_count: int
    blocked_count: int
    remaining_capacity: int


class GymSlotPublicResponse(BaseModel):
    id: int
    gym_id: int
    name: str
    start_time: time
    end_time: time
    capacity: int
    price: str
    is_active: bool
    availability: SlotAvailabilityResponse


class GymSlotOwnerResponse(BaseModel):
    id: int
    gym_id: int
    name: str
    start_time: time
    end_time: time
    capacity: int
    price: str
    is_active: bool
