"""Immutable source evidence and transactional outbox; no historical backfill."""
from alembic import op
import sqlalchemy as sa

revision = 'f68a92dc1480'
down_revision = 'e57f81cb0379'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_source_evidence',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('idempotency_key', sa.String(64), nullable=False, unique=True),
        sa.Column('event_type', sa.String(50), nullable=False), sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_id', sa.String(100), nullable=False),
        sa.Column('checkout_id', sa.String(36), sa.ForeignKey('payment_checkouts.id'), nullable=True),
        sa.Column('mode', sa.String(10), nullable=True), sa.Column('evidence_status', sa.String(40), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=True), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True), sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False), sa.Column('payload_hash', sa.String(64), nullable=False))
    op.create_table('financial_source_outbox',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evidence_id', sa.String(36), sa.ForeignKey('financial_source_evidence.id'), nullable=False, unique=True),
        sa.Column('idempotency_key', sa.String(64), nullable=False, unique=True),
        sa.Column('event_type', sa.String(50), nullable=False), sa.Column('source_id', sa.String(100), nullable=False),
        sa.Column('mode', sa.String(10), nullable=False), sa.Column('occurred_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('status', sa.String(30), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False), sa.Column('last_error', sa.String(500), nullable=True),
        sa.Column('available_at', sa.DateTime(), nullable=False), sa.Column('lease_until', sa.DateTime(), nullable=True),
        sa.Column('lease_token', sa.String(36), nullable=True), sa.Column('binding_status', sa.String(40), nullable=False),
        sa.Column('agreement_pin_id', sa.BigInteger(), sa.ForeignKey('financial_agreement_pins.id'), nullable=True))
    op.create_index('ix_source_outbox_claim', 'financial_source_outbox', ['mode', 'status', 'available_at'])
    op.create_table('gym_owner_evidence',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('evidence_id', sa.String(36), sa.ForeignKey('financial_source_evidence.id'), nullable=False, unique=True),
        sa.Column('gym_id', sa.BigInteger(), sa.ForeignKey('gyms.id'), nullable=False),
        sa.Column('owner_user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False), sa.Column('basis', sa.String(40), nullable=False))
    op.create_index('ix_gym_owner_evidence_gym_id', 'gym_owner_evidence', ['gym_id'])


def downgrade():
    for name in ('financial_source_outbox', 'gym_owner_evidence', 'financial_source_evidence'):
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {name}')):
            raise RuntimeError('Source evidence exists; destructive downgrade refused.')
    for name in ('gym_owner_evidence', 'financial_source_outbox', 'financial_source_evidence'):
        op.drop_table(name)