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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CartItemStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    CONFIRMED = "CONFIRMED"


class BookingType(str, enum.Enum):
    GYM = "GYM"
    CLASS = "CLASS"


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        Index("ix_cart_items_user_id", "user_id"),
        Index("ix_cart_items_status", "status"),
        Index("ix_cart_items_gym_id", "gym_id"),
        Index("ix_cart_items_booking_date", "booking_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    booking_type: Mapped[str] = mapped_column(String(10), nullable=False)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    class_session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("class_sessions.id"), nullable=True)

    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    preferred_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    preferred_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    price_per_person: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CartItemStatus.ACTIVE.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
