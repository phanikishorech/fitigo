"""Signing configuration/startup tests; no database or external service access."""
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from jose import JWTError
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.security import create_access_token, decode_token


@pytest.mark.parametrize('environment', ['production', 'staging', 'development', 'test', 'PRODUCTION'])
@pytest.mark.parametrize('secret', ['', ' ', 'CHANGE_ME', 'secret', 'a' * 80,
                                    'replace-with-your-secret-' * 4])
def test_insecure_secrets_rejected_in_every_environment(environment, secret):
    config = Settings(_env_file=None, environment=environment, jwt_secret=secret)
    with pytest.raises(RuntimeError, match='JWT_SECRET is missing or insecure') as error:
        config.validate_security()
    assert str(error.value) == (
        'JWT_SECRET is missing or insecure. Configure an independently generated random signing secret '
        'of at least 32 bytes for HS256, 48 for HS384 or 64 for HS512; placeholders are not allowed.'
    )


def test_missing_production_secret_has_no_default(monkeypatch):
    monkeypatch.delenv('JWT_SECRET', raising=False)
    config = Settings(_env_file=None, environment='production')
    with pytest.raises(RuntimeError, match='JWT_SECRET'):
        config.validate_security()


@pytest.mark.parametrize('algorithm,size', [('HS256', 32), ('HS384', 48), ('HS512', 64)])
def test_strong_config_and_same_key_instances_preserve_sessions(monkeypatch, algorithm, size):
    secret = secrets.token_urlsafe(64)[:size]
    first = Settings(_env_file=None, environment='production', jwt_secret=secret, jwt_algorithm=algorithm)
    second = Settings(_env_file=None, environment='production', jwt_secret=secret, jwt_algorithm=algorithm)
    first.validate_security(); second.validate_security()
    assert secret not in repr(first) and secret not in first.model_dump_json()
    monkeypatch.setattr(settings, 'jwt_secret', first.jwt_secret)
    monkeypatch.setattr(settings, 'jwt_algorithm', first.jwt_algorithm)
    token = create_access_token('1')
    monkeypatch.setattr(settings, 'jwt_secret', second.jwt_secret)
    assert decode_token(token)['sub'] == '1'
    monkeypatch.setattr(settings, 'jwt_secret', SecretStr(secrets.token_urlsafe(64)))
    with pytest.raises(JWTError):
        decode_token(token)


@pytest.mark.parametrize('algorithm', ['none', 'RS256', 'unrecognized'])
def test_unapproved_signing_algorithms_fail_closed(algorithm):
    with pytest.raises(RuntimeError, match='JWT_ALGORITHM'):
        Settings(_env_file=None, jwt_secret=secrets.token_urlsafe(64), jwt_algorithm=algorithm).validate_security()


def test_app_factory_and_lifespan_reject_bad_configuration(monkeypatch):
    from app.main import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    monkeypatch.setattr(settings, 'jwt_secret', SecretStr(''))
    with pytest.raises(RuntimeError, match='JWT_SECRET'):
        create_app()
    with pytest.raises(RuntimeError, match='JWT_SECRET'):
        with TestClient(app):
            pass


def test_real_production_import_fails_without_key_and_never_echoes_secret():
    # Explicit overrides prevent reading a real DB or provider configuration.
    env = dict(os.environ, ENVIRONMENT='production', JWT_SECRET='', DATABASE_URL='')
    result = subprocess.run([sys.executable, '-c', 'import app.main'],
                            cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'JWT_SECRET is missing or insecure' in result.stderr


@pytest.mark.parametrize('entry', ['seed_dev_users', 'seed_sample_gyms_and_slots'])
@pytest.mark.parametrize('environment,opt_in,password', [('production', '1', 'private password 782!'),
                                                       ('development', '', 'private password 782!'),
                                                       ('development', '1', '')])
def test_demo_seeding_cannot_bypass_environment_or_opt_in(monkeypatch, entry, environment, opt_in, password):
    from app.scripts import seed_dev
    monkeypatch.setattr(settings, 'environment', environment)
    monkeypatch.setattr(settings, 'database_url', 'mysql+pymysql://unused@localhost/disposable')
    monkeypatch.setenv('ENVIRONMENT', 'development')  # Must not override parsed production.
    monkeypatch.setenv('FITIGO_ALLOW_DEV_SEED', opt_in)
    monkeypatch.setenv('DEV_SEED_PASSWORD', password)
    def forbidden_database():
        pytest.fail('Seeder attempted a database connection before safety checks')
    monkeypatch.setattr(seed_dev, 'SessionLocal', forbidden_database)
    with pytest.raises(RuntimeError):
        getattr(seed_dev, entry)()