from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


class UserMeResponse(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    email: EmailStr
    phone: str | None
    status: str
    created_at: datetime
    is_email_verified: bool = False
    is_phone_verified: bool = False


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default='', max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, pattern=r'^\+?[1-9][0-9]{7,14}$')
    current_password: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('first_name', 'last_name', 'email', 'phone', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value
