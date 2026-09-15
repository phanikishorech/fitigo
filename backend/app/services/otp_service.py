from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.roles import ROLE_CUSTOMER
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.auth import RefreshToken, User
from app.repositories.user_repository import UserRepository


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class _OtpRecord:
    otp_hash: str
    expires_at_epoch: float
    attempts_left: int
    last_sent_epoch: float


class OtpService:
    """Email/Mobile OTP service.

    Local MVP implementation:
    - OTP state is stored in-memory (per-process).
    - In production, move to Redis or a DB table.
    - OTP is never returned in API responses.
    """

    _email_store: dict[str, _OtpRecord] = {}
    _mobile_store: dict[str, _OtpRecord] = {}

    OTP_TTL_SECONDS = 10 * 60
    RESEND_COOLDOWN_SECONDS = 30
    MAX_VERIFY_ATTEMPTS = 5

    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def _generate_otp(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _rate_limit_send(self, store: dict[str, _OtpRecord], key: str) -> None:
        rec = store.get(key)
        if not rec:
            return
        now = time.time()
        if now - rec.last_sent_epoch < self.RESEND_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {int(self.RESEND_COOLDOWN_SECONDS - (now - rec.last_sent_epoch))}s before resending.",
            )

    def send_email_otp(self, *, email: str) -> None:
        email = email.strip().lower()
        self._rate_limit_send(self._email_store, email)

        otp = self._generate_otp()
        now = time.time()
        self._email_store[email] = _OtpRecord(
            otp_hash=_sha256_hex(otp),
            expires_at_epoch=now + self.OTP_TTL_SECONDS,
            attempts_left=self.MAX_VERIFY_ATTEMPTS,
            last_sent_epoch=now,
        )

        # TODO: integrate real email provider.
        return None

    def verify_email_otp(self, *, email: str, otp: str):
        email = email.strip().lower()
        rec = self._email_store.get(email)
        if not rec:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not requested")
        if time.time() > rec.expires_at_epoch:
            self._email_store.pop(email, None)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
        if rec.attempts_left <= 0:
            self._email_store.pop(email, None)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attempts")

        if _sha256_hex(otp) != rec.otp_hash:
            rec.attempts_left -= 1
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

        self._email_store.pop(email, None)

        user = self.repo.get_by_email(email)
        if not user:
            user = User(
                first_name=None,
                last_name=None,
                email=email,
                phone=None,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                status="ACTIVE",
                is_email_verified=True,
                is_phone_verified=False,
            )
            role = self.repo.get_or_create_role(ROLE_CUSTOMER)
            self.repo.create_user(user)
            self.repo.assign_role(user.id, role.id)
        else:
            user.is_email_verified = True

        access_token = create_access_token(str(user.id))
        refresh_token, refresh_exp = create_refresh_token(str(user.id))
        rt = RefreshToken(
            user_id=user.id,
            token_hash=_sha256_hex(refresh_token),
            expires_at=refresh_exp,
            revoked_at=None,
        )
        self.repo.store_refresh_token(rt)
        self.db.commit()

        return access_token, refresh_token, user

    def send_mobile_otp(self, *, country_code: str, mobile_number: str) -> None:
        cc = country_code.strip()
        num = mobile_number.strip()
        key = f"{cc}:{num}"
        self._rate_limit_send(self._mobile_store, key)

        otp = self._generate_otp()
        now = time.time()
        self._mobile_store[key] = _OtpRecord(
            otp_hash=_sha256_hex(otp),
            expires_at_epoch=now + self.OTP_TTL_SECONDS,
            attempts_left=self.MAX_VERIFY_ATTEMPTS,
            last_sent_epoch=now,
        )

        # TODO: integrate SMS provider.
        return None

    def verify_mobile_otp(self, *, country_code: str, mobile_number: str, otp: str):
        cc = country_code.strip()
        num = mobile_number.strip()
        key = f"{cc}:{num}"
        rec = self._mobile_store.get(key)
        if not rec:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not requested")
        if time.time() > rec.expires_at_epoch:
            self._mobile_store.pop(key, None)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
        if rec.attempts_left <= 0:
            self._mobile_store.pop(key, None)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attempts")

        if _sha256_hex(otp) != rec.otp_hash:
            rec.attempts_left -= 1
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

        self._mobile_store.pop(key, None)

        phone = f"{cc}{num}"
        user = self.repo.get_by_phone(phone)
        if not user:
            user = User(
                first_name=None,
                last_name=None,
                email=f"user_{secrets.token_hex(10)}@placeholder.local",
                phone=phone,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                status="ACTIVE",
                is_email_verified=False,
                is_phone_verified=True,
            )
            role = self.repo.get_or_create_role(ROLE_CUSTOMER)
            self.repo.create_user(user)
            self.repo.assign_role(user.id, role.id)
        else:
            user.is_phone_verified = True

        access_token = create_access_token(str(user.id))
        refresh_token, refresh_exp = create_refresh_token(str(user.id))
        rt = RefreshToken(
            user_id=user.id,
            token_hash=_sha256_hex(refresh_token),
            expires_at=refresh_exp,
            revoked_at=None,
        )
        self.repo.store_refresh_token(rt)
        self.db.commit()

        return access_token, refresh_token, user


def user_to_public_dict(user: User) -> dict:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "created_at": user.created_at.replace(tzinfo=timezone.utc).isoformat()
        if user.created_at
        else datetime.now(timezone.utc).isoformat(),
    }
