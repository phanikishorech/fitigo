"""The disposable runner migrated this schema; validate actual MySQL DDL/guards."""
from pathlib import Path
from importlib.util import module_from_spec,spec_from_file_location
import pytest
from sqlalchemy import inspect,text
from app.database.session import engine
from test_database_guard import disposable_name


def test_monthly_forward_migration_has_guards_and_no_working_deployment():
    # Guard proves an isolated run namespace, never accepts the working database.
    assert engine.url.database.startswith('fitigo_test_')
    disposable_name()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) in {'da2e6f105824','eb3f70126935'}
        inspector=inspect(connection)
        for table in ('gym_monthly_calculations','membership_visit_fees'):
            assert inspector.has_table(table)
            assert connection.scalar(text(f'SELECT COUNT(*) FROM {table}'))==0
            names={row[0] for row in connection.execute(text('SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE=:table'),{'table':table})}
            assert names=={table+'_no_update',table+'_no_delete'}
        cap=next(c for c in inspector.get_columns('gym_visit_payouts') if c['name']=='applied_cap')
        assert cap['nullable'] is True
    path=Path(__file__).resolve().parents[1]/'alembic/versions/da2e6f105824_monthly_visit_completion.py'
    spec=spec_from_file_location('monthly_forward',path);module=module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(RuntimeError,match='Forward-only'):module.downgrade()