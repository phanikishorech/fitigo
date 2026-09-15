from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ReviewStatus(str, enum.Enum):
    PUBLISHED = "PUBLISHED"
    HIDDEN = "HIDDEN"


class GymReview(Base):
    __tablename__ = "gym_reviews"
    __table_args__ = (
        UniqueConstraint("gym_id", "user_id"),
        Index("ix_gym_reviews_gym_id", "gym_id"),
        Index("ix_gym_reviews_user_id", "user_id"),
        Index("ix_gym_reviews_status", "status"),
        Index("ix_gym_reviews_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReviewStatus.PUBLISHED.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
