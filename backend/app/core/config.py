from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_THIS_FILE = Path(__file__).resolve()
# .../Fitigo/backend/app/core/config.py
_PROJECT_ROOT = _THIS_FILE.parents[4]  # .../Fitigo
_BACKEND_DIR = _THIS_FILE.parents[3]  # .../Fitigo/backend


class Settings(BaseSettings):
    # Try project-root .env first (recommended), then backend/.env if user prefers.
    model_config = SettingsConfigDict(
        env_file=(str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FitiGo"
    environment: str = "development"
    debug: bool = True

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

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
