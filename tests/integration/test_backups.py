"""Sauvegarde PostgreSQL réelle et copie incrémentale des objets nécessaires."""

import json
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, func, insert, select, update
from sqlalchemy.exc import DBAPIError

from metiquo.contracts.enums import DataMode
from metiquo.db.ops_models import AuditEventRecord, BackupRunRecord
from metiquo.foundation.metrics import ApiMetrics
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.models import ModelArtifactStore
from metiquo.operations.backup import BackupService, PostgresTools, repository_fingerprint
from metiquo.operations.backup_tools import BackupError
from metiquo.services.operational_status import OperationalStatusService
from metiquo.worker.contracts import JobCancelled
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
@pytest.mark.parametrize("encrypted", (False, True))
def test_backup_contains_dump_raw_and_models_and_reuses_immutable_blobs(
    postgresql_url: str, tmp_path: Path, encrypted: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "mock").model_copy(
        update={
            "object_store_root": tmp_path / "objects",
            "backup_root": tmp_path / "backups",
            "backup_retention_count": 2,
        }
    )
    age = os.environ.get("TEST_AGE_BINARY") or shutil.which("age")
    private_key = tmp_path / "restore-key.txt"
    if encrypted:
        if not age:
            pytest.skip("age ou TEST_AGE_BINARY requis pour le vrai chiffrement")
        keygen = str(Path(age).with_name("age-keygen.exe" if os.name == "nt" else "age-keygen"))
        subprocess.run([keygen, "-o", str(private_key)], capture_output=True, check=True)
        recipient = subprocess.run(
            [keygen, "-y", str(private_key)], capture_output=True, text=True, check=True
        ).stdout.strip()
        settings = settings.model_copy(
            update={
                "backup_external": True,
                "backup_age_recipient": recipient,
                "backup_age_binary": age,
            }
        )
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"
    report = OracleElixirYearSync(
        engine=engine, settings=settings, clock=FixedClock(UtcInstant(NOW))
    ).sync_year(year=2026, policy=FreshnessPolicy(require_fresh=True), fixture_path=fixture)
    assert report.snapshot_id is not None
    model = ModelArtifactStore(FilesystemObjectStore(settings.object_store_root / "models")).put(
        b"backup-fixture-model",
        year=2026,
        artifact_format="application/octet-stream",
        code_commit="abcdef1",
    )
    settings = settings.model_copy(update={"app_data_mode": DataMode.REAL})
    container = os.environ.get("TEST_PG_CONTAINER")
    if container is None and shutil.which("pg_dump") is None:
        pytest.skip("pg_dump ou TEST_PG_CONTAINER requis pour le vrai dump")
    tools = PostgresTools(
        engine.url,
        dump_command=(
            "docker",
            "exec",
            "-i",
            "-e",
            "PGHOST",
            "-e",
            "PGPORT",
            "-e",
            "PGUSER",
            "-e",
            "PGPASSWORD",
            "-e",
            "PGDATABASE",
            container,
            "pg_dump",
        )
        if container
        else ("pg_dump",),
        environment_overrides={"PGHOST": "127.0.0.1", "PGPORT": "5432"} if container else {},
    )
    service = BackupService(engine, settings, tools=tools, clock=FixedClock(UtcInstant(NOW)))
    interrupted_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(BackupRunRecord).values(
                id=interrupted_id,
                status="running",
                repository_fingerprint=repository_fingerprint(settings),
                object_key=str(interrupted_id),
                started_at=NOW - timedelta(days=1),
                encrypted=encrypted,
                retained=True,
            )
        )
    first = service.run()
    with engine.connect() as connection:
        interrupted = connection.execute(
            select(BackupRunRecord.status, BackupRunRecord.error_code).where(
                BackupRunRecord.id == interrupted_id
            )
        ).one()
        assert interrupted == ("failed", "BACKUP_INTERRUPTED")

    def content(name: str) -> bytes:
        if encrypted:
            assert age is not None
            return subprocess.run(
                [
                    age,
                    "--decrypt",
                    "--identity",
                    str(private_key),
                    str(first.path / (name + ".age")),
                ],
                capture_output=True,
                check=True,
            ).stdout
        return (first.path / name).read_bytes()

    manifest = json.loads(content("manifest.json"))
    assert content("database.dump").startswith(b"PGDMP")
    paths = {entry["path"] for entry in manifest["objects"]}
    assert f"models/{model.object_key}" in paths
    assert any(
        path.startswith("raw/oracles_elixir/") and path.endswith("source.csv") for path in paths
    )
    assert first.copied_objects == len(paths) and first.copied_objects > 1
    assert service.run().copied_objects == 0
    assert postgresql_url not in json.dumps(manifest)
    health = OperationalStatusService(engine, settings, FixedClock(UtcInstant(NOW))).snapshot(
        ApiMetrics().snapshot()
    )
    assert health.backups.status == "fresh" and health.backups.last_success_at == NOW
    assert service.run().warnings == ()
    assert len(list((tmp_path / "backups/runs").iterdir())) == 2
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(BackupRunRecord)
                .where(BackupRunRecord.retained.is_(False))
            )
            == 1
        )
    if not encrypted:

        def unavailable(root: Path, target: Path) -> None:
            raise PermissionError("simulated unavailable retention storage")

        with monkeypatch.context() as patch:
            patch.setattr("metiquo.operations.backup.remove_tree", unavailable)
            assert service.run().warnings == ("BACKUP_RETENTION_FAILED",)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(AuditEventRecord.id).where(
                        AuditEventRecord.action == "backup.retention_failed"
                    )
                )
                is not None
            )
        assert service.run().warnings == ()
        assert len(list((tmp_path / "backups/runs").iterdir())) == 2
    with (
        pytest.raises(DBAPIError, match="completed backup proof is immutable"),
        engine.begin() as connection,
    ):
        connection.execute(
            update(BackupRunRecord)
            .where(BackupRunRecord.id == first.backup_id)
            .values(sha256="0" * 64)
        )
    source = next(settings.object_store_root.glob("raw/**/source.csv"))
    source_bytes = source.read_bytes()
    source.unlink()
    try:
        with pytest.raises(BackupError, match="BACKUP_REQUIRED_OBJECT_INVALID"):
            service.run()
    finally:
        source.write_bytes(source_bytes)
    blob = next(
        entry["blob"]
        for entry in manifest["objects"]
        if entry["path"] == f"models/{model.object_key}"
    )
    blob_path = tmp_path / "backups/blobs" / blob["stored"]["file"]
    if encrypted:
        assert b"backup-fixture-model" not in blob_path.read_bytes()
        assert not any(
            path.name in {"database.dump", "manifest.json"}
            for path in (tmp_path / "backups").rglob("*")
        )
    blob_path.write_bytes(b"corrupted-backup")
    with pytest.raises(BackupError, match="BACKUP_OBJECT_CORRUPTED"):
        service.run()
    failed = OperationalStatusService(engine, settings, FixedClock(UtcInstant(NOW))).snapshot(
        ApiMetrics().snapshot()
    )
    assert failed.backups.status == "failed"
    engine.dispose()


@pytest.mark.integration
def test_backup_guards_external_storage_and_cancellation(
    postgresql_url: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real").model_copy(
        update={
            "object_store_root": tmp_path / "objects",
            "backup_root": tmp_path / "backups",
            "backup_external": True,
            "backup_age_recipient": None,
        }
    )
    with pytest.raises(BackupError, match="BACKUP_ENCRYPTION_REQUIRED"):
        BackupService(engine, settings).run()
    overlap = settings.model_copy(
        update={
            "backup_external": False,
            "backup_root": tmp_path / "objects/raw/backups",
        }
    )
    with pytest.raises(BackupError, match="BACKUP_ROOT_OVERLAP"):
        BackupService(engine, overlap).run()
    calls = 0

    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise JobCancelled()

    with pytest.raises(JobCancelled):
        BackupService(
            engine, settings.model_copy(update={"backup_external": False}), checkpoint=cancel
        ).run()
    with engine.connect() as connection:
        assert set(connection.scalars(select(BackupRunRecord.error_code))) == {
            "BACKUP_ENCRYPTION_REQUIRED",
            "BACKUP_ROOT_OVERLAP",
            "BACKUP_CANCELLED",
        }
    engine.dispose()
