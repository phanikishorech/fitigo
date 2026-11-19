from __future__ import annotations

from pathlib import Path
import os
from typing import Literal
from pydantic import Field, SecretStr, field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


_THIS_FILE = Path(__file__).resolve()
# .../Fitigo/backend/app/core/config.py
_PROJECT_ROOT = _THIS_FILE.parents[3]  # .../Fitigo
_BACKEND_DIR = _THIS_FILE.parents[2]  # .../Fitigo/backend


class Settings(BaseSettings):
    # Try project-root .env first (recommended), then backend/.env if user prefers.
    model_config = SettingsConfigDict(
        env_file=(str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "FitiGo"
    environment: str = "development"
    debug: bool = False
    payment_mode: Literal["test", "live"] = "test"
    # None retains the legacy RAZORPAY_ENABLED / PAYMENT_MODE configuration.
    payment_gateway: Literal["razorpay", "cashfree"] | None = None
    payment_env: Literal["sandbox", "production"] | None = None
    cashfree_client_id: str = ""
    cashfree_client_secret: SecretStr = SecretStr("")
    cashfree_api_version: Literal["2026-01-01"] = "2026-01-01"
    payment_return_url: str = "http://localhost:5173/checkout"
    razorpay_enabled: bool = False
    razorpay_live_enabled: bool = False
    razorpay_key_id: str = ""
    razorpay_key_secret: SecretStr = SecretStr("")
    razorpay_webhook_secret: SecretStr = SecretStr("")

    @field_validator("payment_mode", "payment_gateway", "payment_env", mode="before")
    @classmethod
    def normalize_payment_mode(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def gateway_required(self) -> bool:
        return self.payment_gateway is not None or self.razorpay_enabled

    @property
    def gateway_name(self) -> str:
        return (self.payment_gateway or "razorpay").upper()

    @property
    def gateway_mode(self) -> str:
        if self.payment_env is not None:
            return "test" if self.payment_env == "sandbox" else "live"
        return self.payment_mode

    @property
    def gateway_environment(self) -> str:
        return "sandbox" if self.gateway_mode == "test" else "production"

    api_v1_prefix: str = "/api/v1"

    # Optional so the app can boot and serve /health even if DB isn't configured yet.
    # /health/db will report unhealthy until configured.
    database_url: str | None = None

    # No shared development/test signing key. Configure every API instance.
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    upload_dir: str = "uploads"
    # Enable only after df081ac34602 has been applied and storage permissions verified.
    operational_workflows_enabled: bool = False
    notification_workflows_enabled: bool = False
    # Separate opt-in; queue creation must never start an external sender.
    notification_email_enabled: bool = False
    support_email: str = ''
    # Activate only after f02a3ce56824; operational audit is required too.
    support_workflows_enabled: bool = False
    # Separate deployment gate; never enables a financial posting engine.
    source_evidence_enabled: bool = False
    marketplace_allocations_enabled: bool = False
    marketplace_live_allocations_enabled: bool = False
    marketplace_payouts_enabled: bool = False

    # App download links (configurable; do not hardcode in frontend)
    android_app_url: str | None = None
    ios_app_url: str | None = None

    allowed_origins: str = "http://localhost:5173"

    # Server-only SMTP credentials. Recovery never returns or logs reset tokens.
    email_provider: Literal['smtp', 'disabled'] = 'smtp'
    public_frontend_url: str = ''
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr = SecretStr('')
    smtp_from: str | None = None
    smtp_security: str = "starttls"  # starttls or ssl; no plaintext delivery
    # Legacy explicit reset URL remains supported; no implicit localhost link.
    password_reset_frontend_url: str = ''
    password_reset_expiry_minutes: int = Field(default=30, ge=5, le=120)
    invitation_expiry_hours: int = Field(default=48, ge=1, le=168)
    invitation_resend_seconds: int = Field(default=60, ge=30, le=3600)
    otp_expiry_seconds: int = Field(default=600, ge=60, le=900)
    otp_resend_seconds: int = Field(default=60, ge=30, le=600)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_send_limit: int = Field(default=5, ge=1, le=10)
    sms_provider: Literal['disabled', 'twilio'] = 'disabled'
    twilio_account_sid: str = ''
    twilio_auth_token: SecretStr = SecretStr('')
    twilio_from_number: str = ''

    def validate_security(self) -> None:
        """Fail closed at API startup, without including configuration values.

        Apply the same policy in every environment: an ENVIRONMENT typo or a
        copied development configuration must not bypass signing-key checks.
        Length/placeholder checks are a floor, not proof of random entropy.
        """
        minimum = {"HS256": 32, "HS384": 48, "HS512": 64}.get(self.jwt_algorithm)
        if minimum is None:
            raise RuntimeError("JWT_ALGORITHM must be HS256, HS384 or HS512.")
        secret = self.jwt_secret.get_secret_value()
        normalized = "".join(c for c in secret.lower() if c.isalnum())
        placeholders = ("changeme", "replacewith", "yoursecret", "yourjwt", "testonly", "developmentonly")
        if (not secret or secret != secret.strip() or len(secret.encode("utf-8")) < minimum
                or len(set(secret)) < 12 or any(value in normalized for value in placeholders)):
            raise RuntimeError(
                "JWT_SECRET is missing or insecure. Configure an independently generated random signing secret "
                "of at least 32 bytes for HS256, 48 for HS384 or 64 for HS512; placeholders are not allowed."
            )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Tests receive all settings from their isolated child process, never local .env.
settings = Settings(_env_file=None) if os.environ.get('FITIGO_TEST_BOOTSTRAPPED') == '1' else Settings()  # type: ignore[call-arg]
