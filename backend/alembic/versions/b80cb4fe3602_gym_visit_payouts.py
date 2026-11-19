"""Verified monthly visit allocation only; no automatic deployment or payout."""
from alembic import op
import sqlalchemy as sa
revision='b80cb4fe3602'
down_revision='a79ba3ed2591'
branch_labels=None
depends_on=None


def upgrade():
    columns=[sa.Column('id',sa.String(36),primary_key=True)]
    for name,target in (('source_event_id','financial_source_outbox.id'),('source_evidence_id','financial_source_evidence.id'),
        ('checkout_id','payment_checkouts.id'),('owner_evidence_id','gym_owner_evidence.id')):
        columns.append(sa.Column(name,sa.String(36),sa.ForeignKey(target),nullable=False,unique=name=='source_event_id'))
    for name,target in (('membership_id','user_memberships.id'),('customer_id','users.id'),('gym_id','gyms.id'),
        ('owner_user_id','users.id'),('checkin_id','checkins.id'),('daily_access_id','customer_daily_accesses.id'),('agreement_pin_id','financial_agreement_pins.id'),
        ('agreement_version_id','financial_agreement_versions.id')):
        columns.append(sa.Column(name,sa.BigInteger(),sa.ForeignKey(target),nullable=False))
    for name,size in (('mode',10),('currency',3),('status',40),('fee_status',40),('idempotency_key',64),('snapshot_hash',64)):
        columns.append(sa.Column(name,sa.String(size),nullable=False,unique=name=='idempotency_key'))
    for name in ('configured_amount','approved_amount','applied_cap'):
        columns.append(sa.Column(name,sa.Numeric(12,2),nullable=False))
    columns += [sa.Column('service_date',sa.Date(),nullable=False),sa.Column('allocation_period',sa.Date(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.UniqueConstraint('mode','checkin_id',name='uq_visit_payout_checkin'),
        sa.UniqueConstraint('mode','daily_access_id',name='uq_visit_payout_daily_access'),
        sa.CheckConstraint('approved_amount >= 0 AND approved_amount <= configured_amount',name='ck_visit_amount')]
    op.create_table('gym_visit_payouts',*columns)
    op.create_index('ix_visit_payout_period','gym_visit_payouts',['mode','allocation_period','gym_id','membership_id'])
    for action in ('UPDATE','DELETE'):
        op.execute(sa.text(f"CREATE TRIGGER gym_visit_payouts_no_{action.lower()} BEFORE {action} ON gym_visit_payouts FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Visit allocations are immutable'"))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM gym_visit_payouts')):
        raise RuntimeError('Visit payout evidence exists; downgrade refused.')
    for action in ('update','delete'):op.execute(sa.text(f'DROP TRIGGER IF EXISTS gym_visit_payouts_no_{action}'))
    op.drop_table('gym_visit_payouts')