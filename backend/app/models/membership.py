from __future__ import annotations

import enum
from datetime import datetime

from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MembershipStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class GymMembershipPlan(Base):
    __tablename__ = "gym_membership_plans"
    __table_args__ = (
        Index("ix_gym_membership_plans_gym_id", "gym_id"),
        Index("ix_gym_membership_plans_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserMembership(Base):
    __tablename__ = "user_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "checkout_key"),
        Index("ix_user_memberships_user_id", "user_id"),
        Index("ix_user_memberships_gym_id", "gym_id"),
        Index("ix_user_memberships_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    gym_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gym_membership_plans.id"), nullable=True)
    membership_type: Mapped[str] = mapped_column(String(20), nullable=False, default="SINGLE_GYM")
    platform_plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("platform_membership_plans.id"), nullable=True)
    checkout_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wallet_transaction_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("wallet_transactions.id"), nullable=True, unique=True)
    terms_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=MembershipStatus.ACTIVE.value)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    payment_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="DUMMY")
    payment_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PAID")
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MembershipDailyAccess(Base):
    """Daily access mark for a membership holder at a specific gym.

    This is created when the QR is scanned at the gym and used by the Profile
    calendar UI to show which dates have already been accessed.
    """

    __tablename__ = "membership_daily_accesses"
    __table_args__ = (
        UniqueConstraint("user_id", "gym_id", "access_date"),
        Index("ix_membership_daily_accesses_user_id", "user_id"),
        Index("ix_membership_daily_accesses_gym_id", "gym_id"),
        Index("ix_membership_daily_accesses_access_date", "access_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)
    access_date: Mapped[date] = mapped_column(Date, nullable=False)

    # SCANNED (future: REVOKED, etc.)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCANNED")
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
