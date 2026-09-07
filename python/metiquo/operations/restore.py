"""Restaurer une preuve vérifiée dans une base et un dossier de test neufs."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, insert, text

from metiquo.config import AppEnvironment, Settings
from metiquo.contracts.enums import DataMode
from metiquo.db.ops_models import AuditEventRecord
from metiquo.foundation.audit import current_audit_context
from metiquo.foundation.time import SystemClock
from metiquo.operations.backup import backup_root
from metiquo.operations.backup_repository import (
    BackupIndex,
    BackupManifest,
    FileProof,
    remove_tree,
    safe_child,
    verify_file,
)
from metiquo.operations.backup_tools import BackupError, PostgresTools, file_hash


@dataclass(frozen=True, slots=True)
class RestoreRequest:
    backup_id: UUID
    index_sha256: str
    target_database: str
    target_root: Path
    identity: Path | None = None


@dataclass(frozen=True, slots=True)
class RestoreResult:
    backup_id: UUID
    database: str
    object_root: Path
    objects_verified: int
    migration_revision: str


class RestoreService:
    def __init__(
        self, engine: Engine, settings: Settings, *, tools: PostgresTools | None = None
    ) -> None:
        self.engine, self.settings = engine, settings
        self.tools = tools or PostgresTools(
            engine.url,
            restore_command=(settings.backup_pg_restore_binary,),
            timeout=settings.backup_timeout_seconds,
        )

    def _validate_target(self, request: RestoreRequest) -> Path:
        if self.settings.app_data_mode is not DataMode.REAL:
            raise BackupError("RESTORE_REAL_MODE_REQUIRED")
        if self.settings.app_env is not AppEnvironment.TEST:
            raise BackupError("RESTORE_TEST_ENV_REQUIRED")
        if not re.fullmatch(r"metiquo_restore_[a-z0-9_]{1,47}", request.target_database):
            raise BackupError("RESTORE_TARGET_NAME_INVALID")
        if request.target_database == self.engine.url.database:
            raise BackupError("RESTORE_SOURCE_TARGET_EQUAL")
        root = request.target_root.absolute()
        if (
            any(p.is_symlink() or p.is_junction() for p in (root, *root.parents))
            or ".." in root.parts
        ):
            raise BackupError("RESTORE_TARGET_LINK_FORBIDDEN")
        if root.exists():
            raise BackupError("RESTORE_TARGET_EXISTS")
        if not root.parent.is_dir():
            raise BackupError("RESTORE_PARENT_MISSING")
        root = root.resolve()
        for protected in (backup_root(self.settings), self.settings.object_store_root.resolve()):
            if root.is_relative_to(protected) or protected.is_relative_to(root):
                raise BackupError("RESTORE_ROOT_OVERLAP")
        if not re.fullmatch(r"[0-9a-f]{64}", request.index_sha256):
            raise BackupError("RESTORE_INDEX_HASH_INVALID")
        return root

    def _decode(self, source: Path, target: Path, request: RestoreRequest, encrypted: bool) -> None:
        try:
            with target.open("xb") as stream:
                if encrypted:
                    if request.identity is None or not request.identity.is_file():
                        raise BackupError("RESTORE_IDENTITY_REQUIRED")
                    result = subprocess.run(
                        [
                            self.settings.backup_age_binary,
                            "--decrypt",
                            "--identity",
                            str(request.identity),
                            str(source),
                        ],
                        stdout=stream,
                        stderr=subprocess.PIPE,
                        timeout=self.settings.backup_timeout_seconds,
                        check=False,
                    )
                    if result.returncode:
                        raise BackupError("RESTORE_DECRYPT_FAILED")
                else:
                    with source.open("rb") as incoming:
                        shutil.copyfileobj(incoming, stream)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackupError("RESTORE_OBJECT_UNAVAILABLE") from error

    def run(self, request: RestoreRequest) -> RestoreResult:
        root = self._validate_target(request)
        repository = backup_root(self.settings)
        run = safe_child(repository, repository / "runs" / str(request.backup_id))
        index_path = safe_child(repository, run / "index.json")
        if not index_path.is_file() or file_hash(index_path) != request.index_sha256:
            raise BackupError("RESTORE_INDEX_CORRUPTED")
        index = BackupIndex.model_validate_json(index_path.read_bytes())
        if index.backup_id != request.backup_id:
            raise BackupError("RESTORE_BACKUP_ID_MISMATCH")
        manifest_source, database_source = (
            verify_file(run, index.manifest),
            verify_file(run, index.database),
        )
        # mkdir sans exist_ok réserve exclusivement ce nouveau dossier.
        root.mkdir()
        stage = safe_child(root, root / ".restore-work")
        stage.mkdir()
        database_created = False
        try:
            self._decode(manifest_source, stage / "manifest.json", request, index.encrypted)
            manifest = BackupManifest.model_validate_json((stage / "manifest.json").read_bytes())
            if manifest.backup_id != request.backup_id or manifest.database != index.database:
                raise BackupError("RESTORE_MANIFEST_MISMATCH")
            self._decode(database_source, stage / "database.dump", request, index.encrypted)
            if file_hash(stage / "database.dump") != manifest.database_plaintext_sha256:
                raise BackupError("RESTORE_DATABASE_CORRUPTED")
            paths: set[str] = set()
            indexed = {blob.model_dump_json() for blob in index.blobs}
            if {item.blob.model_dump_json() for item in manifest.objects} != indexed:
                raise BackupError("RESTORE_MANIFEST_MISMATCH")
            for item in manifest.objects:
                if item.path in paths or item.path.split("/")[0] not in {
                    "raw",
                    "models",
                    "quarantine",
                }:
                    raise BackupError("RESTORE_OBJECT_PATH_INVALID")
                paths.add(item.path)
                if item.blob.model_dump_json() not in indexed:
                    raise BackupError("RESTORE_MANIFEST_MISMATCH")
                source = verify_file(repository / "blobs", item.blob.stored)
                destination = safe_child(root, root / item.path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._decode(source, destination, request, index.encrypted)
                verify_file(
                    destination.parent,
                    FileProof(
                        file=destination.name,
                        sha256=item.blob.plaintext_sha256,
                        byte_size=item.blob.plaintext_bytes,
                    ),
                )
            self._create_database(request.target_database)
            database_created = True
            self.tools.restore(stage / "database.dump", request.target_database)
            self._verify_database(request, manifest, root)
            remove_tree(root, stage)
            logging.getLogger("metiquo.restore").info("backup.restored")
            return RestoreResult(
                request.backup_id,
                request.target_database,
                root,
                len(paths),
                manifest.migration_revision,
            )
        except Exception:
            # Avant SQL, nettoyer uniquement le dossier réservé par cette opération.
            # Après création de la base, conserver l'ensemble pour diagnostic explicite.
            if not database_created:
                remove_tree(root.parent, root)
            logging.getLogger("metiquo.restore").error("backup.restore_failed")
            raise

    def _create_database(self, database: str) -> None:
        admin = create_engine(
            self.engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
        )
        try:
            with admin.connect() as connection:
                if connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database}
                ):
                    raise BackupError("RESTORE_DATABASE_EXISTS")
                # Identifiant contrôlé par la regex de _validate_target, aucune option SQL libre.
                connection.exec_driver_sql(f'CREATE DATABASE "{database}" TEMPLATE template0')
        finally:
            admin.dispose()

    def _verify_database(
        self, request: RestoreRequest, manifest: BackupManifest, root: Path
    ) -> None:
        restored = create_engine(self.engine.url.set(database=request.target_database))
        try:
            with restored.begin() as connection:
                revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
                raw_ids = set(connection.scalars(text("SELECT id FROM raw.snapshots")))
                model_ids = set(connection.scalars(text("SELECT id FROM ml.model_versions")))
                if (
                    revision != manifest.migration_revision
                    or raw_ids != set(manifest.snapshot_ids)
                    or model_ids != set(manifest.model_ids)
                ):
                    raise BackupError("RESTORE_DATABASE_MANIFEST_MISMATCH")
                for row in connection.execute(
                    text("SELECT object_key, sha256, byte_size FROM raw.snapshots")
                ):
                    relative = (
                        "quarantine/oracles_elixir/" + row.object_key.removeprefix("quarantine/")
                        if row.object_key.startswith("quarantine/")
                        else "raw/oracles_elixir/" + row.object_key
                    )
                    path = safe_child(root, root / relative)
                    verify_file(
                        path.parent,
                        FileProof(file=path.name, sha256=row.sha256, byte_size=row.byte_size),
                    )
                for row in connection.execute(
                    text(
                        "SELECT artifact_object_key, artifact_hash, artifact_size_bytes "
                        "FROM ml.model_versions"
                    )
                ):
                    path = safe_child(root, root / "models" / row.artifact_object_key)
                    verify_file(
                        path.parent,
                        FileProof(
                            file=path.name,
                            sha256=row.artifact_hash,
                            byte_size=row.artifact_size_bytes,
                        ),
                    )
                context = current_audit_context()
                connection.execute(
                    insert(AuditEventRecord).values(
                        id=uuid4(),
                        actor=context.actor if context else "restore-service",
                        action="backup.restored",
                        target_type="ops.backup_runs",
                        target_id=str(request.backup_id),
                        before_refs={},
                        after_refs={
                            "snapshots": len(raw_ids),
                            "models": len(model_ids),
                            "objects": len(manifest.objects),
                        },
                        trace_id=context.trace_id if context else uuid4(),
                        occurred_at=SystemClock().now().value,
                    )
                )
        finally:
            restored.dispose()
