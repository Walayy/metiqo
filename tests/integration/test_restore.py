"""Exercice DB + objets, corruption refusée et reconstruction depuis le raw."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from metiquo.contracts.enums import DataMode
from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.models import ModelArtifactStore
from metiquo.operations.backup import BackupService
from metiquo.operations.backup_tools import BackupError, file_hash
from metiquo.operations.restore import RestoreRequest, RestoreService
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings
from tests.operations.support import age_key, postgres_tools


@pytest.mark.integration
@pytest.mark.parametrize("encrypted", (False, True))
def test_restore_drill_rebuilds_raw_and_preserves_source(
    postgresql_url: str, tmp_path: Path, encrypted: bool
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    source = create_engine(postgresql_url)
    _seed_catalogs(source, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "mock").model_copy(
        update={
            "object_store_root": tmp_path / "source",
            "backup_root": tmp_path / "backups",
        }
    )
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"
    sync = OracleElixirYearSync(engine=source, settings=settings).sync_year(
        year=2026,
        policy=FreshnessPolicy(require_fresh=True),
        fixture_path=fixture,
    )
    artifact = ModelArtifactStore(FilesystemObjectStore(settings.object_store_root / "models")).put(
        b"restore-drill-model-fixture",
        year=2026,
        artifact_format="application/octet-stream",
        code_commit="abcdef1",
    )
    identity = None
    settings = settings.model_copy(update={"app_data_mode": DataMode.REAL})
    if encrypted:
        age, recipient, identity = age_key(tmp_path)
        settings = settings.model_copy(
            update={
                "backup_external": True,
                "backup_age_binary": age,
                "backup_age_recipient": recipient,
            }
        )
    tools = postgres_tools(source)
    backup = BackupService(source, settings, tools=tools).run()
    target_name = "metiquo_restore_" + uuid4().hex
    root = tmp_path / "restored"
    request = RestoreRequest(
        backup.backup_id, file_hash(backup.path / "index.json"), target_name, root, identity
    )
    service = RestoreService(source, settings, tools=tools)
    admin = create_engine(source.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = create_engine(source.url.set(database=target_name))
    try:
        with pytest.raises(BackupError, match="RESTORE_INDEX_CORRUPTED"):
            service.run(replace(request, index_sha256="0" * 64))
        if encrypted:
            wrong_key_dir = tmp_path / "wrong-key"
            wrong_key_dir.mkdir()
            _, _, wrong_key = age_key(wrong_key_dir)
            with pytest.raises(BackupError, match="RESTORE_DECRYPT_FAILED"):
                service.run(replace(request, identity=wrong_key))
            assert not root.exists()
        # Une corruption est refusée avant toute création de base et sans laisser de dossier.
        index = json.loads((backup.path / "index.json").read_bytes())
        blob = tmp_path / "backups/blobs" / index["blobs"][0]["stored"]["file"]
        original = blob.read_bytes()
        blob.write_bytes(b"corrupted")
        with pytest.raises(BackupError, match="BACKUP_OBJECT_CORRUPTED"):
            service.run(request)
        assert not root.exists()
        with admin.connect() as connection:
            assert not connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": target_name}
            )
        blob.write_bytes(original)
        result = service.run(request)
        assert result.objects_verified >= 3
        with pytest.raises(BackupError, match="RESTORE_DATABASE_EXISTS"):
            service.run(replace(request, target_root=tmp_path / "duplicate"))
        assert not (tmp_path / "duplicate").exists()
        assert (
            root / "models" / artifact.object_key
        ).read_bytes() == b"restore-drill-model-fixture"
        with target.connect() as connection:
            assert (
                connection.scalar(text("SELECT current_snapshot_id FROM raw.source_catalog"))
                == sync.snapshot_id
            )
            before = connection.execute(
                text("SELECT natural_key, row_hash FROM raw.canonical_rows ORDER BY natural_key")
            ).all()
            assert len(before) == 12
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM ops.audit_events WHERE action='backup.restored'")
                )
                == 1
            )
        # Effacer uniquement la projection dans cette nouvelle base prouve une reconstruction.
        with target.begin() as connection:
            connection.execute(text("DELETE FROM raw.canonical_rows"))
        environment = {
            **os.environ,
            "APP_ENV": "test",
            "APP_DATA_MODE": "real",
            "ODDS_PROVIDER": "disabled",
            "DATABASE_URL": target.url.render_as_string(hide_password=False),
            "OBJECT_STORE_ROOT": str(root),
            "PYTHONIOENCODING": "utf-8",
        }
        rebuilt = subprocess.run(
            [
                sys.executable,
                "-m",
                "metiquo.cli",
                "rebuild-canonical",
                "--from",
                "2026-01-01",
                "--json",
            ],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert rebuilt.returncode == 0, rebuilt.stderr
        assert json.loads(rebuilt.stdout)["canonicalRowsFromDate"] == 12
        with target.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM raw.row_revisions")) == 12
            assert connection.scalar(text("SELECT count(*) FROM core.games")) == 1
            assert (
                connection.execute(
                    text(
                        "SELECT natural_key, row_hash FROM raw.canonical_rows ORDER BY natural_key"
                    )
                ).all()
                == before
            )
        with source.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT natural_key, row_hash FROM raw.canonical_rows ORDER BY natural_key"
                    )
                ).all()
                == before
            )
        with pytest.raises(BackupError, match="RESTORE_TARGET_EXISTS"):
            service.run(request)
    finally:
        target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{target_name}" WITH (FORCE)')
        admin.dispose()
        source.dispose()
