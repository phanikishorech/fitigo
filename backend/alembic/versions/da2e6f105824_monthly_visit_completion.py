"""Append-only monthly visit completion and once-per-membership fee budgets.

No seeding, backfill, configuration changes or processing activation.
"""
from alembic import op
import sqlalchemy as sa

revision = 'da2e6f105824'
down_revision = 'c91dc50f4713'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('gym_visit_payouts', 'applied_cap', existing_type=sa.Numeric(12,2), nullable=True)
    op.create_table('gym_monthly_calculations',
        sa.Column('id',sa.String(36),primary_key=True), sa.Column('mode',sa.String(10),nullable=False),
        sa.Column('gym_id',sa.BigInteger(),sa.ForeignKey('gyms.id'),nullable=False),
        sa.Column('period',sa.Date(),nullable=False),sa.Column('revision',sa.BigInteger(),nullable=False),
        sa.Column('source_evidence_id',sa.String(36),sa.ForeignKey('financial_source_evidence.id'),nullable=True,unique=True),
        sa.Column('actor_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('gross_amount',sa.Numeric(12,2),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('mode','gym_id','period','revision',name='uq_monthly_gym_revision'))
    op.create_table('membership_visit_fees',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('checkout_id',sa.String(36),sa.ForeignKey('payment_checkouts.id'),nullable=False,unique=True),
        sa.Column('fee_evidence_id',sa.String(36),sa.ForeignKey('financial_source_evidence.id'),nullable=False),
        sa.Column('mode',sa.String(10),nullable=False),sa.Column('actual_fee',sa.Numeric(12,2),nullable=False),
        sa.Column('snapshot',sa.JSON(),nullable=False),sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    for table in ('gym_monthly_calculations','membership_visit_fees'):
        for action in ('UPDATE','DELETE'):
            op.execute(sa.text(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Monthly financial evidence is immutable'"))


def downgrade():
    raise RuntimeError('Forward-only financial migration; history must not be removed.')