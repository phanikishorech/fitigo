from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BookingCreateRequest(BaseModel):
    gym_slot_id: int
    slot_date: date
    quantity: int = Field(ge=1, le=50)
    notes: str | None = Field(default=None, max_length=2000)


class PaymentResponse(BaseModel):
    id: int
    provider: str
    status: str
    amount: str
    currency: str
    external_ref: str | None
    created_at: datetime
    updated_at: datetime


class BookingResponse(BaseModel):
    id: int
    user_id: int
    gym_id: int
    gym_slot_id: int
    slot_date: date
    quantity: int
    unit_price: str
    total_price: str
    currency: str
    status: str
    notes: str | None
    expires_at: datetime
    expired_at: datetime | None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None
    payment: PaymentResponse | None


class BookingCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingRescheduleRequest(BaseModel):
    gym_slot_id: int
    slot_date: date
    note: str | None = Field(default=None, max_length=500)
