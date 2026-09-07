"""Publier un dump cohérent et ses objets dans un dépôt incrémental vérifié."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, insert, select, text, update

from metiquo.config import ObjectStoreBackend, Settings
from metiquo.contracts.enums import DataMode
from metiquo.db.ops_models import AuditEventRecord, BackupRunRecord
from metiquo.foundation.audit import current_audit_context
from metiquo.foundation.locks import resource_lock
from metiquo.foundation.time import Clock, SystemClock
from metiquo.operations.backup_repository import (
    BackupIndex,
    BackupManifest,
    BackupRepository,
    BlobProof,
    ObjectProof,
    remove_tree,
    safe_child,
    write_document,
)
from metiquo.operations.backup_tools import BackupError, file_hash
from metiquo.operations.backup_tools import PostgresTools as PostgresTools
from metiquo.worker.contracts import JobCancelled


@dataclass(frozen=True, slots=True)
class BackupResult:
    backup_id: UUID
    path: Path
    copied_objects: int
    warnings: tuple[str, ...] = ()


def backup_root(settings: Settings) -> Path:
    return (settings.backup_root or settings.object_store_root / "backups").resolve()


def repository_fingerprint(settings: Settings) -> str:
    return hashlib.sha256(str(backup_root(settings)).encode()).hexdigest()


class BackupService:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        tools: PostgresTools | None = None,
        clock: Clock | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> None:
        self.engine, self.settings, self.clock = engine, settings, clock or SystemClock()
        self.checkpoint = checkpoint or (lambda: None)
        self.tools = tools or PostgresTools(
            engine.url,
            dump_command=(settings.backup_pg_dump_binary,),
            timeout=settings.backup_timeout_seconds,
        )

    def run(self) -> BackupResult:
        if self.settings.app_data_mode is not DataMode.REAL:
            raise BackupError("BACKUP_REAL_MODE_REQUIRED")
        if not self.settings.backup_enabled:
            raise BackupError("BACKUP_DISABLED")
        self.checkpoint()
        with resource_lock(self.engine, "ops:backup"):
            identity, started = uuid4(), self.clock.now().value
            with self.engine.begin() as connection:
                # Le verrou de session exclut tout ancien producteur encore vivant.
                connection.execute(
                    update(BackupRunRecord)
                    .where(
                        BackupRunRecord.repository_fingerprint
                        == repository_fingerprint(self.settings),
                        BackupRunRecord.status == "running",
                        BackupRunRecord.started_at <= started,
                    )
                    .values(status="failed", finished_at=started, error_code="BACKUP_INTERRUPTED")
                )
                connection.execute(
                    insert(BackupRunRecord).values(
                        id=identity,
                        status="running",
                        repository_fingerprint=repository_fingerprint(self.settings),
                        object_key=str(identity),
                        started_at=started,
                        encrypted=bool(self.settings.backup_age_recipient),
                        retained=True,
                    )
                )
            try:
                result, index_hash = self._publish(identity)
            except Exception as error:
                code = (
                    error.code
                    if isinstance(error, BackupError)
                    else (
                        "BACKUP_CANCELLED" if isinstance(error, JobCancelled) else "BACKUP_FAILED"
                    )
                )
                with self.engine.begin() as connection:
                    connection.execute(
                        update(BackupRunRecord)
                        .where(BackupRunRecord.id == identity)
                        .values(
                            status="failed",
                            finished_at=self.clock.now().value,
                            error_code=code,
                        )
                    )
                logging.getLogger("metiquo.backup").error("backup.failed.%s", code)
                if isinstance(error, JobCancelled):
                    raise
                raise BackupError(code) from error
            with self.engine.begin() as connection:
                connection.execute(
                    update(BackupRunRecord)
                    .where(BackupRunRecord.id == identity)
                    .values(
                        status="succeeded",
                        finished_at=self.clock.now().value,
                        sha256=index_hash,
                    )
                )
            try:
                self._retain(identity)
            except Exception:
                logging.getLogger("metiquo.backup").error("backup.retention_failed")
                with self.engine.begin() as connection:
                    self._audit(connection, identity, "backup.retention_failed")
                result = BackupResult(
                    identity, result.path, result.copied_objects, ("BACKUP_RETENTION_FAILED",)
                )
            logging.getLogger("metiquo.backup").info("backup.completed")
            return result

    def _audit(self, connection: Connection, identity: UUID, action: str) -> None:
        context = current_audit_context()
        connection.execute(
            insert(AuditEventRecord).values(
                id=uuid4(),
                actor=context.actor if context else "backup-service",
                trace_id=context.trace_id if context else uuid4(),
                action=action,
                target_type="ops.backup_runs",
                target_id=str(identity),
                before_refs={},
                after_refs={},
                occurred_at=self.clock.now().value,
            )
        )

    def _repository(self) -> BackupRepository:
        return BackupRepository(
            backup_root(self.settings),
            recipient=self.settings.backup_age_recipient,
            age_binary=self.settings.backup_age_binary,
            timeout=self.settings.backup_timeout_seconds,
        )

    def _indices(
        self, repository: BackupRepository, current: UUID | None = None
    ) -> list[BackupIndex]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(BackupRunRecord.id, BackupRunRecord.sha256)
                .where(
                    BackupRunRecord.repository_fingerprint == repository_fingerprint(self.settings),
                    BackupRunRecord.status == "succeeded",
                    BackupRunRecord.retained.is_(True),
                )
                .order_by(
                    (BackupRunRecord.id == current).desc(),
                    BackupRunRecord.finished_at.desc(),
                    BackupRunRecord.id.desc(),
                )
            ).all()
        return [
            repository.read_index(identity, digest)
            for identity, digest in rows
            if digest is not None
        ]

    def _publish(self, identity: UUID) -> tuple[BackupResult, str]:
        settings = self.settings
        if settings.object_store_backend is not ObjectStoreBackend.FILESYSTEM:
            raise BackupError("BACKUP_STORAGE_UNSUPPORTED")
        if (
            settings.backup_external or str(backup_root(settings)).startswith("\\\\")
        ) and not settings.backup_age_recipient:
            raise BackupError("BACKUP_ENCRYPTION_REQUIRED")
        source_root = settings.object_store_root.resolve()
        source_root.mkdir(parents=True, exist_ok=True)
        for name in ("raw", "models", "quarantine"):
            data_root = source_root / name
            if backup_root(settings).is_relative_to(data_root) or data_root.is_relative_to(
                backup_root(settings)
            ):
                raise BackupError("BACKUP_ROOT_OVERLAP")
        repository = self._repository()
        known: dict[tuple[str, str], BlobProof] = {}
        for index in self._indices(repository):
            for blob in index.blobs:
                known[(blob.plaintext_sha256, blob.recipient_fingerprint)] = blob
        destination = safe_child(repository.root, repository.root / "runs" / str(identity))
        destination.mkdir()
        copied, objects = 0, []
        staging_root = safe_child(source_root, source_root / "raw" / ".backup-work")
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=staging_root) as temporary:
            stage = safe_child(source_root, Path(temporary))
            with self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True
            ) as connection:
                snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
                assert isinstance(snapshot, str)
                revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
                raw_rows = (
                    connection.execute(
                        text("""
                    SELECT s.id, s.object_key, s.sha256, s.byte_size, c.provider
                    FROM raw.snapshots s JOIN raw.source_catalog c ON c.id = s.source_catalog_id
                """)
                    )
                    .mappings()
                    .all()
                )
                models = (
                    connection.execute(
                        text("""
                    SELECT id, artifact_object_key, artifact_hash, artifact_size_bytes
                    FROM ml.model_versions
                """)
                    )
                    .mappings()
                    .all()
                )
                references: dict[str, tuple[str, int]] = {}
                for row in raw_rows:
                    if row["provider"] != "oracles_elixir":
                        raise BackupError("BACKUP_PROVIDER_UNSUPPORTED")
                    key = row["object_key"]
                    relative = (
                        ("quarantine/oracles_elixir/" + key.removeprefix("quarantine/"))
                        if key.startswith("quarantine/")
                        else "raw/oracles_elixir/" + key
                    )
                    references[relative] = (row["sha256"], row["byte_size"])
                for row in models:
                    references["models/" + row["artifact_object_key"]] = (
                        row["artifact_hash"],
                        row["artifact_size_bytes"],
                    )
                for relative, (digest, size) in references.items():
                    path = safe_child(source_root, source_root / relative)
                    if (
                        not path.is_file()
                        or file_hash(path) != digest
                        or path.stat().st_size != size
                    ):
                        raise BackupError("BACKUP_REQUIRED_OBJECT_INVALID")
                for name in ("raw", "models", "quarantine"):
                    folder = safe_child(source_root, source_root / name)
                    if not folder.exists():
                        continue
                    for directory, subdirectories, files in os.walk(folder):
                        for child in subdirectories:
                            safe_child(source_root, Path(directory) / child)
                        subdirectories[:] = sorted(
                            child for child in subdirectories if not child.startswith(".")
                        )
                        for name in sorted(files):
                            if name.startswith(".") or name.endswith(".part"):
                                continue
                            self.checkpoint()
                            path = safe_child(source_root, Path(directory) / name)
                            blob, added = repository.copy_blob(path, known)
                            objects.append(
                                ObjectProof(
                                    path=path.relative_to(source_root).as_posix(), blob=blob
                                )
                            )
                            copied += int(added)
                captured = {
                    item.path: (item.blob.plaintext_sha256, item.blob.plaintext_bytes)
                    for item in objects
                }
                if any(captured.get(path) != expected for path, expected in references.items()):
                    raise BackupError("BACKUP_SOURCE_CHANGED")
                self.checkpoint()
                self.tools.dump(snapshot, stage / "database.dump")
                self.checkpoint()
                raw_ids = tuple(row["id"] for row in raw_rows)
                model_ids = tuple(row["id"] for row in models)
            encrypted = bool(settings.backup_age_recipient)
            database = repository.encrypt_or_copy(
                stage / "database.dump",
                destination / ("database.dump.age" if encrypted else "database.dump"),
            )
            manifest = BackupManifest(
                backup_id=identity,
                created_at=self.clock.now().value,
                migration_revision=str(revision),
                snapshot_ids=raw_ids,
                model_ids=model_ids,
                database=database,
                database_plaintext_sha256=file_hash(stage / "database.dump"),
                objects=tuple(objects),
            )
            write_document(stage / "manifest.json", manifest)
            manifest_proof = repository.encrypt_or_copy(
                stage / "manifest.json",
                destination / ("manifest.json.age" if encrypted else "manifest.json"),
            )
            index = BackupIndex(
                backup_id=identity,
                created_at=self.clock.now().value,
                encrypted=encrypted,
                manifest=manifest_proof,
                database=database,
                blobs=tuple(item.blob for item in objects),
            )
            write_document(destination / "index.json", index)
            self.checkpoint()
        return BackupResult(identity, destination, copied), file_hash(destination / "index.json")

    def _retain(self, identity: UUID) -> None:
        repository = self._repository()
        indices = self._indices(repository, identity)
        kept = indices[: self.settings.backup_retention_count]
        removed = indices[self.settings.backup_retention_count :]
        for index in removed:
            # Retirer d'abord la disponibilité : un crash de suppression ne doit
            # jamais laisser une preuve annoncée conservée mais déjà effacée.
            with self.engine.begin() as connection:
                connection.execute(
                    update(BackupRunRecord)
                    .where(BackupRunRecord.id == index.backup_id)
                    .values(retained=False)
                )
                self._audit(connection, index.backup_id, "backup.pruned")
        # Reprendre aussi une suppression interrompue lors du passage précédent.
        with self.engine.connect() as connection:
            retired = connection.execute(
                select(BackupRunRecord.id, BackupRunRecord.sha256).where(
                    BackupRunRecord.repository_fingerprint == repository_fingerprint(self.settings),
                    BackupRunRecord.status == "succeeded",
                    BackupRunRecord.retained.is_(False),
                )
            ).all()
        used = {blob.stored.file for index in kept for blob in index.blobs}
        obsolete: set[str] = set()
        directories: list[Path] = []
        for retired_id, digest in retired:
            directory = safe_child(repository.root, repository.root / "runs" / str(retired_id))
            if not directory.exists():
                continue
            index_path = safe_child(repository.root, directory / "index.json")
            if index_path.is_file():
                if file_hash(index_path) != digest:
                    raise BackupError("BACKUP_INDEX_CORRUPTED")
                index = BackupIndex.model_validate_json(index_path.read_bytes())
                obsolete.update(
                    blob.stored.file for blob in index.blobs if blob.stored.file not in used
                )
            directories.append(directory)
        # Garder les index jusqu'à suppression des blobs permet de reprendre le nettoyage.
        for name in obsolete:
            safe_child(repository.root, repository.root / "blobs" / name).unlink(missing_ok=True)
        for directory in directories:
            remove_tree(repository.root, directory)
