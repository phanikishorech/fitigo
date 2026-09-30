from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field


class CalendarGym(BaseModel):
    id: int
    name: str


class AccessCalendarDay(BaseModel):
    date: date
    status: str
    qr_available: bool = False
    qr_status: str | None = None

    gym_id: int | None = None
    gym_name: str | None = None
    checkin_time: time | None = None


class AccessCalendarResponse(BaseModel):
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)

    access_type: str | None = None  # SINGLE_GYM | MULTI_GYM
    gym: CalendarGym | None = None

    days: list[AccessCalendarDay]


class TodayAccessGym(BaseModel):
    id: int
    name: str


class TodayAccessActiveResponse(BaseModel):
    status: Literal["ACTIVE"] = "ACTIVE"
    access_type: str
    gym: TodayAccessGym | None = None
    qr_token: str
    expires_at: datetime


class TodayAccessUsedResponse(BaseModel):
    status: Literal["USED"] = "USED"
    gym_name: str | None = None
    used_at: datetime


class TodayAccessPausedResponse(BaseModel):
    status: Literal["PAUSED"] = "PAUSED"


class TodayAccessExpiredResponse(BaseModel):
    status: Literal["EXPIRED"] = "EXPIRED"


class TodayAccessNoAccessResponse(BaseModel):
    status: Literal["NO_ACCESS"] = "NO_ACCESS"


TodayAccessResponse = (
    TodayAccessActiveResponse
    | TodayAccessUsedResponse
    | TodayAccessPausedResponse
    | TodayAccessExpiredResponse
    | TodayAccessNoAccessResponse
)


class ValidateCheckinRequest(BaseModel):
    qr_token: str = Field(min_length=10)
    gym_id: int = Field(ge=1)


class ValidateCheckinSuccessResponse(BaseModel):
    success: bool = True
    status: str = "CHECKED_IN"
    customer_name: str
    gym_name: str
    access_type: str
    checkin_time: datetime


class ValidateCheckinFailureResponse(BaseModel):
    success: bool = False
    status: str
    message: str
