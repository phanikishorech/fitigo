from __future__ import annotations

from pydantic import BaseModel, Field


class AdminForceCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdminUpdatePaymentStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=30)
    external_ref: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=500)
