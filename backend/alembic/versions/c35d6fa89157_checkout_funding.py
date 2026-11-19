"""Checkout funding allocations and wallet holds; existing balances remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = 'c35d6fa89157'
down_revision = 'b24c5ef78046'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('checkout_funding',
        sa.Column('checkout_id', sa.String(36), sa.ForeignKey('payment_checkouts.id'), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('wallet_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('gateway_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False), sa.Column('mode', sa.String(10), nullable=False),
        sa.Column('state', sa.String(20), nullable=False), sa.Column('request_wallet', sa.String(40), nullable=False),
        sa.Column('wallet_transaction_id', sa.BigInteger(), sa.ForeignKey('wallet_transactions.id'), nullable=True, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False), sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('total_amount = wallet_amount + gateway_amount', name='ck_funding_sum'),
        sa.CheckConstraint('wallet_amount >= 0 AND gateway_amount >= 0', name='ck_funding_nonnegative'))
    op.create_index('ix_funding_holds', 'checkout_funding', ['user_id', 'state'])
    op.create_index('ix_funding_expiry', 'checkout_funding', ['state', 'expires_at'])
    op.create_table('booking_funding',
        sa.Column('booking_id', sa.BigInteger(), sa.ForeignKey('bookings.id'), primary_key=True),
        sa.Column('checkout_id', sa.String(36), sa.ForeignKey('checkout_funding.checkout_id'), nullable=False),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('wallet_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('gateway_amount', sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint('total_amount = wallet_amount + gateway_amount', name='ck_booking_funding_sum'),
        sa.CheckConstraint('wallet_amount >= 0 AND gateway_amount >= 0', name='ck_booking_funding_nonnegative'))
    op.create_index('ix_booking_funding_checkout_id', 'booking_funding', ['checkout_id'])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT COUNT(*) FROM checkout_funding')):
        raise RuntimeError('Funding/hold evidence exists; archive/reconcile explicitly before downgrade.')
    op.drop_table('booking_funding'); op.drop_table('checkout_funding')