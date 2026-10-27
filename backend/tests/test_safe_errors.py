"""Exercise the real application boundary; never use the configured database."""
import logging
import re
import pytest
from fastapi import BackgroundTasks, Depends, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import OperationalError
from app.core.config import settings
from app.main import create_app
from app.routers import health

SECRET = 'NEVER-EXPOSE-secret-password-123'
PRIVATE = r'C:\Users\private\app\payments.py'


class InvalidInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=20)
    token: str

    @field_validator('token')
    @classmethod
    def reject_token(cls, value):
        raise ValueError(f'private validator value: {value}')


class Output(BaseModel):
    count: int


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, 'debug', True)
    application = create_app()

    @application.get('/_test/unexpected')
    def unexpected():
        raise RuntimeError(f'{PRIVATE} password={SECRET}')

    @application.get('/_test/database')
    def database():
        raise OperationalError('SELECT password_hash FROM users WHERE token=:token', {'token': SECRET},
                               RuntimeError('mysql://root:password@localhost/fitigo'))

    @application.get('/_test/server/{code}')
    def server(code: int):
        raise HTTPException(code, detail={'message': SECRET, 'sql': 'SELECT * FROM payments', 'file': PRIVATE},
                            headers={'X-Debug': SECRET})

    @application.get('/_test/conflict')
    def conflict():
        raise HTTPException(409, {'code': 'MEMBERSHIP_ALREADY_ACTIVE', 'message': 'Membership already active',
                                  'internal': SECRET})

    @application.get('/_test/auth')
    def auth():
        raise HTTPException(401, 'Invalid or expired token', headers={'WWW-Authenticate': 'Bearer'})

    @application.get('/_test/rate')
    def rate():
        raise HTTPException(429, 'Too many attempts. Please try again later.', headers={'Retry-After': '60'})

    @application.get('/_test/unsafe-client-error')
    def unsafe_client_error():
        raise HTTPException(400, f'Traceback {PRIVATE} SQLAlchemy password={SECRET}')

    @application.post('/_test/validation')
    def validation(payload: InvalidInput):
        return {'ok': True}

    @application.get('/_test/output', response_model=Output)
    def output():
        return {'count': SECRET}

    def dependency():
        raise RuntimeError(SECRET)

    @application.get('/_test/dependency')
    def dependency_failure(value=Depends(dependency)):
        return {'ok': True}

    @application.get('/_test/background')
    def background(tasks: BackgroundTasks):
        tasks.add_task(dependency)
        return {'accepted': True}

    # No context manager: do not run production startup/credential validation.
    return TestClient(application, raise_server_exceptions=False)


