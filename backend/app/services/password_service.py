"""Account recovery and password changes using the existing user/session store."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.auth import AuthRateLimit, PasswordResetToken, RefreshToken, User
from app.services import account_delivery
from app.services.operation_audit import record as record_audit
from app.services.notification_workflow import publish

def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def as_utc(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def email_ready():
    try:
        account_delivery.frontend_link('/auth/reset-password')
        return account_delivery.email_ready()
    except HTTPException:
        return False


def send_reset_email(address: str, token: str):
    # Fragment avoids including the secret in HTTP requests, access logs or referrers.
    link = f"{account_delivery.frontend_link('/auth/reset-password')}#token={token}"
    account_delivery.send_email(address, 'Reset your FitiGo password',
        f'If you have an active FitiGo account, use this link to reset your password:\n\n{link}\n\n'
        f'This link expires in {settings.password_reset_expiry_minutes} minutes and can be used once. '
        'If you did not request this, ignore this email. Your password has not changed.')


class PasswordService:
    def __init__(self, db: Session):
        self.db = db

    def throttle(self, key: str, limit: int, seconds: int):
        """Persistent per-key rate limit. No password/email/token is stored in the key."""
        key_hash = digest(key)
        stamp = now()
        if self.db.get_bind().dialect.name == 'mysql':
            # Insert/lock atomically. SELECT FOR UPDATE on an absent key can
            # deadlock concurrent first requests under InnoDB gap locking.
            from sqlalchemy.dialects.mysql import insert
            statement = insert(AuthRateLimit).values(key=key_hash, attempts=0, window_start=stamp)
            self.db.execute(statement.on_duplicate_key_update(key=statement.inserted.key))
        row = self.db.scalars(select(AuthRateLimit).where(AuthRateLimit.key == key_hash).with_for_update()).first()
        if row is None:
            try:
                with self.db.begin_nested():
                    self.db.add(AuthRateLimit(key=key_hash, attempts=0, window_start=stamp))
                    self.db.flush()
            except IntegrityError:
                pass
            row = self.db.scalars(select(AuthRateLimit).where(AuthRateLimit.key == key_hash).with_for_update()).one()
        if as_utc(row.window_start) + timedelta(seconds=seconds) <= stamp:
            row.attempts = 0
            row.window_start = stamp
        if row.attempts >= limit:
            self.db.rollback()
            raise HTTPException(429, 'Too many attempts. Please try again later.')
        row.attempts += 1
        self.db.commit()

    def request_reset(self, email: str, address: str):
        self.throttle(f'reset-ip:{address}', 20, 900)
        if not email_ready():
            raise account_delivery.unavailable()
        self.throttle(f'reset-email:{email}', 3, 900)

    def deliver_reset(self, email: str):
        # Same provider operation/template whether an account exists or not.
        # Only active accounts receive a usable persisted credential.
        user = self.db.scalars(select(User).where(User.email == email).with_for_update()).first()
        token = secrets.token_urlsafe(32)
        try:
            if user is not None and user.status == 'ACTIVE':
                self.db.add(PasswordResetToken(token_hash=digest(token), user_id=user.id,
                    expires_at=now() + timedelta(minutes=settings.password_reset_expiry_minutes)))
            self.db.flush()
            send_reset_email(email, token)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise account_delivery.unavailable(True) from None

    def _replace_password(self, user: User, password: str):
        stamp = now()
        user.password_hash = hash_password(password)
        user.token_version += 1
        self.db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=stamp))
        self.db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=stamp))

    def reset(self, token: str, password: str, address: str):
        self.throttle(f'reset-verify:{address}', 20, 900)
        token_hash = digest(token)
        record = self.db.get(PasswordResetToken, token_hash)
        invalid = HTTPException(400, 'This reset link is invalid or expired. Request a new link.')
        if record is None:
            raise invalid
        # Lock user first, matching password changes and refresh. Then re-read token
        # under the lock so concurrent requests cannot reuse a single recovery link.
        user = self.db.scalars(select(User).where(User.id == record.user_id).with_for_update().execution_options(populate_existing=True)).first()
        record = self.db.scalars(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash).with_for_update().execution_options(populate_existing=True)).one()
        if user is None or user.status != 'ACTIVE' or record.used_at or as_utc(record.expires_at) <= now():
            raise invalid
        if verify_password(password, user.password_hash):
            raise HTTPException(400, 'Choose a password different from your current password.')
        self._replace_password(user, password)
        record_audit(self.db, 'PASSWORD_RESET', user.id, user.id, reason_code='SECURITY')
        publish(self.db, user.id, 'PASSWORD_RESET', user.id)
        self.db.commit()
    def change(self, user_id: int, current: str, password: str, expected_version: int):
        self.throttle(f'change-password:{user_id}', 5, 900)
        user = self.db.scalars(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)).first()
        if not user or user.status != 'ACTIVE' or user.token_version != expected_version:
            raise HTTPException(401, 'Session expired. Sign in again.')
        if not verify_password(current, user.password_hash):
            raise HTTPException(400, 'Your current password is incorrect.')
        if verify_password(password, user.password_hash):
            raise HTTPException(400, 'Choose a password different from your current password.')
        self._replace_password(user, password)
        record_audit(self.db, 'PASSWORD_CHANGED', user.id, user.id, reason_code='SECURITY')
        publish(self.db, user.id, 'PASSWORD_CHANGED', user.id)
        self.db.commit()