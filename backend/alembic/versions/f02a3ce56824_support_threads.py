"""Private support requests and immutable conversation entries."""
from alembic import op
import sqlalchemy as sa

revision = 'f02a3ce56824'
down_revision = 'ef192bd45713'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('support_tickets'):
        op.create_table('support_tickets',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('request_key', sa.String(64), nullable=False),
            sa.Column('category', sa.String(20), nullable=False),
            sa.Column('subject', sa.String(120), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('user_id', 'request_key', name='uq_support_ticket_request'))
    if not sa.inspect(bind).has_table('support_messages'):
        op.create_table('support_messages',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('ticket_id', sa.BigInteger(), sa.ForeignKey('support_tickets.id'), nullable=False),
            sa.Column('author_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('author_kind', sa.String(20), nullable=False),
            sa.Column('request_key', sa.String(64), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('ticket_id', 'author_id', 'request_key', name='uq_support_message_request'))
    for table, columns in [('support_tickets', ['user_id', 'status', 'updated_at']), ('support_messages', ['ticket_id'])]:
        indexes = {i['name'] for i in sa.inspect(bind).get_indexes(table)}
        for column in columns:
            name = f'ix_{table}_{column}'
            if name not in indexes: op.create_index(name, table, [column])


def downgrade():
    bind = op.get_bind()
    for table in ('support_messages', 'support_tickets'):
        if sa.inspect(bind).has_table(table) and bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Archive support conversations explicitly before downgrade; no records deleted.')
    for table in ('support_messages', 'support_tickets'):
        if sa.inspect(bind).has_table(table): op.drop_table(table)