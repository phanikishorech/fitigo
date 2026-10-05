"""Account recovery and password changes using the existing user/session store."""
import hashlib
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.auth import AuthRateLimit, PasswordResetToken, RefreshToken, User

logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def as_utc(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def email_ready():
    url = urlsplit(settings.password_reset_frontend_url)
    secure_url = url.scheme == 'https' or (
        settings.environment == 'development' and url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1'}
    )
    return bool(settings.smtp_host and settings.smtp_from and settings.smtp_security in {'starttls', 'ssl'}
                and secure_url and url.netloc and not url.fragment and not url.query and not url.username)


def send_reset_email(address: str, token: str):
    message = EmailMessage()
    message['Subject'] = 'Reset your FitiGo password'
    message['From'] = settings.smtp_from
    message['To'] = address
    # Fragment avoids including the secret in HTTP requests, access logs or referrers.
    link = f'{settings.password_reset_frontend_url}#token={token}'
    message.set_content(f'Use this link to reset your FitiGo password:\n\n{link}\n\n'
                        'This link expires in 30 minutes and can be used once. '
                        'If you did not request this, ignore this email. Your password has not changed.')
    context = ssl.create_default_context()
    cls = smtplib.SMTP_SSL if settings.smtp_security == 'ssl' else smtplib.SMTP
    kwargs = {'context': context} if settings.smtp_security == 'ssl' else {}
    with cls(settings.smtp_host, settings.smtp_port, timeout=10, **kwargs) as smtp:
        if settings.smtp_security == 'starttls':
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or '')
        smtp.send_message(message)


class PasswordService:
    def __init__(self, db: Session):
        self.db = db

    def throttle(self, key: str, limit: int, seconds: int):
        """Persistent per-key rate limit. No password/email/token is stored in the key."""
        key_hash = digest(key)
        stamp = now()
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
            raise HTTPException(503, 'Password reset email is not configured.')
        self.throttle(f'reset-email:{email}', 3, 900)

    def deliver_reset(self, email: str):
        # Executed after the generic HTTP response for both known and unknown
        # addresses. SMTP response times must not reveal account existence.
        user = self.db.scalars(select(User).where(User.email == email).with_for_update()).first()
        token = secrets.token_urlsafe(32)
        if user is None or user.status != 'ACTIVE':
            self.db.rollback()
            return
        record = PasswordResetToken(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(minutes=30))
        self.db.add(record)
        try:
            self.db.flush()
            send_reset_email(user.email, token)
            self.db.commit()
        except Exception:
            # Do not leak SMTP diagnostics or account existence. No valid token remains.
            self.db.rollback()
            logger.warning('Password reset delivery failed; verify SMTP configuration and service health.')

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
        self.db.commit()


def deliver_password_reset(bind, email: str):
    # Own a session rather than retaining a request-scoped session in a background task.
    try:
        with Session(bind) as db:
            PasswordService(db).deliver_reset(email)
    except Exception:
        logger.warning('Password reset delivery failed; verify SMTP configuration and service health.')