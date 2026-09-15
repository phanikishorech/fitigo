from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class AccessTypeOption(BaseModel):
    id: str
    name: str
    type: str
    icon: str | None = None
    membership_included: bool = False
    additional_price: str | None = None


class MembershipStatusBanner(BaseModel):
    status: str
    title: str
    subtitle: str | None = None
    tone: str = Field(default="info")


class GymBookingOptionsResponse(BaseModel):
    gym_id: int
    gym_name: str
    locality: str | None = None
    city: str | None = None

    membership_status: MembershipStatusBanner
    available_access_types: list[AccessTypeOption]
    workout_areas: list[dict]

    # New Add-to-Cart booking model fields
    gym_price_per_person: str | None = None
    has_classes: bool = False
    classes_available: bool = False
    classes_unavailable_message: str | None = None


class ValidateBookingRequest(BaseModel):
    access_type_id: str
    gym_slot_id: int
    slot_date: date
    quantity: int = Field(ge=1, le=50)

    # Optional/forward-compat
    duration_minutes: int | None = Field(default=None, ge=15, le=360)
    workout_area_id: str | None = None
    resource_id: str | None = None


class ValidateBookingResponse(BaseModel):
    available: bool
    availability_message: str
    membership_eligible: bool

    currency: str
    price: str
    discount: str
    tax: str
    total: str


class CreateAccessBookingRequest(BaseModel):
    items: list[ValidateBookingRequest] = Field(min_length=1, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)


class CreateAccessBookingItemResult(BaseModel):
    booking_id: int
    status: str
    payment_status: str | None = None
    total: str
    currency: str


class CreateAccessBookingResponse(BaseModel):
    results: list[CreateAccessBookingItemResult]
