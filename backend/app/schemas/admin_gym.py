from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal
from app.schemas.gym import GymSubmissionResponse


class GymReviewHistoryItem(BaseModel):
    id: int
    old_status: str
    new_status: str
    reason: str | None
    created_at: datetime


class AdminGymDetails(GymSubmissionResponse):
    allowed_actions: list[Literal['APPROVE', 'REJECT']] = Field(default_factory=list)
    review_history: list[GymReviewHistoryItem] = Field(default_factory=list)


class RejectGymRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SuspendGymRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
