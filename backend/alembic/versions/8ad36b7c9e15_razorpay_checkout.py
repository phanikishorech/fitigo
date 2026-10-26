"""Durable gateway checkout links and webhook deduplication; retain existing payment ledger."""
from alembic import op
import sqlalchemy as sa

revision = "8ad36b7c9e15"
down_revision = "7fc25a6b8d04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("payment_checkouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("gateway_order_id", sa.String(80), unique=True),
        sa.Column("gateway_payment_id", sa.String(80), unique=True),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "source_key", name="uq_gateway_checkout_source"))
    op.create_index("ix_payment_checkouts_user_id", "payment_checkouts", ["user_id"])
    op.create_index("ix_payment_checkouts_status", "payment_checkouts", ["status"])
    op.create_table("payment_webhook_receipts",
        sa.Column("id", sa.String(100), primary_key=True), sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("event", sa.String(60), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    for table, column, unique in [("bookings", "checkout_id", False), ("cart_items", "checkout_id", False),
                                   ("user_memberships", "gateway_checkout_id", True), ("platform_membership_orders", "checkout_id", True)]:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(column, sa.String(36), nullable=True))
            batch.create_foreign_key(f"fk_{table}_gateway", "payment_checkouts", [column], ["id"])
            if unique:
                batch.create_unique_constraint(f"uq_{table}_gateway", [column])
            else:
                batch.create_index(f"ix_{table}_{column}", [column])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM payment_checkouts")):
        raise RuntimeError("Gateway checkout history exists. Archive and reconcile it explicitly before downgrading.")
    for table, column, unique in [("platform_membership_orders", "checkout_id", True), ("user_memberships", "gateway_checkout_id", True),
                                   ("cart_items", "checkout_id", False), ("bookings", "checkout_id", False)]:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_gateway", type_="foreignkey")
            if unique:
                batch.drop_constraint(f"uq_{table}_gateway", type_="unique")
            else:
                batch.drop_index(f"ix_{table}_{column}")
            batch.drop_column(column)
    op.drop_table("payment_webhook_receipts")
    op.drop_table("payment_checkouts")