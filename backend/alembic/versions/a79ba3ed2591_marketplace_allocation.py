"""Lightweight immutable commercial allocation schema. No posting/backfill."""
from alembic import op
import sqlalchemy as sa

revision = 'a79ba3ed2591'
down_revision = 'f68a92dc1480'
branch_labels = None
depends_on = None


def upgrade():
    columns = [sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('original_unit_key',sa.String(64),nullable=True,unique=True)]
    for name, target in (
        ('source_event_id','financial_source_outbox.id'), ('source_evidence_id','financial_source_evidence.id'),
        ('checkout_id','payment_checkouts.id'), ('owner_evidence_id','gym_owner_evidence.id')):
        columns.append(sa.Column(name, sa.String(36), sa.ForeignKey(target), nullable=False))
    for name, target, nullable in (
        ('gym_id','gyms.id',False), ('owner_user_id','users.id',False), ('customer_id','users.id',False),
        ('booking_id','bookings.id',True), ('membership_id','user_memberships.id',True),
        ('agreement_pin_id','financial_agreement_pins.id',False), ('agreement_version_id','financial_agreement_versions.id',False)):
        columns.append(sa.Column(name, sa.BigInteger(), sa.ForeignKey(target), nullable=nullable))
    for name, size in (('source_type',50),('source_record_id',100),('allocation_key',100),('idempotency_key',64),
        ('transaction_reference',100),('mode',10),('category',30),('currency',3),('fee_status',40),
        ('calculation_status',40),('posting_status',20),('entry_kind',20),('calculation_hash',64)):
        columns.append(sa.Column(name, sa.String(size), nullable=False))
    for name in ('price_amount','discount_amount','tax_amount','eligible_amount','customer_funded_amount',
                 'wallet_amount','gateway_amount','gym_gross_share','fitigo_gross_commission'):
        columns.append(sa.Column(name, sa.Numeric(12,2), nullable=False))
    for name in ('gateway_fee','gym_gateway_fee_share','fitigo_gateway_fee_share','gym_owner_net_entitlement','fitigo_net_commission'):
        columns.append(sa.Column(name, sa.Numeric(12,2), nullable=True))
    columns += [sa.Column('visitor_index',sa.Integer(),nullable=True), sa.Column('agreement_version',sa.Integer(),nullable=False),
        sa.Column('reversal_of_id',sa.String(36),sa.ForeignKey('marketplace_allocations.id'),nullable=True),
        sa.Column('adjustment_of_id',sa.String(36),sa.ForeignKey('marketplace_allocations.id'),nullable=True),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('calculation_snapshot',sa.JSON(),nullable=False),
        sa.UniqueConstraint('source_event_id','allocation_key',name='uq_marketplace_source_allocation'),
        sa.UniqueConstraint('reversal_of_id',name='uq_marketplace_full_reversal'),sa.UniqueConstraint('idempotency_key'),
        sa.CheckConstraint("mode IN ('test','live') AND currency = 'INR'",name='ck_marketplace_mode_currency'),
        sa.CheckConstraint("entry_kind IN ('ORIGINAL','REVERSAL','FEE_ADJUSTMENT','REPLACEMENT')",name='ck_marketplace_entry_kind'),
        sa.CheckConstraint("posting_status = 'POSTED'",name='ck_marketplace_posted_only'),
        sa.CheckConstraint('gym_gross_share + fitigo_gross_commission = eligible_amount',name='ck_marketplace_gross_balance'),
        sa.CheckConstraint('wallet_amount + gateway_amount = customer_funded_amount',name='ck_marketplace_funding_balance'),
        sa.CheckConstraint('(gateway_fee IS NULL AND gym_gateway_fee_share IS NULL AND fitigo_gateway_fee_share IS NULL AND gym_owner_net_entitlement IS NULL AND fitigo_net_commission IS NULL) OR '
            '(gateway_fee IS NOT NULL AND gym_gateway_fee_share IS NOT NULL AND fitigo_gateway_fee_share IS NOT NULL AND gym_owner_net_entitlement IS NOT NULL AND fitigo_net_commission IS NOT NULL AND '
            'gym_gateway_fee_share + fitigo_gateway_fee_share = gateway_fee AND gym_owner_net_entitlement = gym_gross_share - gym_gateway_fee_share AND '
            'fitigo_net_commission = fitigo_gross_commission - fitigo_gateway_fee_share)',name='ck_marketplace_net_balance'),
        sa.CheckConstraint("(entry_kind = 'REVERSAL' AND reversal_of_id IS NOT NULL AND adjustment_of_id IS NULL) OR "
            "(entry_kind IN ('FEE_ADJUSTMENT','REPLACEMENT') AND reversal_of_id IS NULL AND adjustment_of_id IS NOT NULL) OR "
            "(entry_kind = 'ORIGINAL' AND reversal_of_id IS NULL AND adjustment_of_id IS NULL)", name='ck_marketplace_correction_reference')]
    op.create_table('marketplace_allocations', *columns)
    op.create_index('ix_marketplace_owner_period','marketplace_allocations',['mode','owner_user_id','occurred_at'])
    # MySQL protection includes bulk/raw UPDATE and DELETE, not just ORM guards.
    for action in ('UPDATE','DELETE'):
        op.execute(sa.text(f"CREATE TRIGGER marketplace_allocations_no_{action.lower()} BEFORE {action} ON marketplace_allocations "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Posted allocations are immutable'"))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM marketplace_allocations')):
        raise RuntimeError('Allocation history exists; destructive downgrade refused.')
    for action in ('update','delete'): op.execute(sa.text(f'DROP TRIGGER IF EXISTS marketplace_allocations_no_{action}'))
    op.drop_table('marketplace_allocations')