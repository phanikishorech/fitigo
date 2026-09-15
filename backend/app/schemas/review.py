from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    id: int
    gym_id: int
    user_id: int
    rating: int
    comment: str | None
    status: str
    created_at: datetime
    updated_at: datetime
