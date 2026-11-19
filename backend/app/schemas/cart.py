from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.schemas.visitors import VisitorName


class CartItemCreateGymRequest(BaseModel):
    visitor_names: list[VisitorName] | None = Field(default=None, min_length=1, max_length=50)
    booking_type: str = Field(default="GYM")
    gym_id: int
    booking_date: date
    preferred_start_time: time
    preferred_end_time: time | None = None
    member_count: int = Field(default=1, ge=1, le=50)


class CartItemCreateClassRequest(BaseModel):
    visitor_names: list[VisitorName] | None = Field(default=None, min_length=1, max_length=50)
    booking_type: str = Field(default="CLASS")
    gym_id: int
    class_session_id: int
    booking_date: date
    member_count: int = Field(default=1, ge=1, le=50)


class CartItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    booking_type: Literal['GYM', 'CLASS']
    gym_id: int = Field(gt=0)
    booking_date: date
    member_count: int = Field(ge=1, le=50)
    visitor_names: list[VisitorName] = Field(min_length=1, max_length=50)
    preferred_start_time: time | None = None
    preferred_end_time: time | None = None
    class_session_id: int | None = Field(default=None, gt=0)
    expected_updated_at: datetime

    @model_validator(mode='after')
    def validate_selection(self):
        if self.booking_type == 'GYM' and (self.preferred_start_time is None or self.class_session_id is not None):
            raise ValueError('Gym visits require a start time and cannot include a class session.')
        if self.booking_type == 'CLASS' and (self.class_session_id is None or self.preferred_start_time is not None or self.preferred_end_time is not None):
            raise ValueError('Choose a class session; its schedule determines the visit times.')
        return self


class CartItemResponse(BaseModel):
    updated_at: datetime
    can_edit: bool = False
    visitor_names: list[str] | None = None
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
