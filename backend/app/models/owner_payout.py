"""Manual evidenced payout workflow; no bank transfer integration."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class OwnerPayout(Base):
    __tablename__='owner_payouts'
    __table_args__=(UniqueConstraint('mode','request_key',name='uq_owner_payout_request'),
        UniqueConstraint('mode','payment_reference',name='uq_owner_payout_payment'),
        CheckConstraint('entitlement_amount > 0 AND deduction_amount >= 0 AND amount > 0 AND amount + deduction_amount = entitlement_amount',name='ck_owner_payout_amount'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    mode: Mapped[str] = mapped_column(String(10))
    gym_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('gyms.id'))
    owner_user_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('users.id'))
    category: Mapped[str] = mapped_column(String(30))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    entitlement_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    deduction_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[int] = mapped_column(BigInteger,ForeignKey('users.id'))
    approved_by: Mapped[int | None] = mapped_column(BigInteger,ForeignKey('users.id'))
    payment_reference: Mapped[str | None] = mapped_column(String(100))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    payment_evidence: Mapped[dict | None] = mapped_column(JSON)
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    deductions: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class OwnerPayoutItem(Base):
    __tablename__='owner_payout_items'
    __table_args__=(UniqueConstraint('payout_id','allocation_id',name='uq_payout_allocation_item'),
        UniqueConstraint('payout_id','visit_payout_id',name='uq_payout_visit_item'),
        CheckConstraint('(allocation_id IS NULL) <> (visit_payout_id IS NULL)',name='ck_payout_item_source'),
        CheckConstraint('amount > 0',name='ck_payout_item_positive'))
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    payout_id: Mapped[str] = mapped_column(String(36),ForeignKey('owner_payouts.id'))
    allocation_id: Mapped[str | None] = mapped_column(String(36),ForeignKey('marketplace_allocations.id'))
    visit_payout_id: Mapped[str | None] = mapped_column(String(36),ForeignKey('gym_visit_payouts.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))


class OwnerPayoutAudit(Base):
    __tablename__='owner_payout_audit'
    __table_args__=(UniqueConstraint('payout_id','request_key',name='uq_payout_audit_request'),
        UniqueConstraint('mode','actual_reference',name='uq_payout_audit_actual_reference'))
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    payout_id: Mapped[str] = mapped_column(String(36),ForeignKey('owner_payouts.id'))
    actor_id: Mapped[int] = mapped_column(BigInteger,ForeignKey('users.id'))
    mode: Mapped[str] = mapped_column(String(10))
    actual_reference: Mapped[str | None] = mapped_column(String(100))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(500))
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)


def immutable(mapper,connection,target):raise ValueError('Payout items/audit are immutable.')
for model in (OwnerPayoutItem,OwnerPayoutAudit):
    event.listen(model,'before_update',immutable);event.listen(model,'before_delete',immutable)
event.listen(OwnerPayout,'before_delete',immutable)


@event.listens_for(OwnerPayout,'before_update')
def protect_payout(mapper,connection,target):
    mutable={'status','version','approved_by','payment_reference','paid_at','payment_evidence'}
    if any(a.history.has_changes() and a.key not in mutable for a in inspect(target).attrs):
        raise ValueError('Payout principal and reservation identity are immutable.')