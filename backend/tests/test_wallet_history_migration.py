from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


@pytest.mark.parametrize('partial', [False, True])
def test_wallet_migration_preserves_balances_and_blocks_history_loss(partial):
    path = Path(__file__).parents[1] / 'alembic/versions/acf58d9e1037_wallet_gateway_history.py'
    spec = spec_from_file_location('wallet_history_migration', path)
    migration = module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE payment_checkouts (id VARCHAR(36) PRIMARY KEY)'))
        db.execute(text('CREATE TABLE wallet_accounts (id INTEGER PRIMARY KEY, balance NUMERIC(12,2))'))
        db.execute(text('CREATE TABLE wallet_transactions (id INTEGER PRIMARY KEY, amount NUMERIC(12,2))'))
        db.execute(text('INSERT INTO wallet_accounts VALUES (1,123.45)'))
        db.execute(text('INSERT INTO wallet_transactions VALUES (1,123.45)'))
        if partial:
            # Reproduce MySQL's partial-DDL state after a constraint failure.
            db.execute(text('ALTER TABLE wallet_accounts ADD COLUMN payment_mode VARCHAR(10)'))
            db.execute(text('ALTER TABLE wallet_transactions ADD COLUMN checkout_id VARCHAR(36)'))
        with Operations.context(MigrationContext.configure(db)):
            migration.upgrade()
            migration.upgrade()  # Completed migration is also safe to resume.
            assert float(db.scalar(text('SELECT balance FROM wallet_accounts'))) == 123.45
            assert db.scalar(text('SELECT payment_mode FROM wallet_accounts')) is None
            assert 'payment_attempts' in inspect(db).get_table_names()
            db.execute(text("INSERT INTO payment_attempts VALUES ('attempt','checkout','payment','SUCCESS',10,'INR',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            with pytest.raises(RuntimeError):
                migration.downgrade()
            db.execute(text('DELETE FROM payment_attempts'))
            migration.downgrade()
            assert 'payment_attempts' not in inspect(db).get_table_names()
            assert float(db.scalar(text('SELECT balance FROM wallet_accounts'))) == 123.45