from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AccessType(str, enum.Enum):
    SINGLE_GYM = "SINGLE_GYM"
    MULTI_GYM = "MULTI_GYM"


class DailyAccessStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    USED = "USED"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class QrTokenStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class CheckinStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"


class CustomerDailyAccess(Base):
    """A single user's gym access entitlement for a specific date.

    IMPORTANT: This is distinct from QR tokens.
    - Daily access is one-time use per date.
    - Multiple short-lived QR tokens can be generated for the same daily access.

    MVP mapping to current product:
    - SINGLE_GYM: user has exactly one active gym membership on that date.
    - MULTI_GYM: user has >1 active gym memberships on that date.
    """

    __tablename__ = "customer_daily_accesses"
    __table_args__ = (
        # A single computed key handles SINGLE vs MULTI uniqueness without NULL-unique pitfalls.
        UniqueConstraint("access_key"),
        Index("ix_customer_daily_accesses_user_id", "user_id"),
        Index("ix_customer_daily_accesses_access_date", "access_date"),
        Index("ix_customer_daily_accesses_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    membership_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_memberships.id"), nullable=False)
    access_type: Mapped[str] = mapped_column(String(20), nullable=False)
    gym_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=True)
    access_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Uniqueness / audit
    access_key: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DailyAccessStatus.AVAILABLE.value)

    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_gym_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=True)
    # We intentionally avoid FK here to prevent circular FK issues with MySQL.
    checkin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccessQrToken(Base):
    __tablename__ = "access_qr_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        Index("ix_access_qr_tokens_daily_access_id", "daily_access_id"),
        Index("ix_access_qr_tokens_status", "status"),
        Index("ix_access_qr_tokens_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    daily_access_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customer_daily_accesses.id"), nullable=False)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=QrTokenStatus.ACTIVE.value)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_gym_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=True)
    checkin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        Index("ix_checkins_user_id", "user_id"),
        Index("ix_checkins_daily_access_id", "daily_access_id"),
        Index("ix_checkins_gym_id", "gym_id"),
        Index("ix_checkins_checkin_time", "checkin_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    daily_access_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customer_daily_accesses.id"), nullable=False)
    qr_token_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("access_qr_tokens.id"), nullable=False)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("gyms.id"), nullable=False)

    checkin_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CheckinStatus.SUCCESS.value)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class AccessPauseDay(Base):
    """Represents a user-paused access day.

    This is used by the calendar and by QR generation/validation to block access.
    """

    __tablename__ = "access_pause_days"
    __table_args__ = (
        UniqueConstraint("user_id", "access_date"),
        Index("ix_access_pause_days_user_id", "user_id"),
        Index("ix_access_pause_days_access_date", "access_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    access_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
