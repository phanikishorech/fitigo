"""Source observations and durable handoff, never an accounting ledger."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, BigInteger, Integer, DateTime, Numeric, JSON, ForeignKey, UniqueConstraint, Index, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class SourceEvidence(Base):
    __tablename__ = 'financial_source_evidence'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(100))
    checkout_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('payment_checkouts.id'))
    # Unknown legacy environments stay quarantined; never enter the outbox.
    mode: Mapped[str | None] = mapped_column(String(10))
    evidence_status: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))


class SourceOutbox(Base):
    __tablename__ = 'financial_source_outbox'
    __table_args__ = (Index('ix_source_outbox_claim', 'mode', 'status', 'available_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey('financial_source_evidence.id'), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(10))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default='PENDING')
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    available_at: Mapped[datetime] = mapped_column(DateTime)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    binding_status: Mapped[str] = mapped_column(String(40), default='AWAITING_POLICY_RESOLUTION')
    agreement_pin_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('financial_agreement_pins.id'))


class GymOwnerEvidence(Base):
    """Observed owner at a NEW source event, not retroactive ownership intervals."""
    __tablename__ = 'gym_owner_evidence'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey('financial_source_evidence.id'), unique=True)
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('gyms.id'), index=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    basis: Mapped[str] = mapped_column(String(40))


def immutable(mapper, connection, target):
    raise ValueError('Source evidence is immutable; corrections require new evidence.')


for model in (SourceEvidence, GymOwnerEvidence):
    event.listen(model, 'before_update', immutable)
    event.listen(model, 'before_delete', immutable)


@event.listens_for(SourceOutbox, 'before_delete')
def no_delete(mapper, connection, target):
    immutable(mapper, connection, target)


@event.listens_for(SourceOutbox, 'before_update')
def immutable_event(mapper, connection, target):
    mutable = {'status', 'retry_count', 'last_error', 'available_at', 'lease_until', 'lease_token'}
    if any(a.history.has_changes() and a.key not in mutable for a in inspect(target).attrs):
        raise ValueError('Source event identity, environment and binding are immutable in Phase 3.')