from __future__ import annotations

from datetime import date, datetime, time
from app.schemas.time import ISTResponse

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from app.schemas.booking import CANCELLATION_MESSAGE


class OwnerBookingActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)


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


class OwnerBookingResponse(ISTResponse):
    allowed_actions: list[Literal['CANCEL', 'MARK_ATTENDED', 'MARK_NO_SHOW']] = Field(default_factory=list)
    action_unavailable_reasons: dict[str, str] = Field(default_factory=dict)
    cancellation_policy: str = CANCELLATION_MESSAGE
    refund_initiated: Literal[False] = False
    cancellation_message: str = CANCELLATION_MESSAGE
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
