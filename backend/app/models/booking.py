from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BookingStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PaymentStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        Index("ix_bookings_user_id", "user_id"),
        Index("ix_bookings_gym_id", "gym_id"),
        Index("ix_bookings_gym_slot_id", "gym_slot_id"),
        Index("ix_bookings_slot_date", "slot_date"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_expires_at", "expires_at"),
        Index("ix_bookings_idempotency_key", "idempotency_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    gym_slot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gym_slots.id"), nullable=False)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")

    status: Mapped[str] = mapped_column(String(30), nullable=False, default=BookingStatus.PENDING_PAYMENT.value)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Payment deadline for pending-payment reservations
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optional request-level idempotency. Uniqueness scoped per-user.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Gym attendance tracking (set by gym owner)
    attendance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attendance_marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attendance_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="booking", uselist=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("booking_id"),
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=False)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="DUMMY")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=PaymentStatus.INITIATED.value)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    booking: Mapped[Booking] = relationship("Booking", back_populates="payment")
