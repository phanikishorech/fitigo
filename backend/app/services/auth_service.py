from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.roles import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_GYM_OWNER,
    ROLE_GYM_STAFF,
    ROLE_SUPER_ADMIN,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth import RefreshToken, User
from app.repositories.user_repository import UserRepository


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def register_user(self, *, first_name: str, last_name: str, email: str, phone: str | None, password: str, role_name: str):
        existing = self.repo.get_by_email(email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            password_hash=hash_password(password),
            status="ACTIVE",
            is_email_verified=False,
            is_phone_verified=False,
        )

        role = self.repo.get_or_create_role(role_name)

        try:
            self.repo.create_user(user)
            self.repo.assign_role(user.id, role.id)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

        return user

    def login(self, *, email: str, password: str):
        user = self.repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if user.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")

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

        return access_token, refresh_token

    def refresh(self, *, refresh_token: str):
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
            sub = payload.get("sub")
            if not sub:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

        token_hash = _sha256_hex(refresh_token)
        stored = self.repo.get_refresh_token_by_hash(token_hash)
        if not stored:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
        if stored.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        # rotate
        stored.revoked_at = datetime.now(timezone.utc)

        access_token = create_access_token(str(sub))
        new_refresh_token, new_exp = create_refresh_token(str(sub))

        rt = RefreshToken(
            user_id=int(sub),
            token_hash=_sha256_hex(new_refresh_token),
            expires_at=new_exp,
            revoked_at=None,
        )
        self.repo.store_refresh_token(rt)
        self.db.commit()

        return access_token, new_refresh_token

    def logout(self, *, refresh_token: str):
        token_hash = _sha256_hex(refresh_token)
        stored = self.repo.get_refresh_token_by_hash(token_hash)
        if not stored:
            return
        if stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            self.db.commit()
