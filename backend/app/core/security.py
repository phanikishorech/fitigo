from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# bcrypt has a 72-byte input limit.
# Use bcrypt_sha256 to safely support long passwords without silent truncation.
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, additional_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode: dict[str, Any] = {"sub": subject, "type": "access", "exp": expire}
    if additional_claims:
        to_encode.update(additional_claims)
    return jwt.encode(to_encode, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, additional_claims: dict[str, Any] | None = None) -> tuple[str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode: dict[str, Any] = {"sub": subject, "type": "refresh", "exp": expire, "jti": uuid4().hex}
    if additional_claims:
        to_encode.update(additional_claims)
    token = jwt.encode(to_encode, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expire


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm],
                             options={"require_exp": True, "require_sub": True})
        subject = payload.get("sub")
        # IDs map to signed BIGINT primary keys. Validate before any DB conversion.
        if (not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal()
                or len(subject) > 19 or not 0 < int(subject) <= 9223372036854775807):
            raise JWTError("Invalid token claims")
        if payload.get("type") not in {"access", "refresh"} or type(payload.get("exp")) is not int:
            raise JWTError("Invalid token claims")
        # Preserve pre-version sessions for accounts still at version zero.
        version = payload.get("version", 0)
        if type(version) is not int or version < 0:
            raise JWTError("Invalid token claims")
        return payload
    except (JWTError, TypeError, ValueError, OverflowError):
        raise JWTError("Invalid or expired token") from None
