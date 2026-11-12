"""Operational evidence and durable file deletion intents; no customer secrets."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class OperationAudit(Base):
    __tablename__ = 'operation_audits'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Deliberately no cascading FK: evidence survives resource/account deletion.
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50), index=True)
    resource_type: Mapped[str] = mapped_column(String(30))
    resource_id: Mapped[int] = mapped_column(BigInteger)
    reason_code: Mapped[str] = mapped_column(String(40))
    context: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PhotoDeletion(Base):
    __tablename__ = 'photo_deletions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, index=True)
    actor_id: Mapped[int] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(500))
    storage_root: Mapped[str] = mapped_column(String(500))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='PENDING', index=True)
    error_code: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


@event.listens_for(OperationAudit, 'before_update')
@event.listens_for(OperationAudit, 'before_delete')
def reject_audit_mutation(mapper, connection, target):
    raise ValueError('Operational audit records are append-only through the application.')