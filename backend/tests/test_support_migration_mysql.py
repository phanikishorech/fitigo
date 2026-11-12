import pytest
from alembic import command
from sqlalchemy import text, inspect
from test_phase4_migrations_mysql import schema


def test_support_migration_roundtrip_preserves_users_and_refuses_history_loss(schema):
    engine, config = schema
    command.upgrade(config, 'ef192bd45713')
    with engine.begin() as c:
        c.execute(text("INSERT INTO users(id,email,password_hash,status,is_email_verified,is_phone_verified,token_version,created_at,updated_at) VALUES(1,'fixture@example.com','unchanged','ACTIVE',0,0,0,NOW(),NOW())"))
    command.upgrade(config, 'head'); command.downgrade(config, 'ef192bd45713'); command.upgrade(config, 'head')
    with engine.begin() as c:
        assert c.scalar(text('SELECT password_hash FROM users')) == 'unchanged'
        c.execute(text("INSERT INTO support_tickets(id,user_id,request_key,category,subject,status,version,created_at,updated_at) VALUES(1,1,'fixture-key','OTHER','Fixture','OPEN',1,NOW(),NOW())"))
        c.execute(text("INSERT INTO support_messages(ticket_id,author_id,author_kind,request_key,body,created_at) VALUES(1,1,'REQUESTER','fixture-key','Retain history',NOW())"))
    with pytest.raises(RuntimeError, match='Archive'): command.downgrade(config, 'ef192bd45713')
    with engine.connect() as c:
        assert c.scalar(text('SELECT body FROM support_messages')) == 'Retain history'
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == 'f02a3ce56824'


def test_support_ddl_resume_before_revision_advance(schema):
    from pathlib import Path
    from importlib.util import module_from_spec, spec_from_file_location
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    engine, config = schema
    command.upgrade(config, 'ef192bd45713')
    path = Path(__file__).parents[1] / 'alembic/versions/f02a3ce56824_support_threads.py'
    spec = spec_from_file_location('support_migration', path)
    module = module_from_spec(spec); spec.loader.exec_module(module)
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade(); module.upgrade()
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == 'f02a3ce56824'
        assert len(inspect(connection).get_unique_constraints('support_messages')) == 1