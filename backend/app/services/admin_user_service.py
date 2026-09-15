from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.repositories.user_repository import UserRepository


class AdminUserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def list_users(
        self,
        *,
        q: str | None = None,
        role: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        stmt = select(User).order_by(User.id.desc()).limit(limit).offset(offset)

        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    User.email.like(like),
                    User.first_name.like(like),
                    User.last_name.like(like),
                    User.phone.like(like),
                )
            )

        if status_filter:
            stmt = stmt.where(User.status == status_filter)

        users = list(self.db.execute(stmt).scalars().all())

        if role:
            # Filter in-memory based on roles mapping (simple + clear; ok for admin lists).
            out: list[User] = []
            for u in users:
                roles = set(self.repo.get_role_names(u.id))
                if role in roles:
                    out.append(u)
            return out

        return users

    def get_user(self, *, user_id: int) -> User:
        u = self.repo.get_by_id(user_id)
        if not u:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return u

    def update_status(self, *, user_id: int, new_status: str, reason: str | None = None) -> User:
        u = self.get_user(user_id=user_id)
        u.status = new_status
        if reason:
            # No dedicated audit table yet; store as a suffix on admin notes if ever added.
            pass
        self.db.commit()
        self.db.refresh(u)
        return u
