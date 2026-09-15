from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    user_id: int
    full_name: str
    profile_image: str | None = None
    member_since: datetime
    membership_status: str | None = None


class MembershipSummaryResponse(BaseModel):
    membership_id: int | None = None
    plan_name: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None

    # Clarify scope
    membership_scope: str | None = None  # SINGLE_GYM | MULTI_GYM
    active_gyms: list[dict] = Field(default_factory=list)

    gym_access_count: int = 0
    remaining_visits: int | None = None
    total_visits: int | None = None

    # Usage stats (MVP - derived from bookings)
    visits_booked: int | None = None
    visits_completed: int | None = None

    # Pause policy (MVP: not implemented yet, but we surface limits clearly)
    pause_days_used: int | None = None
    pause_days_remaining: int | None = None
    membership_features: list[str] = Field(default_factory=list)


class BookingItemResponse(BaseModel):
    booking_id: int
    booking_status: str
    attendance_status: str | None = None

    gym_id: int
    gym_name: str
    gym_location: str

    access_type: str
    class_name: str | None = None

    visit_date: date
    start_time: time
    end_time: time

    membership_covered: bool
    amount_paid: str | None = None
    currency: str

    booking_created_at: datetime
    cancelled_at: datetime | None = None


class ActivityBreakdownItem(BaseModel):
    key: str
    label: str
    count: int


class ProfileActivityResponse(BaseModel):
    total_gym_visits: int
    total_classes_attended: int
    current_streak_days: int
    partner_gyms_visited: int
    activity_breakdown: list[ActivityBreakdownItem] = Field(default_factory=list)


class FavoriteGymItem(BaseModel):
    gym_id: int
    gym_name: str
    gym_location: str
    visit_count: int


class FavoritesResponse(BaseModel):
    gyms: list[FavoriteGymItem] = Field(default_factory=list)


class MembershipPassResponse(BaseModel):
    member_id: str
    full_name: str
    plan_name: str | None = None
    status: str | None = None
    valid_until: datetime | None = None
    qr_payload: str
    gym_access_count: int = 0

    # Extra context for UI
    membership_scope: str | None = None
    active_gyms: list[dict] = Field(default_factory=list)
    visits_booked: int | None = None
    visits_completed: int | None = None
    pause_days_used: int | None = None
    pause_days_remaining: int | None = None
