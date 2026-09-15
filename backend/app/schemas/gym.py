from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field


class GymCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)

    # Pricing
    # Keep as string to preserve 2-decimal money formatting consistency across the API.
    gym_price_per_person: str = Field(default="0.00", pattern=r"^\d+(\.\d{1,2})?$")
    # Feature flag for class booking flow (public /class-sessions endpoint checks this)
    has_classes: bool = False

    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: str | None = Field(default=None, max_length=50)
    longitude: str | None = Field(default=None, max_length=50)


class GymUpdateRequest(GymCreateRequest):
    is_active: bool | None = None


class GymImageResponse(BaseModel):
    id: int
    file_path: str
    original_filename: str | None
    image_type: str | None
    display_order: int
    is_cover: bool
    created_at: datetime


class GymFacilityResponse(BaseModel):
    id: int
    name: str
    description: str | None
    icon: str | None


class GymOperatingHoursItem(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False


class GymResponse(BaseModel):
    id: int
    owner_user_id: int
    name: str
    description: str | None
    phone: str | None
    email: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    country: str | None
    postal_code: str | None
    latitude: str | None
    longitude: str | None
    status: str
    is_active: bool

    gym_price_per_person: str = "0.00"
    has_classes: bool = False
    created_at: datetime
    updated_at: datetime
    images: list[GymImageResponse] = []
    facilities: list[GymFacilityResponse] = []
    operating_hours: list[GymOperatingHoursItem] = []


class GymListItem(BaseModel):
    id: int
    name: str
    city: str | None
    status: str
    is_active: bool
    created_at: datetime
    # Optional field returned by geo search (/gyms?lat=..&lon=..)
    distance_km: float | None = None
    # Optional cover image URL for card views (if a cover image exists)
    cover_image_url: str | None = None


class GymDiscoverItem(BaseModel):
    gym_id: int
    gym_name: str
    primary_image: str | None = None
    images: list[str] = []
    latitude: str | None = None
    longitude: str | None = None
    address: str | None = None
    locality: str | None = None
    city: str | None = None
    distance_km: float | None = None
    average_rating: float | None = None
    review_count: int = 0
    facilities: list[GymFacilityResponse] = []
    is_featured: bool = False
    membership_access_status: str | None = None
    required_membership_tier: str | None = None
    active_promotion: str | None = None
    is_open_now: bool | None = None


class GymDiscoverResponse(BaseModel):
    total_count: int
    page: int
    page_size: int
    has_more: bool
    gyms: list[GymDiscoverItem]


class SetGymFacilitiesRequest(BaseModel):
    facility_ids: list[int] = Field(default_factory=list)


class SetGymOperatingHoursRequest(BaseModel):
    items: list[GymOperatingHoursItem]
