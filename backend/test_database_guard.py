"""Test-only bootstrap. No application imports, credentials or dotenv fallback."""
import os
import re
import sys
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url


class UnsafeTestDatabase(RuntimeError):
    pass


def configuration(environ=None):
    env = os.environ if environ is None else environ
    run = env.get('FITIGO_TEST_RUN_ID', '')
    name = env.get('FITIGO_TEST_DATABASE_NAME', '')
    raw = env.get('FITIGO_TEST_DATABASE_URL', '')
    if not re.fullmatch(r'[a-f0-9]{16}', run) or name != f'fitigo_test_{run}_main' or not raw:
        raise UnsafeTestDatabase('Tests require the isolated runner; no database connection was attempted.')
    try:
        url = make_url(raw)
    except Exception:
        raise UnsafeTestDatabase('Invalid isolated test configuration.') from None
    if (url.drivername != 'mysql+pymysql' or url.host != '127.0.0.1' or not url.port or url.port == 3306
            or url.database != name or url.username != 'fitigo_test' or not url.password
            or url.query or env.get('DATABASE_URL') != raw):
        raise UnsafeTestDatabase('Test database does not match the isolated run; refusing to connect.')
    return run, url


def validate_connection(url, params, run, approved):
    if url.get_backend_name() == 'sqlite':
        if url.database not in (None, '', ':memory:'):
            raise UnsafeTestDatabase('Only in-memory SQLite is allowed in tests.')
        return
    db = params.get('database', params.get('db', url.database))
    if (url.drivername != approved.drivername or url.host != approved.host or url.port != approved.port
            or url.username != approved.username or url.password != approved.password or url.query
            or params.get('host') != approved.host or params.get('port') != approved.port
            or params.get('user') != approved.username
            or params.get('password', params.get('passwd')) != approved.password
            or params.get('unix_socket') or params.get('read_default_file')
            or (db and not re.fullmatch(rf'fitigo_test_{run}_(?:main|[a-f0-9]{{12}})', db))):
        raise UnsafeTestDatabase('Database connection outside the isolated test run was blocked.')


def bootstrap():
    if any(name in sys.modules for name in ('app.core.config', 'app.database.session')):
        raise UnsafeTestDatabase('Application loaded before test isolation. Start a fresh isolated runner.')
    run, approved = configuration()
    os.environ['FITIGO_TEST_BOOTSTRAPPED'] = '1'

    @event.listens_for(Engine, 'do_connect')
    def guard(dialect, connection_record, args, params):
        # Check the final driver arguments, including connect_args overrides,
        # before a socket/file is opened. This complements runner isolation.
        if dialect.name == 'sqlite':
            if args and args[0] != ':memory:':
                raise UnsafeTestDatabase('Only in-memory SQLite is allowed in tests.')
            return
        if dialect.name != 'mysql' or dialect.driver != 'pymysql':
            raise UnsafeTestDatabase('Unexpected test database driver was blocked.')
        if args:
            raise UnsafeTestDatabase('Unexpected positional database connection arguments were blocked.')
        candidate = approved.set(database=params.get('database', params.get('db')))
        validate_connection(candidate, params, run, approved)


def disposable_name():
    from uuid import uuid4
    run, _ = configuration()
    return f'fitigo_test_{run}_{uuid4().hex[:12]}'