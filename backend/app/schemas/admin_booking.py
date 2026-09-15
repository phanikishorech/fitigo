from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel


class AdminBookingCustomer(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: str
    phone: str | None


class AdminBookingGym(BaseModel):
    id: int
    name: str
    city: str | None
    status: str
    is_active: bool
    owner_user_id: int


class AdminBookingSlot(BaseModel):
    id: int
    name: str
    start_time: time
    end_time: time


class AdminBookingPayment(BaseModel):
    id: int
    provider: str
    status: str
    amount: str
    currency: str
    external_ref: str | None


class AdminBookingResponse(BaseModel):
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
    attendance_status: str | None
    attendance_marked_at: datetime | None
    attendance_note: str | None

    customer: AdminBookingCustomer
    gym: AdminBookingGym
    slot: AdminBookingSlot
    payment: AdminBookingPayment | None
