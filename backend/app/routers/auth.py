from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.auth import (
    CustomerRegisterRequest,
    GymOwnerRegisterRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.core.roles import ROLE_CUSTOMER, ROLE_GYM_OWNER
from app.services.auth_service import AuthService
from app.schemas.otp_auth import (
    EmailSendOtpRequest,
    EmailVerifyOtpRequest,
    MobileSendOtpRequest,
    MobileVerifyOtpRequest,
)
from app.services.otp_service import OtpService, user_to_public_dict


router = APIRouter(prefix="/auth")


@router.post("/register/customer", response_model=dict)
def register_customer(payload: CustomerRegisterRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user = svc.register_user(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email).lower(),
        phone=payload.phone,
        password=payload.password,
        role_name=ROLE_CUSTOMER,
    )
    return {"id": user.id, "email": user.email}


@router.post("/register/gym-owner", response_model=dict)
def register_gym_owner(payload: GymOwnerRegisterRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user = svc.register_user(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email).lower(),
        phone=payload.phone,
        password=payload.password,
        role_name=ROLE_GYM_OWNER,
    )
    return {"id": user.id, "email": user.email}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    access, refresh = svc.login(email=str(payload.email).lower(), password=payload.password)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    access, refresh_token = svc.refresh(refresh_token=payload.refresh_token)
    return TokenResponse(access_token=access, refresh_token=refresh_token)


@router.post("/logout", response_model=dict)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    svc.logout(refresh_token=payload.refresh_token)
    return {"status": "ok"}


@router.post("/email/send-otp", response_model=dict)
def email_send_otp(payload: EmailSendOtpRequest, db: Session = Depends(get_db)):
    svc = OtpService(db)
    svc.send_email_otp(email=str(payload.email).lower())
    return {"status": "ok"}


@router.post("/email/verify-otp", response_model=dict)
def email_verify_otp(payload: EmailVerifyOtpRequest, db: Session = Depends(get_db)):
    svc = OtpService(db)
    access, refresh, user = svc.verify_email_otp(email=str(payload.email).lower(), otp=payload.otp)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_to_public_dict(user),
    }


@router.post("/mobile/send-otp", response_model=dict)
def mobile_send_otp(payload: MobileSendOtpRequest, db: Session = Depends(get_db)):
    svc = OtpService(db)
    svc.send_mobile_otp(country_code=payload.country_code, mobile_number=payload.mobile_number)
    return {"status": "ok"}


@router.post("/mobile/verify-otp", response_model=dict)
def mobile_verify_otp(payload: MobileVerifyOtpRequest, db: Session = Depends(get_db)):
    svc = OtpService(db)
    access, refresh, user = svc.verify_mobile_otp(
        country_code=payload.country_code,
        mobile_number=payload.mobile_number,
        otp=payload.otp,
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_to_public_dict(user),
    }
