from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.database.base import Base

# Import models so they are registered on Base.metadata
from app.models import auth  # noqa: F401
from app.models import gym  # noqa: F401
from app.models import slot  # noqa: F401
from app.models import booking  # noqa: F401
from app.models import staff  # noqa: F401
from app.models import membership  # noqa: F401
from app.models import review  # noqa: F401
from app.models import notification  # noqa: F401
from app.models import class_booking  # noqa: F401
from app.models import cart  # noqa: F401
from app.models import wallet  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the project root .env file before running migrations."
        )
    return settings.database_url


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
