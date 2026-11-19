"""Permanent policy evidence, not duplicate entitlement or payment ledgers."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class BookingCancellation(Base):
    __tablename__ = 'booking_cancellations'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('bookings.id'), unique=True)
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('payments.id'), nullable=True)
    wallet_transaction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('wallet_transactions.id'), nullable=True, unique=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10))
    scheduled_start: Mapped[datetime] = mapped_column(DateTime)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class MembershipTransfer(Base):
    __tablename__ = 'membership_transfers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    membership_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('user_memberships.id'), unique=True)
    original_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    recipient_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='COMPLETED')
    consumed_access_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    original_end_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)