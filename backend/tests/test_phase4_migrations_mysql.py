"""Real migrations, legacy rows and guards on runner-owned disposable MySQL."""
import logging
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.database.session import engine as application_engine
from test_database_guard import disposable_name


@pytest.fixture
def schema(monkeypatch):
    name = disposable_name()
    control = create_engine(application_engine.url.set(database=None), isolation_level='AUTOCOMMIT')
    engine = None
    created = False
    try:
        with control.connect() as c:
            c.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')); created = True
        engine = create_engine(application_engine.url.set(database=name))
        config = Config(str(Path(__file__).parents[1]/'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).parents[1]/'alembic'))
        monkeypatch.setattr(settings, 'database_url', engine.url.render_as_string(hide_password=False))
        yield engine, config
    finally:
        if engine is not None: engine.dispose()
        if created:
            with control.connect() as c: c.execute(text(f'DROP DATABASE `{name}`'))
        control.dispose()


def test_wallet_mysql_roundtrip_preserves_legacy_rows_and_logging(schema, caplog):
    engine, config = schema
    handlers = list(logging.getLogger().handlers)
    command.upgrade(config, '9be47c8d0f26')
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,password_hash,status,is_email_verified,is_phone_verified,token_version,created_at,updated_at) VALUES (1,'fixture@example.com','unchanged','ACTIVE',0,0,0,NOW(),NOW())"))
        c.execute(text("INSERT INTO wallet_accounts (id,user_id,balance,currency,created_at,updated_at) VALUES (1,1,123.45,'INR',NOW(),NOW())"))
        c.execute(text("INSERT INTO wallet_transactions (id,account_id,user_id,direction,txn_type,amount,currency,created_at) VALUES (1,1,1,'IN','TOPUP',123.45,'INR',NOW())"))
        before = c.execute(text('SELECT * FROM wallet_transactions')).all()
    command.upgrade(config, 'acf58d9e1037')
    with engine.connect() as c:
        assert 'fk_wallet_transaction_checkout' in {f['name'] for f in inspect(c).get_foreign_keys('wallet_transactions')}
    command.downgrade(config, '9be47c8d0f26')
    with engine.connect() as c:
        assert c.execute(text('SELECT * FROM wallet_transactions')).all() == before
        assert str(c.scalar(text('SELECT balance FROM wallet_accounts'))) == '123.45'
        assert 'checkout_id' not in {col['name'] for col in inspect(c).get_columns('wallet_transactions')}
    command.upgrade(config, 'acf58d9e1037')
    with engine.begin() as c: c.execute(text("UPDATE wallet_accounts SET payment_mode='test'"))
    with pytest.raises(RuntimeError, match='payment-mode'): command.downgrade(config, '9be47c8d0f26')
    with engine.connect() as c:
        assert c.scalar(text('SELECT payment_mode FROM wallet_accounts')) == 'test'
        assert inspect(c).has_table('payment_attempts')
    assert logging.getLogger().handlers == handlers
    with caplog.at_level(logging.ERROR, logger='fitigo.errors'):
        logging.getLogger('fitigo.errors').error('migration-safe-fixture-event')
    assert 'migration-safe-fixture-event' in caplog.text


def test_class_mysql_roundtrip_no_guessed_links_and_no_history_loss(schema):
    engine, config = schema
    command.upgrade(config, 'bdf69ea12480')
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,password_hash,status,is_email_verified,is_phone_verified,token_version,created_at,updated_at) VALUES (1,'fixture@example.com','unchanged','ACTIVE',0,0,0,NOW(),NOW())"))
        c.execute(text("INSERT INTO gyms (id,owner_user_id,name,status,is_active,created_at,updated_at) VALUES (1,1,'Legacy gym','APPROVED',1,NOW(),NOW())"))
        c.execute(text("INSERT INTO gym_slots (id,gym_id,name,start_time,end_time,capacity,price,is_active,created_at,updated_at) VALUES (1,1,'Legacy','10:00','11:00',10,100,1,NOW(),NOW())"))
    command.upgrade(config, 'head')
    with engine.connect() as c:
        assert c.scalar(text('SELECT sync_kind FROM gym_slots')) == 'LEGACY'
        assert 'source_slot_id' in {col['name'] for col in inspect(c).get_columns('class_sessions')}
    command.downgrade(config, 'bdf69ea12480')
    with engine.connect() as c:
        assert c.scalar(text('SELECT name FROM gym_slots')) == 'Legacy'
        assert 'sync_kind' not in {col['name'] for col in inspect(c).get_columns('gym_slots')}
    command.upgrade(config, 'head')
    with engine.begin() as c: c.execute(text("UPDATE gym_slots SET sync_kind='CLASS'"))
    with pytest.raises(RuntimeError, match='slot provenance'): command.downgrade(config, 'bdf69ea12480')
    with engine.connect() as c: assert c.scalar(text('SELECT sync_kind FROM gym_slots')) == 'CLASS'
    with engine.begin() as c:
        c.execute(text("UPDATE gym_slots SET sync_kind='LEGACY'"))
        c.execute(text("INSERT INTO gym_classes (id,gym_id,class_name,is_active,created_at,updated_at) VALUES (1,1,'History',1,NOW(),NOW())"))
        c.execute(text("INSERT INTO class_sessions (id,gym_class_id,source_slot_id,session_date,start_time,end_time,maximum_capacity,booked_capacity,price_per_person,status,created_at,updated_at) VALUES (1,1,1,'2026-01-01','10:00','11:00',10,2,100,'CLOSED',NOW(),NOW())"))
    with pytest.raises(RuntimeError, match='class-session provenance'): command.downgrade(config, 'bdf69ea12480')
    with engine.connect() as c:
        assert c.execute(text('SELECT source_slot_id,booked_capacity FROM class_sessions')).one() == (1,2)