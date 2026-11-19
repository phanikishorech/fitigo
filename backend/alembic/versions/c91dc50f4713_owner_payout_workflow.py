"""Manual owner payout reservations and append-only audit. No payment calls."""
from alembic import op
import sqlalchemy as sa
revision='c91dc50f4713'
down_revision='b80cb4fe3602'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('owner_payouts',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('mode',sa.String(10),nullable=False),
        sa.Column('gym_id',sa.BigInteger(),sa.ForeignKey('gyms.id'),nullable=False),
        sa.Column('owner_user_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('category',sa.String(30),nullable=False),sa.Column('period_start',sa.Date(),nullable=False),sa.Column('period_end',sa.Date(),nullable=False),
        sa.Column('entitlement_amount',sa.Numeric(12,2),nullable=False),sa.Column('deduction_amount',sa.Numeric(12,2),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),sa.Column('currency',sa.String(3),nullable=False),sa.Column('status',sa.String(30),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('requested_by',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('approved_by',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=True),sa.Column('payment_reference',sa.String(100),nullable=True),
        sa.Column('paid_at',sa.DateTime(),nullable=True),sa.Column('payment_evidence',sa.JSON(),nullable=True),
        sa.Column('request_key',sa.String(64),nullable=False),sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('deductions',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('mode','request_key',name='uq_owner_payout_request'),sa.UniqueConstraint('mode','payment_reference',name='uq_owner_payout_payment'),
        sa.CheckConstraint('entitlement_amount > 0 AND deduction_amount >= 0 AND amount > 0 AND amount + deduction_amount = entitlement_amount',name='ck_owner_payout_amount'))
    op.create_table('owner_payout_items',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('payout_id',sa.String(36),sa.ForeignKey('owner_payouts.id'),nullable=False),
        sa.Column('allocation_id',sa.String(36),sa.ForeignKey('marketplace_allocations.id'),nullable=True),
        sa.Column('visit_payout_id',sa.String(36),sa.ForeignKey('gym_visit_payouts.id'),nullable=True),sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.UniqueConstraint('payout_id','allocation_id',name='uq_payout_allocation_item'),sa.UniqueConstraint('payout_id','visit_payout_id',name='uq_payout_visit_item'),
        sa.CheckConstraint('(allocation_id IS NULL) <> (visit_payout_id IS NULL)',name='ck_payout_item_source'),sa.CheckConstraint('amount > 0',name='ck_payout_item_positive'))
    op.create_table('owner_payout_audit',sa.Column('id',sa.String(36),primary_key=True),sa.Column('payout_id',sa.String(36),sa.ForeignKey('owner_payouts.id'),nullable=False),
        sa.Column('actor_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),sa.Column('from_status',sa.String(30),nullable=True),
        sa.Column('mode',sa.String(10),nullable=False),sa.Column('actual_reference',sa.String(100),nullable=True),
        sa.Column('to_status',sa.String(30),nullable=False),sa.Column('reason',sa.String(500),nullable=False),sa.Column('request_key',sa.String(64),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('evidence',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('payout_id','request_key',name='uq_payout_audit_request'),
        sa.UniqueConstraint('mode','actual_reference',name='uq_payout_audit_actual_reference'))
    for table in ('owner_payout_items','owner_payout_audit'):
        for action in ('UPDATE','DELETE'):
            op.execute(sa.text(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payout evidence is immutable'"))


def downgrade():
    for table in ('owner_payouts','owner_payout_items','owner_payout_audit'):
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):raise RuntimeError('Payout history exists; downgrade refused.')
    for table in ('owner_payout_items','owner_payout_audit'):
        for action in ('update','delete'):op.execute(sa.text(f'DROP TRIGGER IF EXISTS {table}_no_{action}'))
    for table in ('owner_payout_audit','owner_payout_items','owner_payouts'):op.drop_table(table)