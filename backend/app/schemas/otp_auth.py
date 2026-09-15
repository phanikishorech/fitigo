from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class EmailSendOtpRequest(BaseModel):
    email: EmailStr


class EmailVerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=8)


class MobileSendOtpRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=5, examples=["+1"])
    mobile_number: str = Field(min_length=6, max_length=15)


class MobileVerifyOtpRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=5)
    mobile_number: str = Field(min_length=6, max_length=15)
    otp: str = Field(min_length=4, max_length=8)


class OtpVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
