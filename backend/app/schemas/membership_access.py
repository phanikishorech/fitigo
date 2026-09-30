from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class MembershipCalendarResponse(BaseModel):
    gym_id: int

    # Membership validity window for this gym.
    membership_start: datetime
    membership_end: datetime

    # Month context (UI convenience)
    month: str = Field(description="YYYY-MM")
    month_start: date
    month_end: date

    accessed_dates: list[date] = Field(default_factory=list)


class MembershipDailyQRResponse(BaseModel):
    gym_id: int
    access_date: date
    scanned: bool = False
    scanned_at: datetime | None = None
    qr_payload: str | None = None
    status: str
    expires_at: datetime | None = None


class ScanMembershipQRRequest(BaseModel):
    qr_payload: str = Field(min_length=10)
    gym_id: int | None = Field(default=None, ge=1)


class ScanMembershipQRResponse(BaseModel):
    gym_id: int
    user_id: int
    access_date: date
    status: str
    scanned_at: datetime