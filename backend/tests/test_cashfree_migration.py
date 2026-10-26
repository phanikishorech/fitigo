from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_cashfree_migration_preserves_existing_rows_and_blocks_destructive_downgrade():
    path = Path(__file__).parents[1] / 'alembic/versions/9be47c8d0f26_cashfree_provider.py'
    spec = spec_from_file_location('cashfree_migration', path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE payment_checkouts (id VARCHAR(36) PRIMARY KEY, amount NUMERIC(12,2))'))
        db.execute(text("INSERT INTO payment_checkouts VALUES ('existing',123.45)"))
        with Operations.context(MigrationContext.configure(db)):
            migration.upgrade()
            assert db.scalar(text("SELECT provider FROM payment_checkouts WHERE id='existing'")) == 'RAZORPAY'
            assert float(db.scalar(text('SELECT amount FROM payment_checkouts'))) == 123.45
            db.execute(text("INSERT INTO payment_checkouts(id,amount,provider) VALUES ('new',100,'CASHFREE')"))
            with pytest.raises(RuntimeError):
                migration.downgrade()
            db.execute(text("DELETE FROM payment_checkouts WHERE id='new'"))
            migration.downgrade()
        assert 'provider' not in {c['name'] for c in inspect(db).get_columns('payment_checkouts')}
        assert db.scalar(text('SELECT COUNT(*) FROM payment_checkouts')) == 1