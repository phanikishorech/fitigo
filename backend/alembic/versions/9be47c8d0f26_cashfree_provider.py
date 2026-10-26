"""Extend the existing checkout, preserving all Razorpay history."""
from alembic import op
import sqlalchemy as sa

revision = "9be47c8d0f26"
down_revision = "8ad36b7c9e15"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payment_checkouts", sa.Column("provider", sa.String(20), nullable=False, server_default="RAZORPAY"))
    op.add_column("payment_checkouts", sa.Column("checkout_data", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM payment_checkouts WHERE provider <> 'RAZORPAY'")):
        raise RuntimeError("Reconcile and archive Cashfree history before removing provider attribution.")
    op.drop_column("payment_checkouts", "checkout_data")
    op.drop_column("payment_checkouts", "provider")