"""Stockage filesystem immuable, adressé par le SHA-256 de la source."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, runtime_checkable

SourceKind = Literal["bin", "csv"]
ArtifactName = Literal["manifest", "schema", "quality-report"]


class ObjectCollisionError(RuntimeError):
    """Le contenu physique existant ne correspond pas à son adresse SHA-256."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Adresse stable d'un objet source dans l'ObjectStore."""

    year: int
    sha256: str
    source_kind: SourceKind
    source_path: Path
    reused: bool

    @property
    def object_directory(self) -> Path:
        return self.source_path.parent

    @property
    def object_key(self) -> str:
        return "/".join(self.source_path.parts[-3:])


@runtime_checkable
class ObjectStore(Protocol):
    """Contrat minimal d'un stockage de sources brutes immuables."""

    def put_source(
        self,
        *,
        year: int,
        chunks: Iterable[bytes],
        source_kind: SourceKind = "bin",
        manifest: Mapping[str, object] | None = None,
        schema: Mapping[str, object] | None = None,
        quality_report: Mapping[str, object] | None = None,
    ) -> StoredObject:
        """Écrire puis promouvoir atomiquement un objet complet."""

    def open_source(self, *, year: int, sha256: str) -> BinaryIO:
        """Ouvrir une source existante en lecture binaire."""


class FilesystemObjectStore:
    """Backend local sous ``/data`` avec répertoires promus atomiquement."""

    def __init__(self, root: Path = Path("/data")) -> None:
        self.root = root.resolve()

    def put_source(
        self,
        *,
        year: int,
        chunks: Iterable[bytes],
        source_kind: SourceKind = "bin",
        manifest: Mapping[str, object] | None = None,
        schema: Mapping[str, object] | None = None,
        quality_report: Mapping[str, object] | None = None,
    ) -> StoredObject:
        self._validate_year(year)
        if source_kind not in ("bin", "csv"):
            raise ValueError("source_kind doit valoir 'bin' ou 'csv'")

        year_directory = self.root / f"year={year}"
        year_directory.mkdir(parents=True, exist_ok=True)
        temporary_directory = Path(tempfile.mkdtemp(prefix=".tmp-", dir=year_directory))
        temporary_source = temporary_directory / f"source.{source_kind}"

        try:
            digest = self._write_source(temporary_source, chunks)
            self._write_json(temporary_directory / "manifest.json", manifest)
            self._write_json(temporary_directory / "schema.json", schema)
            self._write_json(temporary_directory / "quality-report.json", quality_report)

            object_directory = year_directory / f"sha256={digest}"
            if object_directory.exists():
                shutil.rmtree(temporary_directory)
                return self._existing_object(year, digest, object_directory)

            try:
                temporary_directory.rename(object_directory)
            except OSError:
                if not object_directory.exists():
                    raise
                shutil.rmtree(temporary_directory)
                return self._existing_object(year, digest, object_directory)

            return StoredObject(
                year=year,
                sha256=digest,
                source_kind=source_kind,
                source_path=object_directory / f"source.{source_kind}",
                reused=False,
            )
        except BaseException:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)
            raise

    def open_source(self, *, year: int, sha256: str) -> BinaryIO:
        self._validate_year(year)
        self._validate_sha256(sha256)
        stored = self._existing_object(
            year,
            sha256,
            self.root / f"year={year}" / f"sha256={sha256}",
        )
        return stored.source_path.open("rb")

    @staticmethod
    def _write_source(target: Path, chunks: Iterable[bytes]) -> str:
        digest = hashlib.sha256()
        with target.open("xb") as stream:
            for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise TypeError("chaque fragment source doit être de type bytes")
                stream.write(chunk)
                digest.update(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        return digest.hexdigest()

    @staticmethod
    def _write_json(target: Path, value: Mapping[str, object] | None) -> None:
        if value is None:
            return
        encoded = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        with target.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def _existing_object(self, year: int, sha256: str, directory: Path) -> StoredObject:
        if not directory.is_dir():
            raise FileNotFoundError(f"objet absent : year={year}/sha256={sha256}")
        candidates = [
            path for path in (directory / "source.bin", directory / "source.csv") if path.is_file()
        ]
        if len(candidates) != 1:
            raise ObjectCollisionError(
                f"l'objet year={year}/sha256={sha256} doit contenir une source unique"
            )
        source_path = candidates[0]
        actual_hash = self._hash_file(source_path)
        if actual_hash != sha256:
            raise ObjectCollisionError(
                f"l'objet year={year}/sha256={sha256} contient le hash {actual_hash}"
            )
        source_kind: SourceKind = "csv" if source_path.suffix == ".csv" else "bin"
        return StoredObject(
            year=year,
            sha256=sha256,
            source_kind=source_kind,
            source_path=source_path,
            reused=True,
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_year(year: int) -> None:
        if not 2014 <= year <= 9999:
            raise ValueError("year doit être compris entre 2014 et 9999")

    @staticmethod
    def _validate_sha256(value: str) -> None:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sha256 doit être un digest hexadécimal minuscule de 64 caractères")
