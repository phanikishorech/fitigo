"""Keep test signing keys and payment settings independent of developer secrets."""
import os
import secrets
import pytest
from pydantic import SecretStr

# Before app imports/collection: test keys are generated only by the test runner,
# never by application startup. No test process inherits a real signing key.
os.environ['JWT_SECRET'] = secrets.token_urlsafe(64)
os.environ['JWT_ALGORITHM'] = 'HS256'
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_payment_settings(monkeypatch):
    for name, value in {
        'payment_gateway': None, 'payment_env': None, 'payment_mode': 'test',
        'razorpay_enabled': False, 'razorpay_live_enabled': False,
        'razorpay_key_id': '', 'razorpay_key_secret': SecretStr(''), 'razorpay_webhook_secret': SecretStr(''),
        'cashfree_client_id': '', 'cashfree_client_secret': SecretStr(''),
        'smtp_host': None, 'smtp_from': None, 'smtp_username': None, 'smtp_password': SecretStr(''),
        'email_provider': 'smtp', 'smtp_security': 'starttls', 'public_frontend_url': '', 'password_reset_frontend_url': '',
        'sms_provider': 'disabled', 'twilio_account_sid': '', 'twilio_auth_token': SecretStr(''), 'twilio_from_number': '',
    }.items():
        monkeypatch.setattr(settings, name, value)