"""Exercise additive/resumable upgrade and guarded downgrade on disposable SQLite."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_account_migration_preserves_users_and_refuses_nonempty_downgrade():
    path = Path(__file__).parents[1]/'alembic/versions/bdf69ea12480_account_onboarding.py'
    spec = spec_from_file_location('account_migration', path)
    migration = module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash VARCHAR(255))'))
        connection.execute(text('CREATE TABLE gyms (id INTEGER PRIMARY KEY)'))
        connection.execute(text("INSERT INTO users VALUES (1, 'preserved')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade(); migration.upgrade()
        assert {'staff_invitations', 'account_otps'} <= set(inspect(connection).get_table_names())
        connection.execute(text("INSERT INTO account_otps (`key`, channel, purpose, nonce, code_hash, expires_at, attempts_left) VALUES ('fixture','email','LOGIN','nonce','hash','2026-01-01',5)"))
        with pytest.raises(RuntimeError, match='Archive'): migration.downgrade()
        assert connection.scalar(text('SELECT COUNT(*) FROM account_otps')) == 1
        # Explicit fixture-only archival; never performed by the migration.
        connection.execute(text('DELETE FROM account_otps'))
        migration.downgrade()
        assert 'staff_invitations' not in inspect(connection).get_table_names()
        assert connection.scalar(text('SELECT password_hash FROM users')) == 'preserved'
    engine.dispose()