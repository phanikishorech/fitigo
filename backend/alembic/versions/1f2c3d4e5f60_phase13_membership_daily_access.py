"""phase13_membership_daily_access

Revision ID: 1f2c3d4e5f60
Revises: c4a1c7d9d1b2
Create Date: 2026-09-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f2c3d4e5f60'
down_revision = 'c4a1c7d9d1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'membership_daily_accesses',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('gym_id', sa.BigInteger(), nullable=False),
        sa.Column('access_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='SCANNED'),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.id'], name=op.f('fk_membership_daily_accesses_gym_id_gyms')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_membership_daily_accesses_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_daily_accesses')),
        sa.UniqueConstraint('user_id', 'gym_id', 'access_date', name=op.f('uq_membership_daily_accesses_user_id')),
    )
    op.create_index('ix_membership_daily_accesses_access_date', 'membership_daily_accesses', ['access_date'], unique=False)
    op.create_index('ix_membership_daily_accesses_gym_id', 'membership_daily_accesses', ['gym_id'], unique=False)
    op.create_index('ix_membership_daily_accesses_user_id', 'membership_daily_accesses', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_membership_daily_accesses_user_id', table_name='membership_daily_accesses')
    op.drop_index('ix_membership_daily_accesses_gym_id', table_name='membership_daily_accesses')
    op.drop_index('ix_membership_daily_accesses_access_date', table_name='membership_daily_accesses')
    op.drop_table('membership_daily_accesses')
