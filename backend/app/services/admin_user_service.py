from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.auth import User, UserRole, Role
from app.services.operation_audit import record
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

        if role:
            stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == role)))
        return list(self.db.execute(stmt).scalars().all())

    def get_user(self, *, user_id: int) -> User:
        u = self.repo.get_by_id(user_id)
        if not u:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return u

    def update_status(self, *, user_id: int, new_status: str, reason: str | None = None,
                      actor_id: int | None = None, reason_code: str = 'ADMIN_REQUEST') -> User:
        if new_status not in {'ACTIVE', 'INACTIVE', 'SUSPENDED', 'BANNED'}:
            raise HTTPException(422, 'Unsupported account status')
        u = self.db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
        if not u: raise HTTPException(404, 'User not found')
        old_status = u.status
        u.status = new_status
        if old_status != new_status:
            from app.services.operation_audit import VALUES
            record(self.db, 'USER_STATUS_CHANGED', user_id, actor_id, reason_code=reason_code,
                   to_status=new_status, **({'from_status':old_status} if old_status in VALUES else {}))
        self.db.commit()
        self.db.refresh(u)
        return u
