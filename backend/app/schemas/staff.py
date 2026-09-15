from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class InviteStaffRequest(BaseModel):
    email: EmailStr
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)


class StaffAssignmentResponse(BaseModel):
    id: int
    gym_id: int
    user_id: int
    role: str
