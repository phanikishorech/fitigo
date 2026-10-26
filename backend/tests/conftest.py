"""Keep unit/API fixtures independent of developer payment credentials and mode."""
import pytest
from pydantic import SecretStr
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_payment_settings(monkeypatch):
    for name, value in {
        'payment_gateway': None, 'payment_env': None, 'payment_mode': 'test',
        'razorpay_enabled': False, 'razorpay_live_enabled': False,
        'razorpay_key_id': '', 'razorpay_key_secret': SecretStr(''), 'razorpay_webhook_secret': SecretStr(''),
        'cashfree_client_id': '', 'cashfree_client_secret': SecretStr(''),
    }.items():
        monkeypatch.setattr(settings, name, value)