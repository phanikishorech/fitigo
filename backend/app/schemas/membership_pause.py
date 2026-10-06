from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PausePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool = False
    max_pause_days: int = Field(default=0, ge=0, le=3660, strict=True)

    @model_validator(mode="after")
    def valid_policy(self):
        if self.allowed and self.max_pause_days == 0:
            raise ValueError("Enabled pause requires a positive allowance")
        if not self.allowed and self.max_pause_days != 0:
            raise ValueError("Disabled pause must have zero allowance")
        return self


class PauseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    days: int = Field(gt=0, le=3660, strict=True)


class PauseConfirm(PauseRequest):
    accepted_preview: str = Field(pattern=r"^[a-f0-9]{64}$")


class PausePeriod(BaseModel):
    id: int
    start_date: date
    end_date: date
    resumes_on: date
    days: int
    status: str
    previous_end_at: datetime
    new_end_at: datetime


class PauseEligibility(BaseModel):
    membership_id: int
    membership_status: str
    pause_allowed: bool
    can_pause: bool
    max_pause_days: int
    pause_days_used: int
    pause_days_remaining: int
    currently_paused: bool
    eligible_from: date | None
    eligible_until: date | None
    original_end_at: datetime
    current_end_at: datetime
    current_pause: PausePeriod | None
    history: list[PausePeriod]
    reason_code: str | None
    timezone: str = "UTC"


class PausePreview(BaseModel):
    membership_id: int
    start_date: date
    end_date: date
    resumes_on: date
    days: int
    current_end_at: datetime
    new_end_at: datetime
    pause_days_remaining_after: int
    preview_token: str