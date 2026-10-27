from __future__ import annotations

from pathlib import Path
from typing import Literal
from pydantic import SecretStr, field_validator

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

    jwt_secret: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    upload_dir: str = "uploads"

    # App download links (configurable; do not hardcode in frontend)
    android_app_url: str | None = None
    ios_app_url: str | None = None

    allowed_origins: str = "http://localhost:5173"

    # Server-only SMTP credentials. Recovery never returns or logs reset tokens.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_security: str = "starttls"  # starttls or ssl; no plaintext delivery
    password_reset_frontend_url: str = "http://localhost:5173/auth/reset-password"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
