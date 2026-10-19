from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, inspect, text


@pytest.mark.parametrize("partial", [False, True])
def test_booking_access_upgrade_preserves_old_records_and_downgrades(partial):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/7fc25a6b8d04_booking_access_qr.py"
    spec = spec_from_file_location("booking_access_migration", path)
    migration = module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("user_memberships", metadata, Column("id", Integer, primary_key=True))
    Table("bookings", metadata, Column("id", Integer, primary_key=True), Column("total_price", Integer), Column("notes", String))
    Table("payments", metadata, Column("id", Integer, primary_key=True), Column("booking_id", Integer), Column("provider", String))
    Table("cart_items", metadata, Column("id", Integer, primary_key=True))
    Table("customer_daily_accesses", metadata, Column("id", Integer, primary_key=True), Column("membership_id", Integer))
    Table("access_qr_tokens", metadata, Column("id", Integer, primary_key=True), Column("daily_access_id", Integer, ForeignKey("customer_daily_accesses.id"), nullable=False))
    Table("checkins", metadata, Column("id", Integer, primary_key=True), Column("daily_access_id", Integer, nullable=False))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO user_memberships VALUES (7)"))
        connection.execute(text("INSERT INTO customer_daily_accesses VALUES (1, 7)"))
        connection.execute(text("INSERT INTO access_qr_tokens VALUES (1, 1)"))
        connection.execute(text("INSERT INTO checkins VALUES (1, 1)"))
        connection.execute(text("INSERT INTO bookings VALUES (1, 0, 'access_type_id=GYM_ACCESS'), (2, 0, 'access_type_id=DAY_PASS'), (3, 0, 'access_type_id=GYM_ACCESS')"))
        connection.execute(text("INSERT INTO payments VALUES (1, 1, 'DUMMY'), (2, 2, 'DUMMY'), (3, 3, 'WALLET')"))
        if partial:
            connection.execute(text("ALTER TABLE bookings ADD visitor_names JSON"))
            connection.execute(text("ALTER TABLE cart_items ADD visitor_names JSON"))
            connection.execute(text("ALTER TABLE access_qr_tokens ADD booking_id BIGINT"))
        # SQLite allows a deliberately corrupt reference while FK enforcement is
        # off. Preflight must refuse it without making ANY further schema changes.
        connection.execute(text("INSERT INTO access_qr_tokens VALUES (2, 999" + (", NULL)" if partial else ")")))
        before = {table: [c["name"] for c in inspect(connection).get_columns(table)]
                  for table in ("bookings", "cart_items", "access_qr_tokens", "checkins")}
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="orphaned reference"):
                migration.upgrade()
        assert before == {table: [c["name"] for c in inspect(connection).get_columns(table)] for table in before}
        connection.execute(text("DELETE FROM access_qr_tokens WHERE id = 2"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # interrupted run after constraints were committed
        assert connection.execute(text("SELECT access_source, membership_id FROM checkins")).one() == ("MEMBERSHIP_ACCESS", 7)
        assert list(connection.execute(text("SELECT access_source FROM bookings ORDER BY id")).scalars()) == ["MEMBERSHIP_ACCESS", "BOOKING_ACCESS", "BOOKING_ACCESS"]
        columns = {col["name"]: col for col in inspect(connection).get_columns("access_qr_tokens")}
        assert columns["daily_access_id"]["nullable"] and "booking_id" in columns
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.execute(text("SELECT daily_access_id FROM checkins")).scalar_one() == 1
        assert "booking_id" not in {col["name"] for col in inspect(connection).get_columns("access_qr_tokens")}
    engine.dispose()