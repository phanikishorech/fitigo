from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminUserListItem(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: EmailStr
    phone: str | None
    status: str
    created_at: datetime
    roles: list[str] = []


class AdminUserDetail(AdminUserListItem):
    # Placeholder for future: last_login_at, etc.
    pass


class AdminUpdateUserStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=50)
    reason: str | None = Field(default=None, max_length=500)
