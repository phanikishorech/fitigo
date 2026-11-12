from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class EmailSendOtpRequest(BaseModel):
    email: EmailStr


class EmailVerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r'^[0-9]{6}$')


class MobileSendOtpRequest(BaseModel):
    country_code: str = Field(pattern=r'^\+[1-9][0-9]{0,2}$', examples=["+1"])
    mobile_number: str = Field(pattern=r'^[0-9]{6,14}$')


class MobileVerifyOtpRequest(BaseModel):
    country_code: str = Field(pattern=r'^\+[1-9][0-9]{0,2}$')
    mobile_number: str = Field(pattern=r'^[0-9]{6,14}$')
    otp: str = Field(pattern=r'^[0-9]{6}$')


class OtpVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
