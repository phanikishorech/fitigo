from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from app.schemas.time import ISTResponse


class InviteStaffRequest(BaseModel):
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
