"""Explicit Multi-Gym entitlements and controlled wallet checkout.

Revision ID: 4c9f2d3e5a71
Revises: 3b8e1c2d4f60
"""
from alembic import op
import sqlalchemy as sa

revision = "4c9f2d3e5a71"
down_revision = "3b8e1c2d4f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gyms", sa.Column("multi_gym_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("user_memberships", "gym_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("user_memberships", "plan_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("user_memberships", "paid_amount", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(12, 2), existing_nullable=False)
    op.add_column("user_memberships", sa.Column("membership_type", sa.String(20), nullable=False, server_default="SINGLE_GYM"))
    op.add_column("user_memberships", sa.Column("platform_plan_id", sa.BigInteger(), nullable=True))
    op.add_column("user_memberships", sa.Column("checkout_key", sa.String(100), nullable=True))
    op.add_column("user_memberships", sa.Column("wallet_transaction_id", sa.BigInteger(), nullable=True))
    op.add_column("user_memberships", sa.Column("terms_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_membership_platform_plan", "user_memberships", "platform_membership_plans", ["platform_plan_id"], ["id"])
    op.create_foreign_key("fk_membership_wallet_transaction", "user_memberships", "wallet_transactions", ["wallet_transaction_id"], ["id"])
    op.create_unique_constraint("uq_membership_checkout", "user_memberships", ["user_id", "checkout_key"])
    op.create_unique_constraint("uq_membership_wallet_transaction", "user_memberships", ["wallet_transaction_id"])
    op.add_column("platform_membership_orders", sa.Column("membership_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_platform_order_membership", "platform_membership_orders", "user_memberships", ["membership_id"], ["id"])
    op.create_unique_constraint("uq_platform_order_membership", "platform_membership_orders", ["membership_id"])


def downgrade():
    raise RuntimeError("Wallet membership history must not be dropped automatically. Use a reviewed backup/forward repair.")