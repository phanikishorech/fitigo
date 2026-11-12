from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
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
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.schemas.auth import ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest
from app.services.password_service import PasswordService, email_ready
from app.core.config import settings
from app.services import account_delivery
from app.services.staff_invitation_service import StaffInvitationService
from app.schemas.staff import InvitationTokenRequest, AcceptInvitationRequest
from app.schemas.auth import SessionResponse, AuthSessionResponse
from app.repositories.user_repository import UserRepository


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix="/auth", dependencies=[Depends(no_store)])


@router.post('/staff-invitations/inspect')
def inspect_invitation(payload: InvitationTokenRequest, request: Request, db: Session = Depends(get_db)):
    return StaffInvitationService(db).inspect(payload.token, request.client.host if request.client else 'unknown')


@router.post('/staff-invitations/accept')
def accept_invitation(payload: AcceptInvitationRequest, request: Request, db: Session = Depends(get_db)):
    return StaffInvitationService(db).accept(payload.token, payload.new_password, payload.current_password,
                                              request.client.host if request.client else 'unknown')


@router.get('/otp/options')
def otp_options():
    return {'email_available': account_delivery.email_ready(), 'mobile_available': account_delivery.sms_ready(),
            'expiry_seconds': settings.otp_expiry_seconds, 'resend_seconds': settings.otp_resend_seconds}


def session_response(db: Session, user: User) -> dict:
    return {'user': user_to_public_dict(user), 'roles': UserRepository(db).get_role_names(user.id)}


@router.get('/session', response_model=SessionResponse)
def authenticated_session(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return session_response(db, current_user)


@router.get('/password-reset/options')
def password_reset_options():
    return {'email_available': email_ready(), 'expiry_minutes': settings.password_reset_expiry_minutes}


@router.post('/forgot-password')
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    PasswordService(db).request_reset(str(payload.email).lower(), request.client.host if request.client else 'unknown')
    PasswordService(db).deliver_reset(str(payload.email).lower())
    return {'message': 'The email provider accepted the request. If you have an active account, the link can reset your password.',
            'delivery_status': 'PROVIDER_ACCEPTED', 'expiry_minutes': settings.password_reset_expiry_minutes}


@router.post('/reset-password')
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    PasswordService(db).reset(payload.token, payload.new_password, request.client.host if request.client else 'unknown')
    return {'status': 'ok'}


@router.post('/change-password')
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    PasswordService(db).change(current_user.id, payload.current_password, payload.new_password, current_user.token_version)
    return {'status': 'ok'}


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


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    access, refresh = svc.login(email=str(payload.email).lower(), password=payload.password)
    user = UserRepository(db).get_by_email(str(payload.email).lower())
    return AuthSessionResponse(access_token=access, refresh_token=refresh, **session_response(db, user))


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
def email_send_otp(payload: EmailSendOtpRequest, request: Request, db: Session = Depends(get_db)):
    svc = OtpService(db)
    svc.send_email_otp(email=str(payload.email).lower(), client_ip=request.client.host if request.client else 'unknown')
    return {"status": "ok", "delivery_status": "PROVIDER_ACCEPTED", "resend_seconds": settings.otp_resend_seconds}


@router.post("/email/verify-otp", response_model=dict)
def email_verify_otp(payload: EmailVerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    svc = OtpService(db)
    access, refresh, user = svc.verify_email_otp(email=str(payload.email).lower(), otp=payload.otp, client_ip=request.client.host if request.client else 'unknown')
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_to_public_dict(user),
        "roles": UserRepository(db).get_role_names(user.id),
    }


@router.post("/mobile/send-otp", response_model=dict)
def mobile_send_otp(payload: MobileSendOtpRequest, request: Request, db: Session = Depends(get_db)):
    svc = OtpService(db)
    svc.send_mobile_otp(country_code=payload.country_code, mobile_number=payload.mobile_number, client_ip=request.client.host if request.client else 'unknown')
    return {"status": "ok", "delivery_status": "PROVIDER_ACCEPTED", "resend_seconds": settings.otp_resend_seconds}


@router.post("/mobile/verify-otp", response_model=dict)
def mobile_verify_otp(payload: MobileVerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    svc = OtpService(db)
    access, refresh, user = svc.verify_mobile_otp(
        country_code=payload.country_code,
        mobile_number=payload.mobile_number,
        otp=payload.otp,
        client_ip=request.client.host if request.client else 'unknown',
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_to_public_dict(user),
        "roles": UserRepository(db).get_role_names(user.id),
    }
