"""Unique cancellation evidence and single lifetime membership transfer."""
from alembic import op
import sqlalchemy as sa

revision = 'b24c5ef78046'
down_revision = 'a13b4df67935'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('booking_cancellations',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('booking_id', sa.BigInteger(), sa.ForeignKey('bookings.id'), nullable=False, unique=True),
        sa.Column('payment_id', sa.BigInteger(), sa.ForeignKey('payments.id'), nullable=True),
        sa.Column('wallet_transaction_id', sa.BigInteger(), sa.ForeignKey('wallet_transactions.id'), nullable=True, unique=True),
        sa.Column('actor_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('scheduled_start', sa.DateTime(), nullable=False),
        sa.Column('deadline', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('membership_transfers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('membership_id', sa.BigInteger(), sa.ForeignKey('user_memberships.id'), nullable=False, unique=True),
        sa.Column('original_user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('actor_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_key', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('consumed_access_date', sa.Date(), nullable=True),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=False),
        sa.Column('original_end_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    for column in ('original_user_id', 'recipient_user_id'):
        op.create_index('ix_membership_transfers_' + column, 'membership_transfers', [column])


def downgrade():
    bind = op.get_bind()
    for table in ('membership_transfers', 'booking_cancellations'):
        if bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Policy audit records exist. Preserve the audit trail; downgrade refused.')
    op.drop_table('membership_transfers')
    op.drop_table('booking_cancellations')