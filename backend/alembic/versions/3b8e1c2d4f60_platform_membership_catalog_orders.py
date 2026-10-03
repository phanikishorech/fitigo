"""Add platform catalog, offers, unpaid review orders and configuration audit.

Revision ID: 3b8e1c2d4f60
Revises: 2a7d0b9c9a11
"""
from alembic import op
import sqlalchemy as sa


revision = "3b8e1c2d4f60"
down_revision = "2a7d0b9c9a11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_membership_plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("duration_value", sa.Integer(), nullable=False),
        sa.Column("duration_unit", sa.String(10), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("benefits", sa.JSON(), nullable=False),
        sa.Column("badge", sa.String(60), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "platform_membership_offers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("platform_membership_plans.id"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("plan_id"),
    )
    op.create_table(
        "platform_membership_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("platform_membership_plans.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key"),
    )
    op.create_index("ix_platform_membership_orders_user_id", "platform_membership_orders", ["user_id"])
    op.create_table(
        "platform_membership_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("platform_membership_plans.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    # Operator-approved only: this discards catalog/order history. Never auto-downgrade.
    op.drop_table("platform_membership_audit")
    op.drop_index("ix_platform_membership_orders_user_id", table_name="platform_membership_orders")
    op.drop_table("platform_membership_orders")
    op.drop_table("platform_membership_offers")
    op.drop_table("platform_membership_plans")