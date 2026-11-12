"""Persistent single-use staff invitations and OTP challenges; no existing data edits."""
from alembic import op
import sqlalchemy as sa

revision = 'bdf69ea12480'
down_revision = 'acf58d9e1037'
branch_labels = None
depends_on = None


def upgrade():
    # Resume cleanly after partially committed MySQL DDL.
    if not sa.inspect(op.get_bind()).has_table('account_otps'):
        op.create_table('account_otps',
            sa.Column('key', sa.String(64), primary_key=True),
            sa.Column('channel', sa.String(10), nullable=False),
            sa.Column('purpose', sa.String(20), nullable=False),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('token_version', sa.Integer(), nullable=True),
            sa.Column('nonce', sa.String(64), nullable=False),
            sa.Column('code_hash', sa.String(64), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('attempts_left', sa.Integer(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True))
    if not sa.inspect(op.get_bind()).has_table('staff_invitations'):
        op.create_table('staff_invitations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('gym_id', sa.BigInteger(), sa.ForeignKey('gyms.id'), nullable=False),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('owner_user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('accepted_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('gym_id', 'user_id', name='uq_staff_invitation_gym_user'))


def downgrade():
    bind = op.get_bind()
    for table in ('staff_invitations', 'account_otps'):
        if sa.inspect(bind).has_table(table) and bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Archive account invitation/OTP records explicitly before downgrade; no records were deleted.')
    for table in ('staff_invitations', 'account_otps'):
        if sa.inspect(bind).has_table(table):
            op.drop_table(table)