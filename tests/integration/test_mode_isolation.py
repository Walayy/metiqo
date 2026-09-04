"""Preuve PostgreSQL de l'isolation des factories mock et réelle."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, String, Table, inspect, select

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.repositories import MockRepositoryFactory, RealRepositoryFactory
from metiquo.repositories.boundary import LogicalSchema

ROOT = Path(__file__).resolve().parents[2]
PROBE_METADATA = MetaData()
PROBE_TABLE = Table(
    "mode_isolation_probe",
    PROBE_METADATA,
    Column("id", Integer, primary_key=True),
    Column("payload", String(32), nullable=False),
    schema=LogicalSchema.CORE.value,
)


def settings(database_url: str, mode: DataMode) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": mode.value,
            "database_url": database_url,
            "odds_provider": "mock" if mode is DataMode.MOCK else "disabled",
        }
    )


def test_mock_and_real_factories_cannot_mix_rows(postgresql_url: str) -> None:
    alembic = Config(ROOT / "alembic.ini")
    alembic.attributes["database_url"] = postgresql_url
    command.upgrade(alembic, "head")

    mock = MockRepositoryFactory.from_settings(settings(postgresql_url, DataMode.MOCK))
    real = RealRepositoryFactory.from_settings(settings(postgresql_url, DataMode.REAL))
    try:
        PROBE_TABLE.create(real.engine, checkfirst=True)
        PROBE_TABLE.create(mock.engine, checkfirst=True)

        with real.engine.begin() as connection:
            connection.execute(PROBE_TABLE.insert().values(id=1, payload="real-only"))
        with mock.engine.begin() as connection:
            connection.execute(PROBE_TABLE.insert().values(id=1, payload="mock-only"))

        with real.engine.connect() as connection:
            real_rows = connection.execute(select(PROBE_TABLE.c.payload)).scalars().all()
        with mock.engine.connect() as connection:
            mock_rows = connection.execute(select(PROBE_TABLE.c.payload)).scalars().all()

        assert real_rows == ["real-only"]
        assert mock_rows == ["mock-only"]
        assert "mode_isolation_probe" in inspect(real.engine).get_table_names(schema="core")
        assert "mode_isolation_probe" in inspect(mock.engine).get_table_names(schema="mock")
    finally:
        PROBE_TABLE.drop(mock.engine, checkfirst=True)
        PROBE_TABLE.drop(real.engine, checkfirst=True)
        mock.engine.dispose()
        real.engine.dispose()
