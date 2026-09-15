from __future__ import annotations

from pydantic import BaseModel, Field


class RejectGymRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SuspendGymRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
