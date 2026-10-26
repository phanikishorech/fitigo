from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect, text


def test_payment_migration_upgrade_and_downgrade_on_disposable_database():
    path = Path(__file__).parents[1] / 'alembic/versions/8ad36b7c9e15_razorpay_checkout.py'
    spec = spec_from_file_location('gateway_migration', path)
    migration = module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    metadata = MetaData()
    for name in ['users', 'bookings', 'cart_items', 'user_memberships', 'platform_membership_orders']:
        Table(name, metadata, Column('id', Integer, primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text('INSERT INTO bookings (id) VALUES (1)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        inspector = inspect(connection)
        assert 'payment_checkouts' in inspector.get_table_names()
        assert 'payment_webhook_receipts' in inspector.get_table_names()
        assert 'checkout_id' in {column['name'] for column in inspector.get_columns('bookings')}
        assert connection.scalar(text('SELECT COUNT(*) FROM bookings')) == 1
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert 'payment_checkouts' not in inspect(connection).get_table_names()
        assert connection.scalar(text('SELECT COUNT(*) FROM bookings')) == 1
    engine.dispose()