"""Run tests on a NEW local MySQL instance; never reads application .env.

Usage: python scripts/run_isolated_tests.py --mysql-bin <mysqld.exe> [pytest args]
Data directory is retained privately for diagnostics; the owned server is stopped.
No account, schema or setting on an existing MySQL server is changed.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import pymysql
from sqlalchemy.engine import URL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mysql-bin', required=True)
    parser.add_argument('--operational', action='store_true', help='Exercise Phase 6 audit/deletion with migrated isolated schema')
    parser.add_argument('--notifications', action='store_true', help='Exercise notification inbox/outbox on isolated data; no sender enabled')
    parser.add_argument('--support', action='store_true', help='Exercise support workflows; also enables transactional audit on isolated data')
    parser.add_argument('--test-timeout', type=int, default=900, help='Bounded pytest timeout in seconds (60..3600)')
    options, tests = parser.parse_known_args()
    if not 60 <= options.test_timeout <= 3600: parser.error('test-timeout must be 60..3600')
    binary = Path(options.mysql_bin).resolve()
    if not binary.is_file():
        parser.error('MySQL server binary not found')
    root = Path(__file__).resolve().parents[1]
    run = secrets.token_hex(8)
    directory = Path(tempfile.mkdtemp(prefix='fitigo-isolated-'+run+'-'))
    datadir = directory/'data'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    if port == 3306:
        raise RuntimeError('Refusing standard database port')
    name = f'fitigo_test_{run}_main'
    password, root_password = secrets.token_hex(32), secrets.token_hex(32)
    init = directory/'initialize.sql'
    # Restricted to this run's namespace on an entirely new instance. Passwords
    # are generated, never supplied on a process command line or printed.
    init.write_text(
        f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_password}';\n"
        f"CREATE USER 'fitigo_test'@'localhost' IDENTIFIED BY '{password}';\n"
        f"GRANT ALL PRIVILEGES ON `fitigo_test_{run}_%`.* TO 'fitigo_test'@'localhost';\n",
        encoding='utf-8')
    server = None
    try:
        with (directory/'initialization.log').open('w') as output:
            result = subprocess.run([str(binary), '--no-defaults', '--initialize-insecure',
                '--basedir='+str(binary.parent.parent), '--datadir='+str(datadir)],
                stdout=output, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise RuntimeError('Disposable server initialization failed; see private initialization log.')
        with (directory/'server.log').open('w') as output:
            server = subprocess.Popen([str(binary), '--no-defaults', '--console',
                '--basedir='+str(binary.parent.parent), '--datadir='+str(datadir),
                '--bind-address=127.0.0.1', f'--port={port}', '--mysqlx=0', '--skip-log-bin',
                '--innodb-buffer-pool-size=64M', '--init-file='+str(init)], stdout=output, stderr=subprocess.STDOUT)
        connection = None
        for _ in range(90):
            if server.poll() is not None: break
            try:
                connection = pymysql.connect(host='127.0.0.1', port=port, user='root', password=root_password, autocommit=True)
                break
            except pymysql.MySQLError:
                time.sleep(1)
        if connection is None:
            raise RuntimeError('Disposable server did not become ready; see private server log.')
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT @@datadir, @@port, VERSION()')
                actual, actual_port, version = cursor.fetchone()
                if Path(actual).resolve() != datadir.resolve() or actual_port != port:
                    raise RuntimeError('Server ownership mismatch; refusing schema creation.')
                cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        init.unlink()
        url = URL.create('mysql+pymysql', username='fitigo_test', password=password, host='127.0.0.1', port=port, database=name).render_as_string(hide_password=False)
        # Deliberate environment allowlist: inherited application/provider secrets
        # and DATABASE_URL never enter the test child.
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'COMSPEC'}}
        env.update(DATABASE_URL=url, FITIGO_TEST_DATABASE_URL=url, FITIGO_TEST_DATABASE_NAME=name,
            FITIGO_TEST_RUN_ID=run, FITIGO_TEST_BOOTSTRAPPED='1', JWT_SECRET=secrets.token_urlsafe(64),
            JWT_ALGORITHM='HS256', ENVIRONMENT='development', EMAIL_PROVIDER='disabled', SMS_PROVIDER='disabled',
            PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONPATH=str(root))
        for flag in ['PAYMENT', 'DASHBOARD', 'BOOKING_QR', 'WALLET', 'ACCOUNT', 'PHASE4']:
            env[f'FITIGO_MYSQL_{flag}_TESTS'] = '1'
        env['OPERATIONAL_WORKFLOWS_ENABLED'] = 'true' if options.operational or options.support else 'false'
        env['SUPPORT_WORKFLOWS_ENABLED'] = 'true' if options.support else 'false'
        env['NOTIFICATION_WORKFLOWS_ENABLED'] = 'true' if options.notifications else 'false'
        env['NOTIFICATION_EMAIL_ENABLED'] = 'false'
        print('Isolated MySQL', version, 'test schema', name, 'artifacts', directory, flush=True)
        with (directory/'migration.log').open('w', encoding='utf-8') as output:
            result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=root, env=env,
                stdout=output, stderr=subprocess.STDOUT, timeout=120)
        if result.returncode:
            raise RuntimeError('Isolated migration failed; working database was not contacted.')
        with (directory/'pytest.log').open('w', encoding='utf-8') as output:
            result = subprocess.run([sys.executable, '-m', 'pytest', *tests, '--junitxml='+str(directory/'results.xml')],
                cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=options.test_timeout)
        summary = {'pytest_exit': result.returncode, 'run_id': run, 'database': name, 'mysql_version': version}
        (directory/'summary.json').write_text(json.dumps(summary, indent=2))
        print('Pytest exit:', result.returncode, 'private log:', directory/'pytest.log', flush=True)
        return result.returncode
    finally:
        # Windows MySQL may launch a child: terminate() of the launcher alone
        # is insufficient. Shut down only the server whose datadir we own.
        if server:
            try:
                with pymysql.connect(host='127.0.0.1', port=port, user='root', password=root_password,
                                     autocommit=True, connect_timeout=3) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT @@datadir')
                        if Path(cursor.fetchone()[0]).resolve() != datadir.resolve():
                            raise RuntimeError('Refusing shutdown of an unowned server')
                        cursor.execute('SHUTDOWN')
            except pymysql.MySQLError:
                pass  # Startup may have failed before authentication was ready.
        if server and server.poll() is None:
            try: server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                else: server.terminate()
                server.wait(timeout=15)
        if init.exists(): init.unlink()
        # No broad deletion: retain only the unique private directory for review.
        print('Owned isolated server stopped; private directory retained:', directory, flush=True)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        # Do not render driver/subprocess objects that could contain credentials.
        print('Isolated test runner failed:', type(error).__name__, file=sys.stderr)
        sys.exit(2)