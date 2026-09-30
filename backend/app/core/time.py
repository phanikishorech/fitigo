from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Central place for server time.

    Current codebase uses UTC everywhere. Keep it explicit to avoid relying on
    server-local timezone configuration.
    """

    return datetime.now(timezone.utc)


def utc_today() -> datetime.date:  # type: ignore[name-defined]
    return utcnow().date()
