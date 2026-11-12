"""Separate inbox/read state and durable email intent, not legacy SENT labels."""
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), primary_key=True)
    operational_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('notification_events.id'), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[int] = mapped_column(BigInteger)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    email_status: Mapped[str] = mapped_column(String(24), index=True)
    recipient_hash: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    claim_id: Mapped[str | None] = mapped_column(String(32))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)