"""Versioned administrative policy configuration, not a commission ledger."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class FinancialAgreementScope(Base):
    __tablename__ = 'financial_agreement_scopes'
    __table_args__ = (UniqueConstraint('mode', 'scope_key', name='uq_financial_agreement_scope'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(10))
    scope_key: Mapped[str] = mapped_column(String(40))
    gym_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('gyms.id'))
    template: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FinancialAgreementVersion(Base):
    __tablename__ = 'financial_agreement_versions'
    __table_args__ = (
        UniqueConstraint('scope_id', 'version', name='uq_financial_agreement_version'),
        UniqueConstraint('scope_id', 'request_key', name='uq_financial_agreement_request'),
        UniqueConstraint('scope_id', 'effective_from', name='uq_financial_agreement_start'),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('financial_agreement_scopes.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(DateTime)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms: Mapped[dict] = mapped_column(JSON)
    action: Mapped[str] = mapped_column(String(20))  # AGREEMENT or INHERIT
    agreement_reference: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(500))
    ca_status: Mapped[str] = mapped_column(String(20))
    ca_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


@event.listens_for(FinancialAgreementVersion, 'before_update')
@event.listens_for(FinancialAgreementVersion, 'before_delete')
def immutable_agreement(mapper, connection, target):
    raise ValueError('Agreement versions are immutable. Schedule a new version instead.')


class FinancialAgreementPin(Base):
    """Policy/source binding only; not a monetary event, journal or allocation."""
    __tablename__ = 'financial_agreement_pins'
    __table_args__ = (UniqueConstraint('checkout_id', 'context', 'source_key', name='uq_agreement_pin_source'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey('payment_checkouts.id'))
    context: Mapped[str] = mapped_column(String(40))
    source_key: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(10))
    agreement_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('financial_agreement_versions.id'))
    selection_policy_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('financial_agreement_versions.id'))
    selected_at: Mapped[datetime] = mapped_column(DateTime)
    evidence: Mapped[dict] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


@event.listens_for(FinancialAgreementPin, 'before_update')
@event.listens_for(FinancialAgreementPin, 'before_delete')
def immutable_pin(mapper, connection, target):
    raise ValueError('Agreement pins are immutable; do not re-resolve completed source events.')