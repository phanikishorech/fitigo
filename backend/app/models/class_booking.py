from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ClassSessionStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    FEW_SLOTS_LEFT = "FEW_SLOTS_LEFT"
    FULL = "FULL"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class GymClass(Base):
    __tablename__ = "gym_classes"
    __table_args__ = (
        Index("ix_gym_classes_gym_id", "gym_id"),
        Index("ix_gym_classes_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    class_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions: Mapped[list["ClassSession"]] = relationship(
        "ClassSession", back_populates="gym_class", cascade="all, delete-orphan"
    )


class ClassSession(Base):
    __tablename__ = "class_sessions"
    __table_args__ = (
        Index("ix_class_sessions_gym_class_id", "gym_class_id"),
        Index("ix_class_sessions_session_date", "session_date"),
        Index("ix_class_sessions_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_class_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gym_classes.id"), nullable=False)

    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Stored as SQL TIME.
    start_time: Mapped[time] = mapped_column(sa.Time(), nullable=False)  # type: ignore[name-defined]
    end_time: Mapped[time] = mapped_column(sa.Time(), nullable=False)  # type: ignore[name-defined]

    maximum_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    booked_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_per_person: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ClassSessionStatus.AVAILABLE.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    gym_class: Mapped[GymClass] = relationship("GymClass", back_populates="sessions")


class GymSpecialHours(Base):
    """Optional per-date override for operating hours."""

    __tablename__ = "gym_special_hours"
    __table_args__ = (
        Index("ix_gym_special_hours_gym_id", "gym_id"),
        Index("ix_gym_special_hours_date", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    date: Mapped[date] = mapped_column(Date, nullable=False)
    open_time: Mapped[time | None] = mapped_column(sa.Time(), nullable=True)  # type: ignore[name-defined]
    close_time: Mapped[time | None] = mapped_column(sa.Time(), nullable=True)  # type: ignore[name-defined]
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
