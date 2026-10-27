"""Wallet checkout linkage, mode isolation and non-sensitive payment attempts."""
from alembic import op
import sqlalchemy as sa

revision = "acf58d9e1037"
down_revision = "9be47c8d0f26"
branch_labels = None
depends_on = None


def upgrade():
    # MySQL DDL is not transactional. Resume safely if a previous deployment
    # added columns but failed before constraints/table/index creation.
    bind = op.get_bind()
    if 'payment_mode' not in {c['name'] for c in sa.inspect(bind).get_columns('wallet_accounts')}:
        op.add_column('wallet_accounts', sa.Column('payment_mode', sa.String(10), nullable=True))
    columns = {c['name'] for c in sa.inspect(bind).get_columns('wallet_transactions')}
    foreign_keys = {fk['name'] for fk in sa.inspect(bind).get_foreign_keys('wallet_transactions')}
    unique_keys = {key['name'] for key in sa.inspect(bind).get_unique_constraints('wallet_transactions')}
    with op.batch_alter_table('wallet_transactions') as batch:
        if 'checkout_id' not in columns:
            batch.add_column(sa.Column('checkout_id', sa.String(36), nullable=True))
        if 'fk_wallet_transaction_checkout' not in foreign_keys:
            batch.create_foreign_key('fk_wallet_transaction_checkout', 'payment_checkouts', ['checkout_id'], ['id'])
        if 'uq_wallet_transaction_checkout' not in unique_keys:
            batch.create_unique_constraint('uq_wallet_transaction_checkout', ['checkout_id'])
    if not sa.inspect(bind).has_table('payment_attempts'):
        op.create_table('payment_attempts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('checkout_id', sa.String(36), sa.ForeignKey('payment_checkouts.id'), nullable=False),
        sa.Column('external_id', sa.String(80), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('refunded_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('checkout_id', 'external_id', name='uq_payment_attempt_external'))
    if 'ix_payment_attempts_checkout_id' not in {index['name'] for index in sa.inspect(bind).get_indexes('payment_attempts')}:
        op.create_index('ix_payment_attempts_checkout_id', 'payment_attempts', ['checkout_id'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM payment_attempts')) or op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM wallet_transactions WHERE checkout_id IS NOT NULL')):
        raise RuntimeError('Reconcile and archive payment attempts and gateway wallet history before downgrade.')
    op.drop_table('payment_attempts')
    with op.batch_alter_table('wallet_transactions') as batch:
        batch.drop_constraint('uq_wallet_transaction_checkout', type_='unique')
        batch.drop_constraint('fk_wallet_transaction_checkout', type_='foreignkey')
        batch.drop_column('checkout_id')
    op.drop_column('wallet_accounts', 'payment_mode')