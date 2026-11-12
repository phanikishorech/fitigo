"""Safety validation never opens the supplied unsafe URL."""
import os
import subprocess
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from test_database_guard import configuration, UnsafeTestDatabase, disposable_name


@pytest.mark.parametrize('change', ['missing', 'empty-run', 'working-name', 'working-url', 'root', 'standard-port', 'query'])
def test_invalid_configuration_fails_before_connection(change):
    env = dict(os.environ)
    if change == 'missing': env.pop('FITIGO_TEST_DATABASE_URL')
    if change == 'empty-run': env['FITIGO_TEST_RUN_ID'] = ''
    if change == 'working-name': env['FITIGO_TEST_DATABASE_NAME'] = 'dev_fitigo'
    if change == 'working-url': env['DATABASE_URL'] = 'mysql+pymysql://unused@localhost/fitigo'
    if change in {'root', 'standard-port', 'query'}:
        from sqlalchemy.engine import make_url
        url = make_url(env['DATABASE_URL'])
        if change == 'root': url = url.set(username='root')
        if change == 'standard-port': url = url.set(port=3306)
        if change == 'query': url = url.update_query_dict({'read_default_file': 'unsafe.ini'})
        env['DATABASE_URL'] = env['FITIGO_TEST_DATABASE_URL'] = url.render_as_string(hide_password=False)
    with pytest.raises(UnsafeTestDatabase): configuration(env)


def test_late_import_bootstrap_and_plain_pytest_fail_in_subprocess():
    root = Path(__file__).parents[1]
    env = dict(os.environ)
    script = "import sys; sys.modules['app.database.session']=object(); from test_database_guard import bootstrap; bootstrap()"
    result = subprocess.run([sys.executable, '-c', script], cwd=root, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0 and 'Application loaded before test isolation' in result.stderr
    for key in ['FITIGO_TEST_DATABASE_URL', 'FITIGO_TEST_RUN_ID', 'FITIGO_TEST_DATABASE_NAME', 'FITIGO_TEST_BOOTSTRAPPED']:
        env.pop(key, None)
    result = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q'], cwd=root, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'Tests require the isolated runner' in result.stderr


def test_connection_boundary_blocks_working_database_and_overrides(tmp_path):
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    engines = [create_engine('mysql+pymysql://unused@127.0.0.1:3306/fitigo'),
               create_engine(url._replace(port=None)),
               create_engine(url.set(database='dev_fitigo')),
               create_engine(url, connect_args={'port': 3306}),
               create_engine('sqlite:///'+str(tmp_path/'not-memory.sqlite'))]
    for engine in engines:
        try:
            with pytest.raises(UnsafeTestDatabase): engine.connect()
        finally: engine.dispose()
    assert not (tmp_path/'not-memory.sqlite').exists()


def test_valid_bootstrap_has_no_application_dotenv_fallback():
    from app.core.config import settings
    _, approved = configuration()
    assert settings.database_url == approved.render_as_string(hide_password=False)
    assert disposable_name().startswith('fitigo_test_'+os.environ['FITIGO_TEST_RUN_ID']+'_')
    assert not settings.cashfree_client_id and not settings.smtp_host