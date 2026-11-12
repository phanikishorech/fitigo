"""Notification preferences, inbox read state and durable email delivery intent."""
from alembic import op
import sqlalchemy as sa
revision = 'ef192bd45713'
down_revision = 'df081ac34602'
branch_labels = None
depends_on = None


def upgrade():
    bind=op.get_bind()
    if not sa.inspect(bind).has_table('notification_preferences'):
        op.create_table('notification_preferences',
            sa.Column('user_id',sa.BigInteger(),sa.ForeignKey('users.id'),primary_key=True),
            sa.Column('operational_email',sa.Boolean(),nullable=False),
            sa.Column('updated_at',sa.DateTime(),nullable=False))
    if not sa.inspect(bind).has_table('notification_deliveries'):
        op.create_table('notification_deliveries',
            sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
            sa.Column('event_id',sa.BigInteger(),sa.ForeignKey('notification_events.id'),nullable=False),
            sa.Column('user_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('kind',sa.String(50),nullable=False),sa.Column('category',sa.String(20),nullable=False),
            sa.Column('resource_id',sa.BigInteger(),nullable=False),sa.Column('read_at',sa.DateTime()),
            sa.Column('email_status',sa.String(24),nullable=False),sa.Column('recipient_hash',sa.String(64)),
            sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('next_attempt_at',sa.DateTime(),nullable=False),
            sa.Column('claimed_at',sa.DateTime()),sa.Column('claim_id',sa.String(32)),sa.Column('accepted_at',sa.DateTime()),
            sa.Column('error_code',sa.String(40)),sa.Column('created_at',sa.DateTime(),nullable=False),
            sa.UniqueConstraint('event_id',name='uq_notification_deliveries_event'))
    existing={i['name'] for i in sa.inspect(bind).get_indexes('notification_deliveries')}
    for column in ['user_id','email_status','next_attempt_at']:
        name='ix_notification_deliveries_'+column
        if name not in existing: op.create_index(name,'notification_deliveries',[column])


def downgrade():
    bind=op.get_bind()
    for table in ['notification_deliveries','notification_preferences']:
        if sa.inspect(bind).has_table(table) and bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Archive notification evidence/preferences before downgrade; no records deleted.')
    for table in ['notification_deliveries','notification_preferences']:
        if sa.inspect(bind).has_table(table): op.drop_table(table)