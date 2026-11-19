from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect


def test_projection_backfill_preserves_originals_and_skips_invalid(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/a13b4df67935_gym_geo_index.py'
    spec = spec_from_file_location('geo_migration', path); migration = module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE gyms (id INTEGER PRIMARY KEY, status VARCHAR(50), is_active BOOLEAN, latitude VARCHAR(50), longitude VARCHAR(50))'))
        connection.execute(text("INSERT INTO gyms VALUES (1,'APPROVED',1,'12.340000','77.5'),(2,'APPROVED',1,NULL,NULL),(3,'APPROVED',1,'NaN','0'),(4,'APPROVED',1,'91','0'),(5,'APPROVED',1,'0','0')"))
        original = connection.execute(text('SELECT id,latitude,longitude FROM gyms ORDER BY id')).all()
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert connection.execute(text('SELECT id,latitude,longitude FROM gyms ORDER BY id')).all() == original
        assert connection.execute(text('SELECT geo_latitude,geo_longitude FROM gyms ORDER BY id')).all() == [(12.34, 77.5), (None, None), (None, None), (None, None), (0, 0)]
        assert 'ix_gyms_discovery_geo' in {item['name'] for item in inspect(connection).get_indexes('gyms')}
        migration.downgrade()
        assert connection.execute(text('SELECT id,latitude,longitude FROM gyms ORDER BY id')).all() == original
    engine.dispose()