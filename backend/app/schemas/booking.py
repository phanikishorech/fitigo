from __future__ import annotations
from app.schemas.time import ISTResponse

from datetime import date, datetime

from pydantic import BaseModel, Field
from app.schemas.visitors import VisitorName
from app.models.access import AccessSource


class BookingAccessPassStatus(ISTResponse):
    qr_id: int
    status: str
    visitor_name: str | None = None
    checked_in_at: datetime | None = None


class BookingAccessResponse(ISTResponse):
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    access_type: AccessSource
    status: str
    message: str
    qr_available: bool
    can_set_visitors: bool
    passes: list[BookingAccessPassStatus]


class BookingQrPassResponse(BookingAccessPassStatus):
    visitor_name: str
    qr_token: str | None
    valid_from: datetime
    expires_at: datetime


class BookingQrResponse(ISTResponse):
    booking_id: int
    access_type: AccessSource
    passes: list[BookingQrPassResponse]


class BookingCreateRequest(BaseModel):
    visitor_names: list[VisitorName] | None = Field(default=None, min_length=1, max_length=50)
    gym_slot_id: int
    slot_date: date
    quantity: int = Field(ge=1, le=50)
    notes: str | None = Field(default=None, max_length=2000)


class PaymentResponse(ISTResponse):
    id: int
    provider: str
    status: str
    amount: str
    currency: str
    external_ref: str | None
    created_at: datetime
    updated_at: datetime


class BookingResponse(ISTResponse):
    visitor_names: list[str] | None = None
    access: BookingAccessResponse
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