def assert_safe(response, status):
    assert response.status_code == status
    assert response.headers['content-type'].startswith('application/json')
    for value in (SECRET, PRIVATE, 'Traceback', 'SELECT ', 'password_hash', 'sqlalchemy', 'RuntimeError', 'mysql://'):
        assert value not in response.text
    assert re.fullmatch(r'[0-9a-f]{32}', response.json()['request_id'])
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('path', ['unexpected', 'database', 'dependency', 'output'])
@pytest.mark.parametrize('accept', ['application/json', 'text/html'])
def test_unexpected_errors_never_expose_debug_html_sql_or_input(client, path, accept, caplog):
    with caplog.at_level(logging.ERROR, logger='fitigo.errors'):
        response = client.get(f'/_test/{path}?token={SECRET}', headers={'Accept': accept, 'Authorization': SECRET, 'X-Request-ID': SECRET})
    assert client.app.debug is False
    assert_safe(response, 500)
    assert response.json()['code'] == 'INTERNAL_SERVER_ERROR'
    assert response.headers['x-request-id'] == response.json()['request_id']
    assert response.json()['request_id'] in caplog.text
    for value in (SECRET, PRIVATE, 'password_hash', 'SELECT ', 'mysql://'):
        assert value not in caplog.text
    assert any('frames=' in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize('code', [500, 502, 503, 504])
def test_explicit_server_exceptions_are_generic(client, code):
    response = client.get(f'/_test/server/{code}')
    assert_safe(response, code)
    assert 'x-debug' not in response.headers
    assert 'payment status' in response.json()['detail']


def test_business_errors_auth_headers_rate_limits_and_cors_are_preserved(client):
    response = client.get('/_test/conflict')
    assert response.status_code == 409
    assert response.json()['detail'] == {'code': 'MEMBERSHIP_ALREADY_ACTIVE', 'message': 'Membership already active'}
    assert SECRET not in response.text
    response = client.get('/_test/auth')
    assert response.status_code == 401 and response.headers['www-authenticate'] == 'Bearer'
    response = client.get('/_test/rate')
    assert response.status_code == 429 and response.headers['retry-after'] == '60'
    response = client.get('/_test/unexpected', headers={'Origin': 'http://localhost:5173'})
    assert_safe(response, 500)
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    assert 'X-Request-ID' in response.headers['access-control-expose-headers']


def test_validation_does_not_echo_secrets_custom_messages_or_unknown_keys(client):
    response = client.post('/_test/validation', json={'password': 'short-secret', 'token': SECRET, SECRET: PRIVATE})
    assert_safe(response, 422)
    assert 'short-secret' not in response.text and 'private validator' not in response.text
    detail = response.json()['detail']
    assert any(error['loc'] == ['body', 'password'] for error in detail)
    assert all(set(error) == {'loc', 'msg', 'type'} for error in detail)
    response = client.post('/_test/validation', content='{"token": "' + SECRET, headers={'Content-Type': 'application/json'})
    assert_safe(response, 422)


def test_client_diagnostics_404_and_method_errors_do_not_expose_internals(client):
    assert_safe(client.get('/_test/unsafe-client-error'), 400)
    assert_safe(client.get('/_test/missing'), 404)
    response = client.post('/_test/conflict')
    assert_safe(response, 405)
    assert response.headers['allow'] == 'GET'


@pytest.mark.parametrize('configured', [True, False])
def test_database_health_never_returns_connection_errors(client, monkeypatch, configured, caplog):
    class BrokenDatabase:
        def connect(self):
            raise RuntimeError(f'mysql://root:{SECRET}@localhost/private')
    monkeypatch.setattr(health, 'engine', BrokenDatabase() if configured else None)
    response = client.get('/api/v1/health/db')
    assert_safe(response, 503)
    assert response.json()['db'] == {'healthy': False}
    assert SECRET not in caplog.text


def test_background_error_does_not_append_diagnostics_to_success(client, caplog):
    with caplog.at_level(logging.ERROR, logger='fitigo.errors'):
        response = client.get('/_test/background')
    assert response.status_code == 200 and response.json() == {'accepted': True}
    assert SECRET not in caplog.text


def test_request_ids_are_generated_per_request(client):
    first = client.get('/_test/unexpected').json()['request_id']
    second = client.get('/_test/unexpected').json()['request_id']
    assert first != second


@pytest.mark.parametrize('path', ['/api/v1/wallet/balance', '/api/v1/wallet/transactions', '/api/v1/payments/history'])
def test_actual_wallet_and_payment_routes_sanitize_database_failure(client, path):
    from app.database.session import get_db

    def broken_database():
        raise OperationalError('SELECT wallet_transactions.checkout_id FROM wallet_transactions',
                               {'secret': SECRET}, RuntimeError(PRIVATE))

    client.app.dependency_overrides[get_db] = broken_database
    response = client.get(path, headers={'Authorization': 'Bearer deliberately-invalid-fixture'})
    assert_safe(response, 500)
    assert 'wallet_transactions' not in response.text


def test_real_auth_validation_never_echoes_submitted_password(client):
    from app.database.session import get_db
    client.app.dependency_overrides[get_db] = lambda: None
    response = client.post('/api/v1/auth/login', json={'email': 'invalid-email', 'password': ''})
    assert_safe(response, 422)
    assert 'invalid-email' not in response.text
    assert all('input' not in error and 'ctx' not in error for error in response.json()['detail'])