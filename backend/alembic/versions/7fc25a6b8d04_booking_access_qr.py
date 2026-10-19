"""Extend existing QR and check-in records with booking visitor access."""
from alembic import op
import sqlalchemy as sa

revision = "7fc25a6b8d04"
down_revision = "6eb14f5a7c93"
branch_labels = None
depends_on = None


def _columns(table):
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_columns(table, columns):
    existing = _columns(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _preflight():
    """Fail before DDL if existing references cannot survive MySQL table rebuilds.

    Do not delete, invent, or silently detach historical access data in a migration.
    Recovery requires a backup and an explicit decision about the invalid records.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    quote = bind.dialect.identifier_preparer.quote
    for table in ("access_qr_tokens", "checkins", "customer_daily_accesses"):
        for foreign_key in inspector.get_foreign_keys(table):
            child_columns = foreign_key["constrained_columns"]
            parent_columns = foreign_key["referred_columns"]
            join = " AND ".join(f"child.{quote(child)} = parent.{quote(parent)}"
                                for child, parent in zip(child_columns, parent_columns))
            present = " AND ".join(f"child.{quote(column)} IS NOT NULL" for column in child_columns)
            count = bind.scalar(sa.text(
                f"SELECT COUNT(*) FROM {quote(table)} child "
                f"LEFT JOIN {quote(foreign_key['referred_table'])} parent ON {join} "
                f"WHERE {present} AND parent.{quote(parent_columns[0])} IS NULL"
            ))
            if count:
                raise RuntimeError(
                    f"Booking QR migration blocked: {count} orphaned reference(s) in "
                    f"{table}.{','.join(child_columns)}. Back up and reconcile these records "
                    "before retrying. No foreign-key checks have been disabled."
                )


def upgrade():
    _preflight()
    # MySQL commits each DDL operation. Inspect before adding so a failed upgrade
    # can resume without duplicate-column errors or falsely stamping completion.
    for table in ("bookings", "cart_items"):
        _add_columns(table, [sa.Column("visitor_names", sa.JSON(), nullable=True)])
    _add_columns("bookings", [sa.Column("access_source", sa.String(30), nullable=False, server_default="BOOKING_ACCESS")])
    # Legacy membership-covered access-bookings explicitly recorded their access type
    # in notes and used DUMMY settlement. Free WALLET visits are still bookings.
    op.execute("UPDATE bookings SET access_source = 'MEMBERSHIP_ACCESS' WHERE total_price = 0 AND notes LIKE '%access_type_id=%' AND notes NOT LIKE '%access_type_id=DAY_PASS%' AND id IN (SELECT booking_id FROM payments WHERE provider = 'DUMMY')")
    _add_columns("access_qr_tokens", [
        sa.Column("booking_id", sa.BigInteger(), nullable=True),
        sa.Column("visitor_index", sa.Integer(), nullable=True),
        sa.Column("visitor_name", sa.String(150), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
    ])
    inspector = sa.inspect(op.get_bind())
    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("access_qr_tokens")}
    uniques = {key["name"] for key in inspector.get_unique_constraints("access_qr_tokens")}
    checks = {key["name"] for key in inspector.get_check_constraints("access_qr_tokens")}
    with op.batch_alter_table("access_qr_tokens") as batch:
        if not _columns("access_qr_tokens")["daily_access_id"]["nullable"]:
            batch.alter_column("daily_access_id", existing_type=sa.BigInteger(), nullable=True)
        if "fk_access_qr_booking" not in foreign_keys:
            batch.create_foreign_key("fk_access_qr_booking", "bookings", ["booking_id"], ["id"])
        if "uq_access_qr_booking_visitor" not in uniques:
            batch.create_unique_constraint("uq_access_qr_booking_visitor", ["booking_id", "visitor_index"])
        if not checks.intersection({"qr_one_source", "ck_access_qr_tokens_qr_one_source"}):
            batch.create_check_constraint("qr_one_source", "(daily_access_id IS NOT NULL AND booking_id IS NULL) OR (daily_access_id IS NULL AND booking_id IS NOT NULL)")
    _add_columns("checkins", [
        sa.Column("access_source", sa.String(30), nullable=False, server_default="MEMBERSHIP_ACCESS"),
        sa.Column("booking_id", sa.BigInteger(), nullable=True),
        sa.Column("membership_id", sa.BigInteger(), nullable=True),
        sa.Column("visitor_index", sa.Integer(), nullable=True),
        sa.Column("visitor_name", sa.String(150), nullable=True),
        sa.Column("scanned_by", sa.BigInteger(), nullable=True),
    ])
    inspector = sa.inspect(op.get_bind())
    foreign_keys = {key["name"] for key in inspector.get_foreign_keys("checkins")}
    uniques = {key["name"] for key in inspector.get_unique_constraints("checkins")}
    with op.batch_alter_table("checkins") as batch:
        if not _columns("checkins")["daily_access_id"]["nullable"]:
            batch.alter_column("daily_access_id", existing_type=sa.BigInteger(), nullable=True)
        for name, parent, column in (
            ("fk_checkins_booking", "bookings", "booking_id"),
            ("fk_checkins_membership", "user_memberships", "membership_id"),
            ("fk_checkins_scanned_by", "users", "scanned_by"),
        ):
            if name not in foreign_keys:
                batch.create_foreign_key(name, parent, [column], ["id"])
        if "uq_checkins_booking_visitor" not in uniques:
            batch.create_unique_constraint("uq_checkins_booking_visitor", ["booking_id", "visitor_index"])
    op.execute("UPDATE checkins SET membership_id = (SELECT membership_id FROM customer_daily_accesses WHERE customer_daily_accesses.id = checkins.daily_access_id) WHERE membership_id IS NULL AND daily_access_id IS NOT NULL")


def downgrade():
    # Never silently delete admission history to satisfy the old NOT NULL columns.
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM access_qr_tokens WHERE booking_id IS NOT NULL")):
        raise RuntimeError("Booking access exists; archive it explicitly before downgrading.")
    with op.batch_alter_table("checkins") as batch:
        for name in ("fk_checkins_booking", "fk_checkins_membership", "fk_checkins_scanned_by"):
            batch.drop_constraint(name, type_="foreignkey")
        batch.drop_constraint("uq_checkins_booking_visitor", type_="unique")
        for name in ("access_source", "booking_id", "membership_id", "visitor_index", "visitor_name", "scanned_by"):
            batch.drop_column(name)
        batch.alter_column("daily_access_id", existing_type=sa.BigInteger(), nullable=False)
    with op.batch_alter_table("access_qr_tokens") as batch:
        batch.drop_constraint("qr_one_source", type_="check")
        batch.drop_constraint("fk_access_qr_booking", type_="foreignkey")
        batch.drop_constraint("uq_access_qr_booking_visitor", type_="unique")
        for name in ("booking_id", "visitor_index", "visitor_name", "valid_from"):
            batch.drop_column(name)
        batch.alter_column("daily_access_id", existing_type=sa.BigInteger(), nullable=False)
    for table in ("bookings", "cart_items"):
        op.drop_column(table, "visitor_names")
    op.drop_column("bookings", "access_source")