from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field


class GymDetailsImage(BaseModel):
    image_id: int
    image_url: str
    alt_text: str | None = None
    display_order: int = 0


class GymDetailsLocation(BaseModel):
    locality: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    full_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class GymDetailsRatings(BaseModel):
    average_rating: float | None = None
    review_count: int = 0
    user_rating: int | None = Field(default=None, ge=1, le=5)


class GymDetailsOpeningHoursItem(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False


class GymDetailsOpeningHours(BaseModel):
    open_now: bool | None = None
    open_today: str | None = None
    weekly: list[GymDetailsOpeningHoursItem] = []


class GymAmenity(BaseModel):
    amenity_id: int
    amenity_name: str
    icon: str | None = None


class GymWorkoutOption(BaseModel):
    workout_type_id: int
    workout_type_name: str
    icon: str | None = None
    # MVP: always INCLUDED; later can become more complex
    access_type: str = "INCLUDED"
    additional_fee: str | None = None
    membership_requirement: str | None = None


class GymMembershipAccess(BaseModel):
    status: str
    current_plan: str | None = None
    required_plan: str | None = None
    upgrade_required: bool = False
    day_pass_available: bool = False
    day_pass_price: str | None = None


class GymClassCard(BaseModel):
    class_id: int
    kind: str
    status: str
    title: str
    gym_name: str
    start_at: datetime
    end_at: datetime
    level: str | None = None
    filled: int = 0
    capacity: int = 0


class GymMemberReview(BaseModel):
    review_id: int
    user_display_name: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    created_at: datetime


class RelatedGymItem(BaseModel):
    gym_id: int
    gym_name: str
    primary_image: str | None = None
    locality: str | None = None
    city: str | None = None
    distance_km: float | None = None
    average_rating: float | None = None
    review_count: int = 0
    membership_access_status: str | None = None


class GymDetailsResponse(BaseModel):
    gym_id: int
    gym_name: str
    slug: str

    location: GymDetailsLocation
    ratings: GymDetailsRatings
    images: list[GymDetailsImage] = []
    opening_hours: GymDetailsOpeningHours

    workout_options: list[GymWorkoutOption] = []
    amenities: list[GymAmenity] = []

    description: str | None = None
    important_information: list[str] = []
    rules: list[str] = []

    membership_access: GymMembershipAccess

    classes_nearby: list[GymClassCard] = []
    related_gyms: list[RelatedGymItem] = []
    reviews: list[GymMemberReview] = []
    reviews_summary: dict | None = None
