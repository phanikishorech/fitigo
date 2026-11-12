"""Migration preservation, resumability and archive guards on isolated MySQL."""
import pytest
from alembic import command
from sqlalchemy import inspect, text
from test_phase4_migrations_mysql import schema


def test_operations_upgrade_roundtrip_and_archive_guards(schema):
    engine,config=schema
    command.upgrade(config,'cef70fb23591')
    with engine.begin() as c:
        c.execute(text("INSERT INTO users(id,email,password_hash,status,is_email_verified,is_phone_verified,token_version,created_at,updated_at) VALUES(1,'fixture@example.com','unchanged','ACTIVE',0,0,0,NOW(),NOW())"))
    command.upgrade(config,'head')
    with engine.connect() as c:assert {'operation_audits','photo_deletions'}<=set(inspect(c).get_table_names())
    command.downgrade(config,'cef70fb23591')
    command.upgrade(config,'head')
    with engine.begin() as c:
        assert c.scalar(text('SELECT password_hash FROM users'))=='unchanged'
        c.execute(text("INSERT INTO operation_audits(actor_id,action,resource_type,resource_id,reason_code,context,created_at) VALUES(1,'PROFILE_UPDATED','USER',1,'USER_REQUEST','{}',NOW())"))
    with pytest.raises(RuntimeError,match='Archive'):command.downgrade(config,'cef70fb23591')
    with engine.begin() as c:
        assert c.scalar(text('SELECT COUNT(*) FROM operation_audits'))==1
        c.execute(text('DELETE FROM operation_audits'))  # explicit isolated-fixture archival
        c.execute(text("INSERT INTO photo_deletions(image_id,gym_id,actor_id,file_path,storage_root,status,attempts,created_at) VALUES(1,1,1,'fixture','fixture','PENDING',0,NOW())"))
    with pytest.raises(RuntimeError,match='Archive'):command.downgrade(config,'cef70fb23591')
    with engine.connect() as c:assert c.scalar(text('SELECT COUNT(*) FROM photo_deletions'))==1


def test_partial_operational_ddl_can_resume(schema):
    engine,config=schema
    command.upgrade(config,'cef70fb23591')
    # Simulate nontransactional DDL completion before Alembic version advancement.
    from importlib.util import spec_from_file_location,module_from_spec
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    spec=spec_from_file_location('phase6',Path(__file__).parents[1]/'alembic/versions/df081ac34602_operational_workflows.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    with engine.begin() as c:
        module.op=Operations(MigrationContext.configure(c));module.upgrade();module.upgrade()
    command.upgrade(config,'df081ac34602')
    with engine.connect() as c:assert c.scalar(text('SELECT version_num FROM alembic_version'))=='df081ac34602'