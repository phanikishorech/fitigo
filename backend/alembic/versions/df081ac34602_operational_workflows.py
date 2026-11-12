"""Phase 6 operational audit and recoverable photo cleanup (additive)."""
from alembic import op
import sqlalchemy as sa

revision = 'df081ac34602'
down_revision = 'cef70fb23591'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('operation_audits'):
        op.create_table('operation_audits',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('actor_id', sa.BigInteger()), sa.Column('action', sa.String(50), nullable=False),
            sa.Column('resource_type', sa.String(30), nullable=False), sa.Column('resource_id', sa.BigInteger(), nullable=False),
            sa.Column('reason_code', sa.String(40), nullable=False), sa.Column('context', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False))
    if not sa.inspect(bind).has_table('photo_deletions'):
        op.create_table('photo_deletions',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('image_id', sa.BigInteger(), nullable=False), sa.Column('gym_id', sa.BigInteger(), nullable=False),
            sa.Column('actor_id', sa.BigInteger(), nullable=False), sa.Column('file_path', sa.String(500), nullable=False),
            sa.Column('storage_root', sa.String(500), nullable=False),
            sa.Column('fingerprint', sa.String(64)), sa.Column('status', sa.String(20), nullable=False),
            sa.Column('error_code', sa.String(40)), sa.Column('attempts', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('completed_at', sa.DateTime()),
            sa.UniqueConstraint('image_id', name='uq_photo_deletions_image_id'))
    for table, columns in [('operation_audits', ['action', 'created_at']), ('photo_deletions', ['gym_id', 'status'])]:
        indexes = {i['name'] for i in sa.inspect(bind).get_indexes(table)}
        for column in columns:
            name = f'ix_{table}_{column}'
            if name not in indexes: op.create_index(name, table, [column])


def downgrade():
    bind = op.get_bind()
    for table in ('operation_audits', 'photo_deletions'):
        if sa.inspect(bind).has_table(table) and bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Archive operational evidence and deletion jobs before downgrade; no records removed.')
    for table in ('photo_deletions', 'operation_audits'):
        if sa.inspect(bind).has_table(table): op.drop_table(table)