from __future__ import annotations

from pydantic import BaseModel, Field


class LocationSuggestion(BaseModel):
    location_name: str = Field(..., max_length=120)
    latitude: float
    longitude: float

    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)

    # Not required by the frontend, but useful for ordering/UX.
    gym_count: int | None = Field(default=None, ge=0)
