"""Append-only financial review controls; no configuration seed or adjustments."""
from alembic import op
import sqlalchemy as sa
revision='eb3f70126935'
down_revision='da2e6f105824'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('financial_review_events',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('case_id',sa.String(36),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('mode',sa.String(10),nullable=False),
        sa.Column('gym_id',sa.BigInteger(),sa.ForeignKey('gyms.id'),nullable=False),
        sa.Column('checkout_id',sa.String(36),sa.ForeignKey('payment_checkouts.id'),nullable=False),
        sa.Column('source_evidence_id',sa.String(36),sa.ForeignKey('financial_source_evidence.id'),nullable=False),
        sa.Column('kind',sa.String(40),nullable=False),sa.Column('status',sa.String(40),nullable=False),
        sa.Column('actor_id',sa.BigInteger(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('reason',sa.String(500),nullable=False),sa.Column('request_key',sa.String(64),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('case_id','revision',name='uq_fin_review_revision'),
        sa.UniqueConstraint('mode','request_key',name='uq_fin_review_request'))
    op.create_index('ix_financial_review_events_case_id','financial_review_events',['case_id'])
    for action in ('UPDATE','DELETE'):
        op.execute(sa.text(f"CREATE TRIGGER financial_review_events_no_{action.lower()} BEFORE {action} ON financial_review_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Financial review history is immutable'"))


def downgrade():
    raise RuntimeError('Forward-only financial review history cannot be removed.')