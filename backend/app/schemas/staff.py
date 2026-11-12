from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime
from app.schemas.time import ISTResponse


class InviteStaffRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)


class StaffAssignmentResponse(ISTResponse):
    id: int
    gym_id: int
    user_id: int
    role: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    account_status: str | None = None
    assigned_at: datetime


class InvitationTokenRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=32, max_length=128)


class AcceptInvitationRequest(InvitationTokenRequest):
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    current_password: str | None = Field(default=None, min_length=1, max_length=128)
