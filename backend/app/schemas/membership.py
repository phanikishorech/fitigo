from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MembershipPlanCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    duration_days: int = Field(ge=1, le=3660)
    price: str = Field(pattern=r"^\d+(\.\d{1,2})?$")
    currency: str = Field(default="INR", max_length=10)


class MembershipPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    duration_days: int | None = Field(default=None, ge=1, le=3660)
    price: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")
    currency: str | None = Field(default=None, max_length=10)
    is_active: bool | None = None


class MembershipPlanResponse(BaseModel):
    id: int
    gym_id: int
    name: str
    description: str | None
    duration_days: int
    price: str
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PurchaseMembershipRequest(BaseModel):
    plan_id: int


class UserMembershipResponse(BaseModel):
    id: int
    user_id: int
    gym_id: int
    plan_id: int
    status: str
    start_at: datetime
    end_at: datetime
    cancelled_at: datetime | None
    paid_amount: str
    currency: str
    payment_provider: str
    payment_status: str
    external_ref: str | None
    created_at: datetime
    updated_at: datetime
