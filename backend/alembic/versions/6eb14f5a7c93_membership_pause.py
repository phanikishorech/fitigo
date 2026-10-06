"""Membership-scoped pause policy and scheduling. Legacy account pauses preserved."""
from alembic import op
import sqlalchemy as sa

revision = "6eb14f5a7c93"
down_revision = "5da03e4f6b82"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("gym_membership_plans", "platform_membership_plans"):
        op.add_column(table, sa.Column("pause_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column("max_pause_days", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_memberships", sa.Column("original_end_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE user_memberships SET original_end_at = end_at WHERE original_end_at IS NULL")
    op.create_table("membership_pauses",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("membership_id", sa.BigInteger(), sa.ForeignKey("user_memberships.id"), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("previous_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("membership_id", "request_key", name="uq_membership_pause_request"))
    op.create_index("ix_membership_pauses_range", "membership_pauses", ["membership_id", "start_date", "end_date"])


def downgrade():
    # End dates intentionally remain extended; don't silently remove purchased access.
    op.drop_index("ix_membership_pauses_range", table_name="membership_pauses")
    op.drop_table("membership_pauses")
    op.drop_column("user_memberships", "original_end_at")
    for table in ("gym_membership_plans", "platform_membership_plans"):
        op.drop_column(table, "max_pause_days")
        op.drop_column(table, "pause_allowed")