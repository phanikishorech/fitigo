from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserMeResponse(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: EmailStr
    phone: str | None
    status: str
    created_at: datetime
