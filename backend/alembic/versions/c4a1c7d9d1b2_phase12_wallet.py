"""phase12_wallet

Revision ID: c4a1c7d9d1b2
Revises: b9c3b3a2f1a1
Create Date: 2026-08-25 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a1c7d9d1b2'
down_revision = 'b9c3b3a2f1a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'wallet_accounts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text('0')),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'INR'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_wallet_accounts_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wallet_accounts')),
        sa.UniqueConstraint('user_id', name=op.f('uq_wallet_accounts_user_id')),
    )
    op.create_index('ix_wallet_accounts_user_id', 'wallet_accounts', ['user_id'], unique=False)

    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('txn_type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default=sa.text("'INR'")),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wallet_accounts.id'], name=op.f('fk_wallet_transactions_account_id_wallet_accounts')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_wallet_transactions_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wallet_transactions')),
    )
    op.create_index('ix_wallet_transactions_account_id', 'wallet_transactions', ['account_id'], unique=False)
    op.create_index('ix_wallet_transactions_user_id', 'wallet_transactions', ['user_id'], unique=False)
    op.create_index('ix_wallet_transactions_created_at', 'wallet_transactions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_wallet_transactions_created_at', table_name='wallet_transactions')
    op.drop_index('ix_wallet_transactions_user_id', table_name='wallet_transactions')
    op.drop_index('ix_wallet_transactions_account_id', table_name='wallet_transactions')
    op.drop_table('wallet_transactions')

    op.drop_index('ix_wallet_accounts_user_id', table_name='wallet_accounts')
    op.drop_table('wallet_accounts')
