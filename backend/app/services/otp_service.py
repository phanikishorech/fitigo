"""Persistent, purpose-bound single-use login OTPs; real provider acceptance only."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import ROLE_CUSTOMER
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.auth import AccountOtp, RefreshToken, User
from app.repositories.user_repository import UserRepository
from app.services import account_delivery
from app.services.password_service import PasswordService, as_utc, digest, now


def mobile_address(country_code, mobile_number):
    number = country_code.strip() + mobile_number.strip()
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', number):
        raise HTTPException(400, 'Enter a valid international mobile number.')
    return number


def code_digest(key, nonce, code):
    # A database dump alone must not permit enumerating the million possible codes.
    return hmac.new(settings.jwt_secret.get_secret_value().encode(),
                    f'account-otp:{key}:{nonce}:{code}'.encode(), hashlib.sha256).hexdigest()


class OtpService:
    def __init__(self, db: Session):
        self.db, self.repo = db, UserRepository(db)

    def _generate_otp(self):
        return f'{secrets.randbelow(1_000_000):06d}'

    def _send(self, channel, address, client_ip):
        rate = PasswordService(self.db)
        rate.throttle(f'otp-send-ip:{client_ip}', 20, 900)
        rate.throttle(f'otp-send:{channel}:{address}', settings.otp_send_limit, 900)
        rate.throttle(f'otp-resend:{channel}:{address}', 1, settings.otp_resend_seconds)
        if not (account_delivery.email_ready() if channel == 'email' else account_delivery.sms_ready()):
            raise account_delivery.unavailable()
        key = digest(f'LOGIN:{channel}:{address}')
        code, nonce = self._generate_otp(), secrets.token_hex(32)
        try:
            user = self.repo.get_by_email(address) if channel == 'email' else self.repo.get_by_phone(address)
            record = self.db.scalar(select(AccountOtp).where(AccountOtp.key == key).with_for_update())
            if record is None:
                record = AccountOtp(key=key); self.db.add(record)
            record.channel, record.purpose = channel, 'LOGIN'
            record.user_id = user.id if user else None
            record.token_version = user.token_version if user else None
            record.nonce, record.code_hash = nonce, code_digest(key, nonce, code)
            record.expires_at = now() + timedelta(seconds=settings.otp_expiry_seconds)
            record.attempts_left, record.used_at = settings.otp_max_attempts, None
            self.db.flush()
            message = (f'Your FitiGo sign-in code is {code}. It expires in {settings.otp_expiry_seconds // 60} minutes. '
                       'Do not share this code. Ignore this message if you did not request it.')
            if channel == 'email':
                account_delivery.send_email(address, 'Your FitiGo sign-in code', message)
            else:
                account_delivery.send_sms(address, message)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise account_delivery.unavailable(True) from None

    def _verify(self, channel, address, code, client_ip):
        rate = PasswordService(self.db)
        rate.throttle(f'otp-verify-ip:{client_ip}', 40, 900)
        rate.throttle(f'otp-verify:{channel}:{address}', 15, 900)
        key = digest(f'LOGIN:{channel}:{address}')
        invalid = HTTPException(400, 'This verification code is invalid or expired. Request a new code.')
        initial = self.db.get(AccountOtp, key)
        # Match password-change lock order: user first, then token/challenge.
        user = None
        if initial and initial.user_id:
            user = self.db.scalar(select(User).where(User.id == initial.user_id).with_for_update().execution_options(populate_existing=True))
        record = self.db.scalar(select(AccountOtp).where(AccountOtp.key == key).with_for_update().execution_options(populate_existing=True))
        if not record or record.purpose != 'LOGIN' or record.channel != channel or record.used_at or as_utc(record.expires_at) <= now() or record.attempts_left <= 0:
            raise invalid
        record.attempts_left -= 1
        if not hmac.compare_digest(record.code_hash, code_digest(key, record.nonce, code)):
            self.db.commit()
            raise invalid
        record.used_at = now()
        if record.user_id:
            contact = user.email.lower() if user and channel == 'email' else user.phone if user else None
            if not user or user.status != 'ACTIVE' or user.token_version != record.token_version or contact != address:
                self.db.commit()
                raise invalid
        else:
            # Never log into an account created/changed since challenge issuance.
            existing = self.repo.get_by_email(address) if channel == 'email' else self.repo.get_by_phone(address)
            if existing:
                self.db.commit(); raise invalid
            user = User(email=address if channel == 'email' else f'mobile-{secrets.token_hex(16)}@accounts.fitigo.invalid',
                        phone=address if channel == 'mobile' else None,
                        password_hash=hash_password(secrets.token_urlsafe(32)), status='ACTIVE')
            try:
                self.repo.create_user(user)
                role = self.repo.get_or_create_role(ROLE_CUSTOMER)
                self.repo.assign_role(user.id, role.id)
            except IntegrityError:
                self.db.rollback(); raise invalid from None
        if channel == 'email': user.is_email_verified = True
        else: user.is_phone_verified = True
        access = create_access_token(str(user.id), {'version': user.token_version or 0})
        refresh, expiry = create_refresh_token(str(user.id), {'version': user.token_version or 0})
        self.repo.store_refresh_token(RefreshToken(user_id=user.id, token_hash=digest(refresh), expires_at=expiry))
        self.db.commit()
        return access, refresh, user

    def send_email_otp(self, *, email, client_ip='unknown'):
        self._send('email', email.strip().lower(), client_ip)

    def verify_email_otp(self, *, email, otp, client_ip='unknown'):
        return self._verify('email', email.strip().lower(), otp, client_ip)

    def send_mobile_otp(self, *, country_code, mobile_number, client_ip='unknown'):
        self._send('mobile', mobile_address(country_code, mobile_number), client_ip)

    def verify_mobile_otp(self, *, country_code, mobile_number, otp, client_ip='unknown'):
        return self._verify('mobile', mobile_address(country_code, mobile_number), otp, client_ip)


def user_to_public_dict(user: User) -> dict:
    return {'id': user.id, 'first_name': user.first_name, 'last_name': user.last_name,
            'email': user.email, 'phone': user.phone, 'status': user.status,
            'is_email_verified': user.is_email_verified, 'is_phone_verified': user.is_phone_verified,
            'created_at': user.created_at.replace(tzinfo=timezone.utc).isoformat()
            if user.created_at else datetime.now(timezone.utc).isoformat()}