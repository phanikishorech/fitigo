"""Versioned configurable financial agreements; seed proposals, not active contracts."""
from alembic import op
import sqlalchemy as sa

revision = 'd46e70ba9268'
down_revision = 'c35d6fa89157'
branch_labels = None
depends_on = None

# User-supplied initial proposal. Runtime calculation/editor code reads stored
# configuration; these values are not fallback constants in business logic.
INITIAL_PROPOSAL = {
    'attended': {'gym_percent': '85.00', 'fitigo_percent': '15.00'},
    'no_show': {'gym_percent': '70.00', 'fitigo_percent': '30.00'},
    'single_gym': {'gym_percent': '85.00', 'fitigo_percent': '15.00'},
    'multi_gym': {'payout_per_visit': None, 'visits_per_member_month': None, 'payout_cap_per_member_month': None},
    'settlements': {'booking_cycle': 'WEEKLY', 'multi_gym_cycle': 'MONTHLY',
        'monthly_single_cycle': 'NEXT_CYCLE', 'quarterly_single_cycle': 'UPFRONT',
        'half_yearly_single_cycle': 'UPFRONT', 'yearly_single_cycle': 'UPFRONT',
        'minimum_payout': '500.00', 'admin_approval_required': True},
    'sharing_basis': 'AFTER_DISCOUNTS_EXCLUDING_TAX', 'gateway_fees': 'SEPARATE_ACTUAL',
    'wallet_same_agreement': True, 'group_basis': 'ATTENDED_VISITORS_WHEN_UNIT_PRICED',
    'business_model': 'AGENT_MARKETPLACE', 'membership_recognition': 'NOT_APPROVED',
}


def upgrade():
    op.create_table('financial_agreement_scopes',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('mode', sa.String(10), nullable=False), sa.Column('scope_key', sa.String(40), nullable=False),
        sa.Column('gym_id', sa.BigInteger(), sa.ForeignKey('gyms.id'), nullable=True),
        sa.Column('template', sa.JSON(), nullable=True),
        sa.UniqueConstraint('mode', 'scope_key', name='uq_financial_agreement_scope'))
    op.create_table('financial_agreement_versions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('scope_id', sa.BigInteger(), sa.ForeignKey('financial_agreement_scopes.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.DateTime(), nullable=False), sa.Column('effective_to', sa.DateTime(), nullable=True),
        sa.Column('terms', sa.JSON(), nullable=False), sa.Column('action', sa.String(20), nullable=False),
        sa.Column('agreement_reference', sa.String(200), nullable=False), sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('ca_status', sa.String(20), nullable=False), sa.Column('ca_reference', sa.String(200), nullable=True),
        sa.Column('actor_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_key', sa.String(64), nullable=False), sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('scope_id', 'version', name='uq_financial_agreement_version'),
        sa.UniqueConstraint('scope_id', 'request_key', name='uq_financial_agreement_request'),
        sa.UniqueConstraint('scope_id', 'effective_from', name='uq_financial_agreement_start'))
    op.create_index('ix_financial_agreement_versions_scope_id', 'financial_agreement_versions', ['scope_id'])
    scope = sa.table('financial_agreement_scopes', sa.column('mode', sa.String()),
        sa.column('scope_key', sa.String()), sa.column('template', sa.JSON()))
    op.bulk_insert(scope, [{'mode': mode, 'scope_key': 'DEFAULT', 'template': INITIAL_PROPOSAL} for mode in ('test', 'live')])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM financial_agreement_versions')):
        raise RuntimeError('Agreement audit history exists; downgrade would destroy evidence.')
    op.drop_table('financial_agreement_versions')
    op.drop_table('financial_agreement_scopes')