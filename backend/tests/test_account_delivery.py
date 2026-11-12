"""Transport contracts use fake SMTP/HTTP only; no network access."""
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from app.core.config import settings
from app.services import account_delivery as delivery


@pytest.mark.parametrize('security', ['starttls', 'ssl'])
@pytest.mark.parametrize('refused', [False, True])
def test_smtp_requires_acceptance_and_tls(monkeypatch, security, refused):
    calls = []
    class SMTP:
        def __init__(self, host, port, **kwargs): calls.append(('connect', host, kwargs))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): calls.append(('ehlo',))
        def starttls(self, context): calls.append(('tls', context.check_hostname))
        def login(self, *args): calls.append(('login',))
        def send_message(self, message):
            assert message['To'] == 'recipient@example.com'
            return {'recipient@example.com': (550, b'private refusal')} if refused else {}
    monkeypatch.setattr(delivery.smtplib, 'SMTP', SMTP)
    monkeypatch.setattr(delivery.smtplib, 'SMTP_SSL', SMTP)
    for name, value in {'smtp_host': 'smtp.example.test', 'smtp_from': 'sender@example.com',
                        'smtp_security': security, 'smtp_username': 'fixture', 'smtp_password': SecretStr('fixture')}.items():
        monkeypatch.setattr(settings, name, value)
    if refused:
        with pytest.raises(HTTPException) as error:
            delivery.send_email('recipient@example.com', 'Subject', 'private body')
        assert error.value.status_code == 503 and 'private' not in str(error.value.detail)
    else:
        delivery.send_email('recipient@example.com', 'Subject', 'private body')
    if security == 'starttls': assert ('tls', True) in calls
    else: assert calls[0][2]['context'].check_hostname


@pytest.mark.parametrize('status,body,accepted', [(201, {'sid': 'SMfixture', 'status': 'queued'}, True),
    (201, {'sid': 'SMfixture', 'status': 'failed'}, False), (401, {'message': 'private credentials'}, False),
    (200, {'sid': 'SMfixture', 'status': 'queued'}, False)])
def test_twilio_acceptance_contract(monkeypatch, status, body, accepted):
    monkeypatch.setattr(settings, 'sms_provider', 'twilio')
    monkeypatch.setattr(settings, 'twilio_account_sid', 'AC'+'1'*32)
    monkeypatch.setattr(settings, 'twilio_auth_token', SecretStr('private-fixture'))
    monkeypatch.setattr(settings, 'twilio_from_number', '+12025550123')
    class Client:
        def __init__(self, **kwargs): assert kwargs == {'timeout': 10, 'follow_redirects': False, 'trust_env': False}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url.startswith('https://api.twilio.com/2010-04-01/Accounts/AC')
            assert kwargs['data']['To'] == '+12025550199'
            return type('Response', (), {'status_code': status, 'json': lambda self: body})()
    monkeypatch.setattr(delivery.httpx, 'Client', Client)
    if accepted: delivery.send_sms('+12025550199', 'private-code')
    else:
        with pytest.raises(HTTPException) as error: delivery.send_sms('+12025550199', 'private-code')
        assert error.value.status_code == 503 and 'private' not in str(error.value.detail)


@pytest.mark.parametrize('value', ['', 'http://app.example.com', 'https://user:password@app.example.com',
                                 'https://app.example.com/#token=bad', 'https://app.example.com/?redirect=bad'])
def test_public_link_configuration_is_required_and_safe(monkeypatch, value):
    monkeypatch.setattr(settings, 'environment', 'production')
    monkeypatch.setattr(settings, 'public_frontend_url', value)
    with pytest.raises(HTTPException): delivery.frontend_link('/auth/accept-invitation')


def test_safe_delivery_errors_survive_global_handler_without_diagnostics():
    from app.main import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    @app.get('/fixture-delivery-error')
    def failure():
        raise HTTPException(503, {'code': 'ACCOUNT_DELIVERY_FAILED', 'message': 'PRIVATE provider diagnostic'})
    response = TestClient(app).get('/fixture-delivery-error')
    assert response.status_code == 503 and response.json()['code'] == 'ACCOUNT_DELIVERY_FAILED'
    assert 'PRIVATE' not in response.text