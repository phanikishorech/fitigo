import pytest
from alembic import command
from sqlalchemy import text,inspect
from test_phase4_migrations_mysql import schema


def test_notification_migration_roundtrip_and_archival_guards(schema):
    engine,config=schema
    command.upgrade(config,'df081ac34602')
    with engine.begin() as c:
        c.execute(text("INSERT INTO users(id,email,password_hash,status,is_email_verified,is_phone_verified,token_version,created_at,updated_at) VALUES(1,'fixture@example.com','unchanged','ACTIVE',0,0,0,NOW(),NOW())"))
    command.upgrade(config,'head');command.downgrade(config,'df081ac34602');command.upgrade(config,'head')
    with engine.begin() as c:
        assert c.scalar(text('SELECT password_hash FROM users'))=='unchanged'
        c.execute(text('INSERT INTO notification_preferences(user_id,operational_email,updated_at) VALUES(1,0,NOW())'))
    with pytest.raises(RuntimeError,match='Archive'):command.downgrade(config,'df081ac34602')
    with engine.begin() as c:
        c.execute(text('DELETE FROM notification_preferences'))
        c.execute(text("INSERT INTO notification_events(id,user_id,event_type,status,payload_json,created_at) VALUES(1,1,'PASSWORD_CHANGED','RECORDED','{}',NOW())"))
        c.execute(text("INSERT INTO notification_deliveries(event_id,user_id,kind,category,resource_id,email_status,attempts,next_attempt_at,created_at) VALUES(1,1,'PASSWORD_CHANGED','SECURITY',1,'UNKNOWN',1,NOW(),NOW())"))
    with pytest.raises(RuntimeError,match='Archive'):command.downgrade(config,'df081ac34602')
    with engine.connect() as c:assert c.scalar(text('SELECT email_status FROM notification_deliveries'))=='UNKNOWN'