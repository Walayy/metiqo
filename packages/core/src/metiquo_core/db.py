from sqlalchemy import Engine, create_engine

from metiquo_core.config import Settings


def create_db(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={
            "connect_timeout": 10,
            "options": "-c timezone=UTC -c statement_timeout=300000",
        },
    )
