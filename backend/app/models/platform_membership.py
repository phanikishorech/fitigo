"""Platform catalog and unpaid order foundations; not access entitlements."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PlatformMembershipPlan(Base):
    __tablename__ = "platform_membership_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(2000))
    duration_value: Mapped[int] = mapped_column(Integer)
    duration_unit: Mapped[str] = mapped_column(String(10))
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    benefits: Mapped[list[str]] = mapped_column(JSON, default=list)
    badge: Mapped[str | None] = mapped_column(String(60))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlatformMembershipOffer(Base):
    __tablename__ = "platform_membership_offers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_membership_plans.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(12))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    title: Mapped[str | None] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlatformMembershipOrder(Base):
    __tablename__ = "platform_membership_orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_membership_plans.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="PAYMENT_DISABLED")
    snapshot: Mapped[dict] = mapped_column(JSON)
    membership_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user_memberships.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlatformMembershipAudit(Base):
    __tablename__ = "platform_membership_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_membership_plans.id"))
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)