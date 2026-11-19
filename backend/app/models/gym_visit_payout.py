"""Monthly verified-visit allocations; not FitiGo earnings or actual owner payment."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class GymVisitPayout(Base):
    __tablename__ = 'gym_visit_payouts'
    __table_args__ = (UniqueConstraint('mode','checkin_id',name='uq_visit_payout_checkin'),
        UniqueConstraint('mode','daily_access_id',name='uq_visit_payout_daily_access'),
        CheckConstraint('approved_amount >= 0 AND approved_amount <= configured_amount',name='ck_visit_amount'),
        Index('ix_visit_payout_period','mode','allocation_period','gym_id','membership_id'))
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    source_event_id: Mapped[str] = mapped_column(String(36),ForeignKey('financial_source_outbox.id'),unique=True)
    source_evidence_id: Mapped[str] = mapped_column(String(36),ForeignKey('financial_source_evidence.id'))
    checkout_id: Mapped[str] = mapped_column(String(36),ForeignKey('payment_checkouts.id'))
    membership_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('user_memberships.id'))
    customer_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('users.id'))
    gym_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('gyms.id'))
    owner_user_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('users.id'))
    owner_evidence_id: Mapped[str] = mapped_column(String(36),ForeignKey('gym_owner_evidence.id'))
    checkin_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('checkins.id'))
    daily_access_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('customer_daily_accesses.id'))
    agreement_pin_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('financial_agreement_pins.id'))
    agreement_version_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('financial_agreement_versions.id'))
    service_date: Mapped[date] = mapped_column(Date)
    allocation_period: Mapped[date] = mapped_column(Date)
    configured_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    applied_cap: Mapped[Decimal | None] = mapped_column(Numeric(12,2), nullable=True)
    mode: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(40))
    fee_status: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(64),unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


@event.listens_for(GymVisitPayout,'before_update')
@event.listens_for(GymVisitPayout,'before_delete')
def immutable_visit(mapper,connection,target):
    raise ValueError('Verified visit allocations are immutable.')


class GymMonthlyCalculation(Base):
    """Append-only monthly completion and source-backed correction revisions."""
    __tablename__ = 'gym_monthly_calculations'
    __table_args__ = (UniqueConstraint('mode','gym_id','period','revision',name='uq_monthly_gym_revision'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10))
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('gyms.id'))
    period: Mapped[date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(BigInteger)
    source_evidence_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('financial_source_evidence.id'), nullable=True, unique=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class MembershipVisitFee(Base):
    """Exactly one actual provider fee budget for a completed membership purchase."""
    __tablename__ = 'membership_visit_fees'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey('payment_checkouts.id'), unique=True)
    fee_evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey('financial_source_evidence.id'))
    mode: Mapped[str] = mapped_column(String(10))
    actual_fee: Mapped[Decimal] = mapped_column(Numeric(12,2))
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


for model in (GymMonthlyCalculation, MembershipVisitFee):
    event.listen(model, 'before_update', immutable_visit)
    event.listen(model, 'before_delete', immutable_visit)