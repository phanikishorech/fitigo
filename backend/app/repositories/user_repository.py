from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import RefreshToken, Role, User, UserRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalars().first()

    def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return self.db.execute(stmt).scalars().first()

    def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        return self.db.execute(stmt).scalars().first()

    def create_user(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def get_or_create_role(self, name: str, description: str | None = None) -> Role:
        stmt = select(Role).where(Role.name == name)
        role = self.db.execute(stmt).scalars().first()
        if role:
            return role
        role = Role(name=name, description=description)
        self.db.add(role)
        self.db.flush()
        return role

    def assign_role(self, user_id: int, role_id: int) -> UserRole:
        mapping = UserRole(user_id=user_id, role_id=role_id)
        self.db.add(mapping)
        self.db.flush()
        return mapping

    def get_role_names(self, user_id: int) -> list[str]:
        stmt = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def store_refresh_token(self, refresh_token: RefreshToken) -> RefreshToken:
        self.db.add(refresh_token)
        self.db.flush()
        return refresh_token

    def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.db.execute(stmt).scalars().first()
