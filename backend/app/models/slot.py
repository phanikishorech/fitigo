from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SlotAvailabilityStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    FULL = "FULL"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class GymSlot(Base):
    __tablename__ = "gym_slots"
    __table_args__ = (
        Index("ix_gym_slots_gym_id", "gym_id"),
        Index("ix_gym_slots_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # stored as 0/1 in DB (TINYINT/INT); API converts to bool
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    availability: Mapped[list["SlotAvailability"]] = relationship(
        "SlotAvailability", back_populates="slot", cascade="all, delete-orphan"
    )


class SlotAvailability(Base):
    __tablename__ = "slot_availability"
    __table_args__ = (
        UniqueConstraint("gym_slot_id", "slot_date"),
        Index("ix_slot_availability_gym_slot_id", "gym_slot_id"),
        Index("ix_slot_availability_slot_date", "slot_date"),
        Index("ix_slot_availability_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_slot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gym_slots.id"), nullable=False)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)

    capacity_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    booked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SlotAvailabilityStatus.AVAILABLE.value)

    slot: Mapped[GymSlot] = relationship("GymSlot", back_populates="availability")
