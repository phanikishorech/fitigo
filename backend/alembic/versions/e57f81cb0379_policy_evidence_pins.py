"""Add dormant policy/source bindings only. No historical backfill or journal."""
from alembic import op
import sqlalchemy as sa
revision = 'e57f81cb0379'
down_revision = 'd46e70ba9268'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_agreement_pins',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('checkout_id', sa.String(36), sa.ForeignKey('payment_checkouts.id'), nullable=False),
        sa.Column('context', sa.String(40), nullable=False), sa.Column('source_key', sa.String(100), nullable=False),
        sa.Column('mode', sa.String(10), nullable=False),
        sa.Column('agreement_version_id', sa.BigInteger(), sa.ForeignKey('financial_agreement_versions.id'), nullable=False),
        sa.Column('selection_policy_version_id', sa.BigInteger(), sa.ForeignKey('financial_agreement_versions.id'), nullable=False),
        sa.Column('selected_at', sa.DateTime(), nullable=False), sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('evidence_hash', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('checkout_id', 'context', 'source_key', name='uq_agreement_pin_source'))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM financial_agreement_pins')):
        raise RuntimeError('Policy pin evidence exists; downgrade refused.')
    op.drop_table('financial_agreement_pins')