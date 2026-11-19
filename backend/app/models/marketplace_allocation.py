"""Append-only commercial allocations. Not a double-entry/statutory ledger."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class MarketplaceAllocation(Base):
    __tablename__ = 'marketplace_allocations'
    __table_args__ = (
        UniqueConstraint('source_event_id', 'allocation_key', name='uq_marketplace_source_allocation'),
        UniqueConstraint('reversal_of_id', name='uq_marketplace_full_reversal'),
        CheckConstraint("mode IN ('test','live') AND currency = 'INR'", name='ck_marketplace_mode_currency'),
        CheckConstraint("entry_kind IN ('ORIGINAL','REVERSAL','FEE_ADJUSTMENT','REPLACEMENT')", name='ck_marketplace_entry_kind'),
        CheckConstraint("posting_status = 'POSTED'", name='ck_marketplace_posted_only'),
        CheckConstraint('gym_gross_share + fitigo_gross_commission = eligible_amount', name='ck_marketplace_gross_balance'),
        CheckConstraint('wallet_amount + gateway_amount = customer_funded_amount', name='ck_marketplace_funding_balance'),
        CheckConstraint('(gateway_fee IS NULL AND gym_gateway_fee_share IS NULL AND fitigo_gateway_fee_share IS NULL AND gym_owner_net_entitlement IS NULL AND fitigo_net_commission IS NULL) OR '
            '(gateway_fee IS NOT NULL AND gym_gateway_fee_share IS NOT NULL AND fitigo_gateway_fee_share IS NOT NULL AND gym_owner_net_entitlement IS NOT NULL AND fitigo_net_commission IS NOT NULL AND '
            'gym_gateway_fee_share + fitigo_gateway_fee_share = gateway_fee AND '
            'gym_owner_net_entitlement = gym_gross_share - gym_gateway_fee_share AND '
            'fitigo_net_commission = fitigo_gross_commission - fitigo_gateway_fee_share)', name='ck_marketplace_net_balance'),
        CheckConstraint("(entry_kind = 'REVERSAL' AND reversal_of_id IS NOT NULL AND adjustment_of_id IS NULL) OR "
            "(entry_kind IN ('FEE_ADJUSTMENT','REPLACEMENT') AND reversal_of_id IS NULL AND adjustment_of_id IS NOT NULL) OR "
            "(entry_kind = 'ORIGINAL' AND reversal_of_id IS NULL AND adjustment_of_id IS NULL)", name='ck_marketplace_correction_reference'),
        Index('ix_marketplace_owner_period', 'mode', 'owner_user_id', 'occurred_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_event_id: Mapped[str] = mapped_column(String(36), ForeignKey('financial_source_outbox.id'))
    source_evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey('financial_source_evidence.id'))
    source_type: Mapped[str] = mapped_column(String(50))
    source_record_id: Mapped[str] = mapped_column(String(100))
    allocation_key: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    # Original business unit is unique even if inconsistent duplicate outbox
    # records are imported. Reversals/adjustments do not consume a new original.
    original_unit_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    checkout_id: Mapped[str] = mapped_column(String(36), ForeignKey('payment_checkouts.id'))
    transaction_reference: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(30))
    gym_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('gyms.id'))
    owner_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    owner_evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey('gym_owner_evidence.id'))
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'))
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('bookings.id'))
    membership_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('user_memberships.id'))
    visitor_index: Mapped[int | None] = mapped_column(Integer)
    agreement_pin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('financial_agreement_pins.id'))
    agreement_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('financial_agreement_versions.id'))
    agreement_version: Mapped[int] = mapped_column(Integer)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    eligible_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    customer_funded_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    wallet_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gateway_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gateway_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    gym_gateway_fee_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fitigo_gateway_fee_share: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    gym_gross_share: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fitigo_gross_commission: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gym_owner_net_entitlement: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fitigo_net_commission: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    fee_status: Mapped[str] = mapped_column(String(40))
    calculation_status: Mapped[str] = mapped_column(String(40))
    posting_status: Mapped[str] = mapped_column(String(20))
    entry_kind: Mapped[str] = mapped_column(String(20))
    reversal_of_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('marketplace_allocations.id'))
    adjustment_of_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('marketplace_allocations.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    calculation_snapshot: Mapped[dict] = mapped_column(JSON)
    calculation_hash: Mapped[str] = mapped_column(String(64))


@event.listens_for(MarketplaceAllocation, 'before_update')
@event.listens_for(MarketplaceAllocation, 'before_delete')
def immutable_allocation(mapper, connection, target):
    raise ValueError('Posted allocations are immutable. Append reversal/adjustment records instead.')