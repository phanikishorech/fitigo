"""Explicit class session provenance; no inferred legacy relationships."""
from alembic import op
import sqlalchemy as sa

revision = 'cef70fb23591'
down_revision = 'bdf69ea12480'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'sync_kind' not in {c['name'] for c in sa.inspect(bind).get_columns('gym_slots')}:
        op.add_column('gym_slots', sa.Column('sync_kind', sa.String(12), nullable=False, server_default='LEGACY'))
    if 'source_slot_id' not in {c['name'] for c in sa.inspect(bind).get_columns('class_sessions')}:
        op.add_column('class_sessions', sa.Column('source_slot_id', sa.BigInteger(), nullable=True))
    if 'fk_class_sessions_source_slot' not in {fk['name'] for fk in sa.inspect(bind).get_foreign_keys('class_sessions')}:
        with op.batch_alter_table('class_sessions') as batch:
            batch.create_foreign_key('fk_class_sessions_source_slot', 'gym_slots', ['source_slot_id'], ['id'])
    if 'ix_class_sessions_source_slot_id' not in {i['name'] for i in sa.inspect(bind).get_indexes('class_sessions')}:
        op.create_index('ix_class_sessions_source_slot_id', 'class_sessions', ['source_slot_id'])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT COUNT(*) FROM class_sessions WHERE source_slot_id IS NOT NULL')):
        raise RuntimeError('Archive class-session provenance before downgrade; no links were removed.')
    if bind.scalar(sa.text("SELECT COUNT(*) FROM gym_slots WHERE sync_kind != 'LEGACY'")):
        raise RuntimeError('Archive slot provenance before downgrade; no metadata was removed.')
    with op.batch_alter_table('class_sessions') as batch:
        batch.drop_constraint('fk_class_sessions_source_slot', type_='foreignkey')
        batch.drop_index('ix_class_sessions_source_slot_id')
        batch.drop_column('source_slot_id')
    op.drop_column('gym_slots', 'sync_kind')