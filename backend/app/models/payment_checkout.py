"""Gateway orchestration, not a second payment ledger. Booking payments stay in payments."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class PaymentCheckout(Base):
    __tablename__ = "payment_checkouts"
    __table_args__ = (UniqueConstraint("user_id", "source_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default="RAZORPAY", server_default="RAZORPAY")
    checkout_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str] = mapped_column(String(10))
    key_id: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    gateway_order_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentWebhookReceipt(Base):
    __tablename__ = "payment_webhook_receipts"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    body_hash: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (UniqueConstraint("checkout_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey("payment_checkouts.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)