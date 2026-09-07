"""Objets de sauvegarde adressés par contenu et preuves de fichiers vérifiables."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from metiquo.contracts.base import ContractModel, UtcDateTime
from metiquo.operations.backup_tools import BackupError, file_hash


class FileProof(ContractModel):
    file: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(alias="byteSize", ge=0)


class BlobProof(ContractModel):
    plaintext_sha256: str = Field(alias="plaintextSha256", pattern=r"^[0-9a-f]{64}$")
    plaintext_bytes: int = Field(alias="plaintextBytes", ge=0)
    recipient_fingerprint: str = Field(alias="recipientFingerprint")
    stored: FileProof


class ObjectProof(ContractModel):
    path: str
    blob: BlobProof


class BackupManifest(ContractModel):
    format: Literal["metiquo-backup-v1"] = "metiquo-backup-v1"
    backup_id: UUID = Field(alias="backupId")
    created_at: UtcDateTime = Field(alias="createdAt")
    migration_revision: str = Field(alias="migrationRevision")
    snapshot_ids: tuple[UUID, ...] = Field(alias="snapshotIds")
    model_ids: tuple[UUID, ...] = Field(alias="modelIds")
    database: FileProof
    database_plaintext_sha256: str = Field(alias="databasePlaintextSha256")
    objects: tuple[ObjectProof, ...]


class BackupIndex(ContractModel):
    format: Literal["metiquo-backup-index-v1"] = "metiquo-backup-index-v1"
    backup_id: UUID = Field(alias="backupId")
    created_at: UtcDateTime = Field(alias="createdAt")
    encrypted: bool
    manifest: FileProof
    database: FileProof
    blobs: tuple[BlobProof, ...]


def safe_child(root: Path, path: Path) -> Path:
    """Refuser les liens, remontées et racines avant lecture, écriture ou suppression."""
    root = root.resolve()
    absolute = path.absolute()
    if not absolute.is_relative_to(root) or absolute == root:
        raise BackupError("BACKUP_PATH_OUTSIDE_ROOT")
    current = root
    for component in absolute.relative_to(root).parts:
        current = current / component
        if component in {"..", "."} or current.is_symlink() or current.is_junction():
            raise BackupError("BACKUP_PATH_LINK_FORBIDDEN")
    resolved = absolute.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise BackupError("BACKUP_PATH_OUTSIDE_ROOT")
    return resolved


def remove_tree(root: Path, path: Path) -> None:
    checked = safe_child(root, path)
    shutil.rmtree(checked)


def write_document(path: Path, document: ContractModel) -> None:
    with path.open("xb") as stream:
        stream.write(document.model_dump_json(by_alias=True).encode())
        stream.flush()
        os.fsync(stream.fileno())


def proof(path: Path) -> FileProof:
    return FileProof(file=path.name, sha256=file_hash(path), byte_size=path.stat().st_size)


def verify_file(root: Path, expected: FileProof) -> Path:
    path = safe_child(root, root / expected.file)
    if (
        not path.is_file()
        or path.stat().st_size != expected.byte_size
        or file_hash(path) != expected.sha256
    ):
        raise BackupError("BACKUP_OBJECT_CORRUPTED")
    return path


class BackupRepository:
    def __init__(self, root: Path, *, recipient: str | None, age_binary: str, timeout: int) -> None:
        self.root = root.resolve()
        self.recipient, self.age_binary, self.timeout = recipient, age_binary, timeout
        self.recipient_fingerprint = (
            hashlib.sha256(recipient.encode()).hexdigest() if recipient else "plain"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("blobs", "runs"):
            safe_child(self.root, self.root / name).mkdir(exist_ok=True)

    def encrypt_or_copy(self, source: Path, target: Path) -> FileProof:
        safe_child(self.root, target)
        temporary = target.with_name(f".{uuid4().hex}.part")
        try:
            with temporary.open("xb") as output:
                if self.recipient:
                    result = subprocess.run(
                        [self.age_binary, "--encrypt", "--recipient", self.recipient, str(source)],
                        stdout=output,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=self.timeout,
                    )
                    if result.returncode:
                        raise BackupError("BACKUP_ENCRYPTION_FAILED")
                else:
                    with source.open("rb") as input_stream:
                        shutil.copyfileobj(input_stream, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            if target.exists():
                raise BackupError("BACKUP_DESTINATION_EXISTS")
            temporary.rename(target)
            return proof(target)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackupError("BACKUP_WRITE_FAILED") from error
        finally:
            if temporary.exists():
                safe_child(self.root, temporary).unlink()

    def copy_blob(
        self, source: Path, known: dict[tuple[str, str], BlobProof]
    ) -> tuple[BlobProof, bool]:
        plaintext_hash, size = file_hash(source), source.stat().st_size
        key = (plaintext_hash, self.recipient_fingerprint)
        previous = known.get(key)
        blob_root = self.root / "blobs"
        if previous is not None:
            if previous.plaintext_bytes != size:
                raise BackupError("BACKUP_OBJECT_CORRUPTED")
            verify_file(blob_root, previous.stored)
            return previous, False
        provisional = blob_root / f"new-{uuid4().hex}"
        stored = self.encrypt_or_copy(source, provisional)
        if file_hash(source) != plaintext_hash:
            raise BackupError("BACKUP_SOURCE_CHANGED")
        destination = blob_root / stored.sha256
        if destination.exists():
            verify_file(
                blob_root,
                FileProof(file=stored.sha256, sha256=stored.sha256, byte_size=stored.byte_size),
            )
            provisional.unlink()
        else:
            provisional.rename(destination)
        item = BlobProof(
            plaintext_sha256=plaintext_hash,
            plaintext_bytes=size,
            recipient_fingerprint=self.recipient_fingerprint,
            stored=FileProof(
                file=destination.name, sha256=stored.sha256, byte_size=stored.byte_size
            ),
        )
        known[key] = item
        return item, True

    def read_index(self, identity: UUID, expected_hash: str) -> BackupIndex:
        path = safe_child(self.root, self.root / "runs" / str(identity) / "index.json")
        if not path.is_file() or file_hash(path) != expected_hash:
            raise BackupError("BACKUP_INDEX_CORRUPTED")
        try:
            index = BackupIndex.model_validate_json(path.read_bytes())
        except ValueError as error:
            raise BackupError("BACKUP_INDEX_CORRUPTED") from error
        if index.backup_id != identity:
            raise BackupError("BACKUP_INDEX_CORRUPTED")
        verify_file(path.parent, index.manifest)
        verify_file(path.parent, index.database)
        return index
