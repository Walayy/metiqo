"""Environnement Alembic de Metiquo."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from metiquo.config import load_settings
from metiquo.db import raw_models as _raw_models  # noqa: F401
from metiquo.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    injected_url = config.attributes.get("database_url")
    if injected_url is not None:
        if not isinstance(injected_url, str):
            raise TypeError("L'URL Alembic injectée doit être une chaîne")
        return injected_url
    return load_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Générer le SQL sans ouvrir de connexion."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécuter les migrations dans une session PostgreSQL forcée en UTC."""

    connectable = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args={"options": "-c timezone=UTC"},
    )

    with connectable.connect() as connection:
        _run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
