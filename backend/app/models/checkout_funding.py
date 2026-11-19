"""Funding metadata/holds on existing checkouts; WalletAccount remains the balance."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class CheckoutFunding(Base):
    __tablename__ = 'checkout_funding'
    __table_args__ = (CheckConstraint('total_amount = wallet_amount + gateway_amount', name='ck_funding_sum'),
        CheckConstraint('wallet_amount >= 0 AND gateway_amount >= 0', name='ck_funding_nonnegative'),
        Index('ix_funding_holds', 'user_id', 'state'), Index('ix_funding_expiry', 'state', 'expires_at'))
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey('payment_checkouts.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    wallet_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gateway_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    mode: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20))  # HELD, DEBITED, RELEASED, NONE
    request_wallet: Mapped[str] = mapped_column(String(40))
    wallet_transaction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('wallet_transactions.id'), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BookingFunding(Base):
    __tablename__ = 'booking_funding'
    __table_args__ = (CheckConstraint('total_amount = wallet_amount + gateway_amount', name='ck_booking_funding_sum'),
        CheckConstraint('wallet_amount >= 0 AND gateway_amount >= 0', name='ck_booking_funding_nonnegative'))
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('bookings.id'), primary_key=True)
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey('checkout_funding.checkout_id'), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    wallet_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gateway_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))