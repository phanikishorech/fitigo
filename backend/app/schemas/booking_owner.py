from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel


class OwnerBookingActionRequest(BaseModel):
    reason: str | None = None
    note: str | None = None


class OwnerBookingCustomer(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: str
    phone: str | None


class OwnerBookingSlot(BaseModel):
    id: int
    name: str
    start_time: time
    end_time: time


class OwnerBookingPayment(BaseModel):
    id: int
    provider: str
    status: str
    amount: str
    currency: str
    external_ref: str | None


class OwnerBookingResponse(BaseModel):
    id: int
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

    attendance_status: str | None
    attendance_marked_at: datetime | None
    attendance_note: str | None

    customer: OwnerBookingCustomer
    slot: OwnerBookingSlot
    payment: OwnerBookingPayment | None
