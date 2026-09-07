"""Upgrade a restored N-1 database while preserving the source and immutable rows."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from metiquo.contracts.enums import DataMode
from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.operations.backup import BackupService
from metiquo.operations.backup_tools import file_hash
from metiquo.operations.migration_drill import MigrationDrill
from metiquo.operations.restore import RestoreRequest
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings
from tests.operations.support import postgres_tools


@pytest.mark.integration
def test_migrations_are_rehearsed_on_a_verified_copy(postgresql_url: str, tmp_path: Path) -> None:
    command.upgrade(alembic_config(postgresql_url), "20260908_0044")
    source = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real").model_copy(
        update={
            "app_data_mode": DataMode.REAL,
            "object_store_root": tmp_path / "source",
            "backup_root": tmp_path / "backups",
        }
    )
    tools = postgres_tools(source)
    _seed_catalogs(source, dataset="league_of_legends_match_data", years=range(2026, 2027))
    OracleElixirYearSync(
        engine=source,
        settings=settings.model_copy(update={"app_data_mode": DataMode.MOCK}),
    ).sync_year(
        year=2026,
        policy=FreshnessPolicy(require_fresh=True),
        fixture_path=Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv",
    )
    backup = BackupService(source, settings, tools=tools).run()
    target_name = "metiquo_restore_" + uuid4().hex
    request = RestoreRequest(
        backup.backup_id, file_hash(backup.path / "index.json"), target_name, tmp_path / "copy"
    )
    admin = create_engine(source.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        result = MigrationDrill(source, settings, tools=tools).run(request)
        assert result.from_revision == "20260908_0044"
        assert result.to_revision == "20260908_0045"
        assert result.database == target_name
        assert result.preserved_snapshots == 1
        with source.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20260908_0044"
            )
            assert connection.scalar(text("SELECT to_regclass('ops.http_rate_limits')")) is None
    finally:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{target_name}" WITH (FORCE)')
        admin.dispose()
        source.dispose()
