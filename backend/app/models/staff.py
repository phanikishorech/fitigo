from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class GymStaffAssignment(Base):
    __tablename__ = "gym_staff_assignments"
    __table_args__ = (
        UniqueConstraint("gym_id", "user_id"),
        Index("ix_gym_staff_assignments_gym_id", "gym_id"),
        Index("ix_gym_staff_assignments_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    # STAFF / MANAGER (future)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="STAFF")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
