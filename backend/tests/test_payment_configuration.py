import httpx
import pytest
from pydantic import SecretStr, ValidationError
from app.core.config import Settings
from app.services import payment_providers, cashfree_provider, razorpay_gateway, razorpay_provider


@pytest.fixture
def config(monkeypatch):
    value = Settings(_env_file=None, payment_gateway='razorpay', payment_env='sandbox',
        payment_mode='test', razorpay_enabled=False, environment='development',
        razorpay_key_id='rzp_test_fixture', razorpay_key_secret='fixture-secret', razorpay_webhook_secret='fixture-webhook',
        cashfree_client_id='fixture-client', cashfree_client_secret='fixture-secret')
    for module in [payment_providers, cashfree_provider, razorpay_gateway, razorpay_provider]:
        monkeypatch.setattr(module, 'settings', value)
    return value


@pytest.mark.parametrize('name,expected', [('razorpay', 'RAZORPAY'), ('cashfree', 'CASHFREE')])
def test_factory_and_explicit_selection_enable_without_legacy_flag(config, name, expected):
    config.payment_gateway = name
    payment_providers.validate_startup()
    assert payment_providers.configured()
    assert payment_providers.get_provider().name == expected
    assert config.gateway_mode == 'test' and config.gateway_environment == 'sandbox'


@pytest.mark.parametrize('name,field', [('razorpay', 'razorpay_key_id'), ('razorpay', 'razorpay_key_secret'),
    ('razorpay', 'razorpay_webhook_secret'), ('cashfree', 'cashfree_client_id'), ('cashfree', 'cashfree_client_secret')])
def test_missing_selected_credentials_fail_startup_without_fallback(config, name, field):
    config.payment_gateway = name
    setattr(config, field, SecretStr('') if 'secret' in field else '')
    with pytest.raises(ValueError):
        payment_providers.validate_startup()
    assert not payment_providers.configured()


def test_legacy_disabled_and_legacy_enabled_defaults(config):
    config.payment_gateway = None
    config.payment_env = None
    assert not config.gateway_required
    payment_providers.validate_startup()
    config.razorpay_enabled = True
    payment_providers.validate_startup()
    assert payment_providers.get_provider().name == 'RAZORPAY'


def test_conflicting_modes_and_production_sandbox_are_rejected(config):
    config.payment_mode = 'live'
    with pytest.raises(ValueError, match='conflicts'):
        payment_providers.validate_startup()
    config.payment_mode = 'test'
    config.environment = 'production'
    with pytest.raises(ValueError, match='Production requires'):
        payment_providers.validate_startup()


def test_razorpay_live_never_accepts_test_credentials(config):
    config.payment_env, config.payment_mode, config.environment = 'production', 'live', 'production'
    config.razorpay_live_enabled = True
    with pytest.raises(ValueError):
        payment_providers.validate_startup()
    config.razorpay_key_id = 'rzp_live_fixture'
    payment_providers.validate_startup()


@pytest.mark.parametrize('status', [401, 403, 500, 404])
def test_cashfree_production_checks_auth_on_production_host(config, monkeypatch, status):
    config.payment_gateway, config.payment_env, config.payment_mode = 'cashfree', 'production', 'live'
    config.environment, config.payment_return_url = 'production', 'https://fitigo.example/checkout'
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == 'api.cashfree.com'
        assert request.method == 'GET' and '/orders/fitigo_probe_' in request.url.path
        return httpx.Response(status, json={'type': 'invalid_request_error', 'code': 'something_not_found'} if status == 404 else {'type': 'authentication_error'})
    real = httpx.Client
    monkeypatch.setattr(cashfree_provider.httpx, 'Client', lambda **kwargs: real(**kwargs, transport=httpx.MockTransport(handler)))
    if status == 404:
        payment_providers.validate_startup()
    else:
        with pytest.raises(RuntimeError, match='credential validation failed'):
            payment_providers.validate_startup()
    assert len(calls) == 1


def test_invalid_enum_configuration_rejected():
    for values in [{'payment_gateway': 'other'}, {'payment_env': 'test'}, {'cashfree_api_version': '1900-01-01'}]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)