"""Password recovery and session revocation.

Revision ID: 5da03e4f6b82
Revises: 4c9f2d3e5a71
"""
from alembic import op
import sqlalchemy as sa

revision = '5da03e4f6b82'
down_revision = '4c9f2d3e5a71'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('password_reset_tokens',
                    sa.Column('token_hash', sa.String(64), primary_key=True),
                    sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    op.create_table('auth_rate_limits',
                    sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('attempts', sa.Integer(), nullable=False),
                    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('auth_rate_limits')
    op.drop_index('ix_password_reset_tokens_user_id', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_column('users', 'token_version')