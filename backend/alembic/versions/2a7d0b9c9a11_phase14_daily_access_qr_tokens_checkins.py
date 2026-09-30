"""phase14_daily_access_qr_tokens_checkins

Revision ID: 2a7d0b9c9a11
Revises: 1f2c3d4e5f60
Create Date: 2026-09-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2a7d0b9c9a11"
down_revision = "1f2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_pause_days",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("access_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_access_pause_days_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_pause_days")),
        sa.UniqueConstraint("user_id", "access_date", name=op.f("uq_access_pause_days_user_id")),
    )
    op.create_index("ix_access_pause_days_user_id", "access_pause_days", ["user_id"], unique=False)
    op.create_index("ix_access_pause_days_access_date", "access_pause_days", ["access_date"], unique=False)

    op.create_table(
        "customer_daily_accesses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("membership_id", sa.BigInteger(), nullable=False),
        sa.Column("access_type", sa.String(length=20), nullable=False),
        sa.Column("gym_id", sa.BigInteger(), nullable=True),
        sa.Column("access_date", sa.Date(), nullable=False),
        sa.Column("access_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="AVAILABLE"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_gym_id", sa.BigInteger(), nullable=True),
        sa.Column("checkin_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["gym_id"], ["gyms.id"], name=op.f("fk_customer_daily_accesses_gym_id_gyms")),
        sa.ForeignKeyConstraint(["membership_id"], ["user_memberships.id"], name=op.f("fk_customer_daily_accesses_membership_id_user_memberships")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_customer_daily_accesses_user_id_users")),
        sa.ForeignKeyConstraint(["used_gym_id"], ["gyms.id"], name=op.f("fk_customer_daily_accesses_used_gym_id_gyms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_daily_accesses")),
        sa.UniqueConstraint("access_key", name=op.f("uq_customer_daily_accesses_access_key")),
    )
    op.create_index("ix_customer_daily_accesses_user_id", "customer_daily_accesses", ["user_id"], unique=False)
    op.create_index("ix_customer_daily_accesses_access_date", "customer_daily_accesses", ["access_date"], unique=False)
    op.create_index("ix_customer_daily_accesses_status", "customer_daily_accesses", ["status"], unique=False)

    op.create_table(
        "access_qr_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("daily_access_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_gym_id", sa.BigInteger(), nullable=True),
        sa.Column("checkin_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["daily_access_id"], ["customer_daily_accesses.id"], name=op.f("fk_access_qr_tokens_daily_access_id_customer_daily_accesses")),
        sa.ForeignKeyConstraint(["used_gym_id"], ["gyms.id"], name=op.f("fk_access_qr_tokens_used_gym_id_gyms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_qr_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_access_qr_tokens_token_hash")),
    )
    op.create_index("ix_access_qr_tokens_daily_access_id", "access_qr_tokens", ["daily_access_id"], unique=False)
    op.create_index("ix_access_qr_tokens_status", "access_qr_tokens", ["status"], unique=False)
    op.create_index("ix_access_qr_tokens_expires_at", "access_qr_tokens", ["expires_at"], unique=False)

    op.create_table(
        "checkins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("daily_access_id", sa.BigInteger(), nullable=False),
        sa.Column("qr_token_id", sa.BigInteger(), nullable=False),
        sa.Column("gym_id", sa.BigInteger(), nullable=False),
        sa.Column("checkin_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SUCCESS"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["daily_access_id"], ["customer_daily_accesses.id"], name=op.f("fk_checkins_daily_access_id_customer_daily_accesses")),
        sa.ForeignKeyConstraint(["gym_id"], ["gyms.id"], name=op.f("fk_checkins_gym_id_gyms")),
        sa.ForeignKeyConstraint(["qr_token_id"], ["access_qr_tokens.id"], name=op.f("fk_checkins_qr_token_id_access_qr_tokens")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_checkins_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkins")),
    )
    op.create_index("ix_checkins_user_id", "checkins", ["user_id"], unique=False)
    op.create_index("ix_checkins_daily_access_id", "checkins", ["daily_access_id"], unique=False)
    op.create_index("ix_checkins_gym_id", "checkins", ["gym_id"], unique=False)
    op.create_index("ix_checkins_checkin_time", "checkins", ["checkin_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_checkins_checkin_time", table_name="checkins")
    op.drop_index("ix_checkins_gym_id", table_name="checkins")
    op.drop_index("ix_checkins_daily_access_id", table_name="checkins")
    op.drop_index("ix_checkins_user_id", table_name="checkins")
    op.drop_table("checkins")

    op.drop_index("ix_access_qr_tokens_expires_at", table_name="access_qr_tokens")
    op.drop_index("ix_access_qr_tokens_status", table_name="access_qr_tokens")
    op.drop_index("ix_access_qr_tokens_daily_access_id", table_name="access_qr_tokens")
    op.drop_table("access_qr_tokens")

    op.drop_index("ix_customer_daily_accesses_status", table_name="customer_daily_accesses")
    op.drop_index("ix_customer_daily_accesses_access_date", table_name="customer_daily_accesses")
    op.drop_index("ix_customer_daily_accesses_user_id", table_name="customer_daily_accesses")
    op.drop_table("customer_daily_accesses")

    op.drop_index("ix_access_pause_days_access_date", table_name="access_pause_days")
    op.drop_index("ix_access_pause_days_user_id", table_name="access_pause_days")
    op.drop_table("access_pause_days")
