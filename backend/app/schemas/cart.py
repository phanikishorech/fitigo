from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field


class CartItemCreateGymRequest(BaseModel):
    booking_type: str = Field(default="GYM")
    gym_id: int
    booking_date: date
    preferred_start_time: time
    preferred_end_time: time
    member_count: int = Field(default=1, ge=1, le=50)


class CartItemCreateClassRequest(BaseModel):
    booking_type: str = Field(default="CLASS")
    gym_id: int
    class_session_id: int
    booking_date: date
    member_count: int = Field(default=1, ge=1, le=50)


class CartItemResponse(BaseModel):
    id: int
    booking_type: str
    gym_id: int
    class_session_id: int | None = None
    booking_date: date
    preferred_start_time: time | None = None
    preferred_end_time: time | None = None
    member_count: int
    price_per_person: str
    total_price: str
    currency: str
    status: str

    # helpful display fields
    gym_name: str | None = None
    class_name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    available_capacity: int | None = None


class CartCheckoutResponse(BaseModel):
    confirmed_items: list[CartItemResponse]
    total_amount: str
    currency: str = "INR"


class CartWalletCheckoutResponse(CartCheckoutResponse):
    wallet_balance_before: str
    wallet_balance_after: str
    wallet_transaction_id: int
    booking_ids: list[int] = Field(default_factory=list)
