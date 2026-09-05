"""Coordination annuelle de la chaîne Oracle's Elixir validée par composants."""

from __future__ import annotations

import csv
import gzip
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, time
from functools import partial
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, Table, func, insert, select, update

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import (
    CanonicalRow,
    IngestionRun,
    Snapshot,
    SourceCatalog,
)
from metiquo.db.raw_models import (
    QualityIssue as PersistedQualityIssue,
)
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.data_quality import (
    DataQualityValidator,
    PreviousQualitySummary,
    QualityReport,
)
from metiquo.ingestion.freshness import (
    FreshnessPolicy,
    FreshnessService,
    PostgresFreshnessRepository,
    SourceFreshnessDecision,
)
from metiquo.ingestion.google_drive_api import GoogleDriveApiTransport
from metiquo.ingestion.google_drive_public import GoogleDrivePublicHttpTransport
from metiquo.ingestion.invalidation import RevisionInvalidationService
from metiquo.ingestion.local_transports import (
    LocalFixtureTransport,
    MirrorSnapshot,
    MirrorTransport,
    prioritized_transports,
)
from metiquo.ingestion.manifest import build_snapshot_manifest, store_snapshot
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.physical_validation import PhysicalValidationReport, PhysicalValidator
from metiquo.ingestion.promotion import SnapshotPromotionService
from metiquo.ingestion.raw_loader import RawLoadStatistics, RawTabularLoader
from metiquo.ingestion.retry import RetryExecutor
from metiquo.ingestion.safe_download import SafeDownloader, SafeDownloadResult
from metiquo.ingestion.schema_contract import ORACLES_ELIXIR_SCHEMA_V1
from metiquo.ingestion.source_errors import SourceTransportError
from metiquo.ingestion.transport import (
    SourceMetadata,
    SourceRef,
    SourceTransport,
    TransportPolicy,
)


class SyncFailed(RuntimeError):
    """La synchronisation a échoué sans snapshot autorisé par la politique."""

    exit_code = 4

    def __init__(self, message: str, *, error_code: str, run_id: UUID) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.run_id = run_id


@dataclass(frozen=True, slots=True)
class YearSyncReport:
    run_id: UUID
    load_run_id: UUID | None
    snapshot_id: UUID | None
    transport: str | None
    freshness: SourceFreshnessDecision
    load_statistics: RawLoadStatistics | None


class _MirrorResolver:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def latest_validated(self, source: SourceRef) -> MirrorSnapshot | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        Snapshot.year,
                        Snapshot.sha256,
                        Snapshot.byte_size,
                        Snapshot.content_type,
                        Snapshot.validated_at,
                        SourceCatalog.last_confirmed_at,
                    )
                    .join(SourceCatalog, SourceCatalog.current_snapshot_id == Snapshot.id)
                    .where(
                        SourceCatalog.provider == source.provider,
                        SourceCatalog.dataset == "league_of_legends_match_data",
                        SourceCatalog.season_year == source.year,
                        Snapshot.status == "validated",
                    )
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["validated_at"] is None:
            return None
        return MirrorSnapshot(
            year=int(row["year"]),
            sha256=str(row["sha256"]),
            byte_size=int(row["byte_size"]),
            content_type=(str(row["content_type"]) if row["content_type"] else None),
            validated_at=row["validated_at"],
            source_confirmed_at=row["last_confirmed_at"],
        )


class OracleElixirYearSync:
    """Exécuter un sync complet en conservant les frontières mock/réel."""

    def __init__(
        self,
        *,
        engine: Engine,
        settings: Settings,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._clock = clock or SystemClock()
        settings.object_store_root.mkdir(parents=True, exist_ok=True)
        self._store = FilesystemObjectStore(settings.object_store_root / "raw" / "oracles_elixir")
        self._catalog = cast(Table, SourceCatalog.__table__)
        self._runs = cast(Table, IngestionRun.__table__)
        self._snapshots = cast(Table, Snapshot.__table__)
        self._canonical = cast(Table, CanonicalRow.__table__)
        self._quality_issues = cast(Table, PersistedQualityIssue.__table__)

    def sync_year(
        self,
        *,
        year: int,
        policy: FreshnessPolicy,
        fixture_path: Path | None = None,
        run_kind: str = "sync",
        request_key_hash: str | None = None,
    ) -> YearSyncReport:
        catalog = self._catalog_record(year)
        if catalog is None:
            raise SyncFailed(
                "aucune source active pour l'année demandée",
                error_code="SOURCE_CATALOG_MISSING",
                run_id=uuid4(),
            )
        catalog_id = cast(UUID, catalog["id"])
        source = SourceRef(
            provider="oracles_elixir",
            year=year,
            source_id=str(catalog["drive_file_id"]),
            locator=f"https://drive.google.com/file/d/{catalog['drive_file_id']}/view",
            source_name=str(catalog["source_name"]),
            mutable=bool(catalog["mutable"]),
        )
        run_id = self._start_run(catalog_id, run_kind, request_key_hash)
        transport_name: str | None = None
        load_run_id: UUID | None = None
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"metiquo-oe-{year}-",
                dir=self._settings.object_store_root,
            ) as directory:
                working = Path(directory)
                metadata, download = self._download(
                    source=source,
                    destination=working / "source.download",
                    fixture_path=fixture_path,
                )
                transport_name = metadata.transport
                self._set_transport(run_id, transport_name)
                physical = PhysicalValidator().validate(
                    download,
                    previous_validated_size=self._previous_size(catalog_id),
                )
                csv_path = _materialize_csv(download, physical, working)
                rows = _read_rows(csv_path, physical)
                assessment = ORACLES_ELIXIR_SCHEMA_V1.assess(physical.header)
                ORACLES_ELIXIR_SCHEMA_V1.require_ingestable(
                    assessment,
                    transport=metadata.transport,
                    source_id=source.source_id,
                )
                quality = DataQualityValidator(clock=self._clock).validate(
                    rows,
                    previous=self._previous_quality(
                        provider=str(catalog["provider"]),
                        dataset=str(catalog["dataset"]),
                        year=year,
                    ),
                )
                self._persist_quality_issues(run_id, quality)
                DataQualityValidator.require_pass(
                    quality,
                    transport=metadata.transport,
                    source_id=source.source_id,
                )
                manifest = build_snapshot_manifest(
                    source=source,
                    metadata=metadata,
                    download=download,
                    schema=assessment.schema,
                    row_count=quality.row_count,
                    min_event_date=_manifest_date(quality.min_event_date),
                    max_event_date=_manifest_date(quality.max_event_date),
                    quality_status=quality.status,
                    quality={
                        "issues": len(quality.issues),
                        "disabledCapabilities": len(quality.disabled_capabilities),
                    },
                    ingestion_code_version="metiquo-0.1.0",
                )
                stored = store_snapshot(
                    object_store=self._store,
                    download=download,
                    manifest=manifest,
                    schema=assessment.schema,
                )
                promoted = SnapshotPromotionService(
                    engine=self._engine,
                    object_store=self._store,
                    clock=self._clock,
                ).promote(
                    source_catalog_id=catalog_id,
                    run_id=run_id,
                    stored=stored,
                    manifest=manifest,
                )
                load_run_id = self._start_load_run(catalog_id, promoted.snapshot_id)
                loaded = RawTabularLoader(
                    engine=self._engine,
                    clock=self._clock,
                ).load(
                    source_catalog_id=catalog_id,
                    snapshot_id=promoted.snapshot_id,
                    run_id=load_run_id,
                    csv_path=csv_path,
                    encoding=physical.encoding,
                    delimiter=physical.delimiter,
                )
                RevisionInvalidationService(
                    engine=self._engine,
                    clock=self._clock,
                ).emit_for_run(load_run_id)
        except Exception as error:
            error_code = _error_code(error)
            self._fail_run(run_id, error_code)
            if load_run_id is not None:
                self._fail_run(load_run_id, error_code)
            decision = self._freshness(catalog_id, policy)
            if decision.usable:
                return YearSyncReport(
                    run_id=run_id,
                    load_run_id=None,
                    snapshot_id=decision.snapshot_id,
                    transport=transport_name,
                    freshness=decision,
                    load_statistics=None,
                )
            raise SyncFailed(
                "synchronisation Oracle's Elixir échouée",
                error_code=error_code,
                run_id=run_id,
            ) from error
        decision = self._freshness(catalog_id, policy)
        return YearSyncReport(
            run_id=run_id,
            load_run_id=load_run_id,
            snapshot_id=promoted.snapshot_id,
            transport=transport_name,
            freshness=decision,
            load_statistics=loaded.statistics,
        )

    def _download(
        self,
        *,
        source: SourceRef,
        destination: Path,
        fixture_path: Path | None,
    ) -> tuple[SourceMetadata, SafeDownloadResult]:
        transports = self._transports(source, fixture_path)
        last_error: Exception | None = None
        for transport in transports:
            try:
                metadata = RetryExecutor().execute(
                    partial(transport.probe, source),
                    policy=transport.policy.retry,
                )
                download = RetryExecutor().execute(
                    partial(
                        SafeDownloader().download,
                        transport=transport,
                        source=source,
                        destination=destination,
                        expected_sha256=metadata.checksum_sha256,
                    ),
                    policy=transport.policy.retry,
                )
                return metadata, download
            except SourceTransportError as error:
                last_error = error
        if last_error is None:
            raise RuntimeError("aucun transport Oracle's Elixir configuré")
        raise last_error

    def _transports(
        self,
        source: SourceRef,
        fixture_path: Path | None,
    ) -> tuple[SourceTransport, ...]:
        policy = TransportPolicy.from_settings(self._settings)
        public = GoogleDrivePublicHttpTransport(policy=policy, clock=self._clock)
        mirror = MirrorTransport(
            policy=policy,
            object_store=self._store,
            resolver=_MirrorResolver(self._engine),
            clock=self._clock,
        )
        if self._settings.app_data_mode is DataMode.MOCK:
            if fixture_path is None:
                raise ValueError("--fixture est requis pour un sync en mode mock")
            fixture = LocalFixtureTransport(
                policy=policy,
                fixtures={source.source_id: fixture_path},
                data_mode=DataMode.MOCK,
                clock=self._clock,
            )
            result = prioritized_transports(
                data_mode=DataMode.MOCK,
                api=None,
                public_http=public,
                mirror=mirror,
                fixture=fixture,
            )
        else:
            result = prioritized_transports(
                data_mode=DataMode.REAL,
                api=GoogleDriveApiTransport.from_settings(self._settings, clock=self._clock),
                public_http=public,
                mirror=mirror,
            )
        return tuple(result)

    def _catalog_record(self, year: int) -> dict[str, object] | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(self._catalog).where(
                        self._catalog.c.provider == "oracles_elixir",
                        self._catalog.c.dataset == "league_of_legends_match_data",
                        self._catalog.c.season_year == year,
                        self._catalog.c.status == "active",
                    )
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def _start_run(
        self,
        catalog_id: UUID,
        run_kind: str,
        request_key_hash: str | None,
    ) -> UUID:
        if run_kind not in {"sync", "backfill"}:
            raise ValueError("run_kind annuel invalide")
        run_id = uuid4()
        now = self._clock.now().value
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._runs).values(
                    id=run_id,
                    source_catalog_id=catalog_id,
                    run_kind=run_kind,
                    status="running",
                    attempt=1,
                    request_key_hash=request_key_hash,
                    correlation_id=f"oe-{run_kind}-{run_id}",
                    started_at=now,
                    created_at=now,
                )
            )
        return run_id

    def _start_load_run(self, catalog_id: UUID, snapshot_id: UUID) -> UUID:
        run_id = uuid4()
        now = self._clock.now().value
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._runs).values(
                    id=run_id,
                    source_catalog_id=catalog_id,
                    snapshot_id=snapshot_id,
                    run_kind="load",
                    status="running",
                    attempt=1,
                    transport="filesystem",
                    correlation_id=f"oe-load-{run_id}",
                    started_at=now,
                    created_at=now,
                )
            )
        return run_id

    def _fail_run(self, run_id: UUID, error_code: str) -> None:
        now = self._clock.now().value
        with self._engine.begin() as connection:
            connection.execute(
                update(self._runs)
                .where(self._runs.c.id == run_id, self._runs.c.status == "running")
                .values(
                    status="failed",
                    finished_at=now,
                    error_code=error_code[:128],
                    error_detail="synchronisation échouée ; consulter le code structuré",
                )
            )

    def _set_transport(self, run_id: UUID, transport: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(self._runs)
                .where(self._runs.c.id == run_id, self._runs.c.status == "running")
                .values(transport=transport)
            )

    def _previous_size(self, catalog_id: UUID) -> int | None:
        with self._engine.connect() as connection:
            value = connection.execute(
                select(self._snapshots.c.byte_size)
                .join(
                    self._catalog,
                    self._catalog.c.current_snapshot_id == self._snapshots.c.id,
                )
                .where(self._catalog.c.id == catalog_id)
            ).scalar_one_or_none()
        return int(value) if value is not None else None

    def _persist_quality_issues(self, run_id: UUID, report: QualityReport) -> None:
        if not report.issues:
            return
        now = self._clock.now().value
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._quality_issues),
                [
                    {
                        "id": uuid4(),
                        "run_id": run_id,
                        "snapshot_id": None,
                        "code": issue.code.value,
                        "severity": issue.severity,
                        "capability": issue.capability,
                        "row_number": issue.row_number,
                        "natural_key": issue.natural_key,
                        "message": issue.message,
                        "context": dict(issue.context),
                        "created_at": now,
                    }
                    for issue in report.issues
                ],
            )

    def _previous_quality(
        self,
        *,
        provider: str,
        dataset: str,
        year: int,
    ) -> PreviousQualitySummary | None:
        with self._engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    select(self._canonical.c.payload).where(
                        self._canonical.c.provider == provider,
                        self._canonical.c.dataset == dataset,
                        func.extract("year", self._canonical.c.event_date) == year,
                    )
                ).scalars()
            )
        natural_keys = frozenset(
            f"{row.get('gameid', '')}:{row.get('participantid', '')}" for row in rows
        )
        return (
            PreviousQualitySummary(row_count=len(rows), natural_keys=natural_keys) if rows else None
        )

    def _freshness(
        self,
        catalog_id: UUID,
        policy: FreshnessPolicy,
    ) -> SourceFreshnessDecision:
        return FreshnessService.from_settings(
            repository=PostgresFreshnessRepository(self._engine),
            settings=self._settings,
            clock=self._clock,
        ).evaluate(catalog_id, policy=policy)


def _materialize_csv(
    download: SafeDownloadResult,
    physical: PhysicalValidationReport,
    working: Path,
) -> Path:
    if physical.compression == "none":
        return download.final_path
    target = working / "source.csv"
    if physical.compression == "gzip":
        with gzip.open(download.final_path, "rb") as source, target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        return target
    with zipfile.ZipFile(download.final_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        with archive.open(members[0]) as source, target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
    return target


def _read_rows(path: Path, physical: PhysicalValidationReport) -> list[dict[str, str]]:
    with path.open("r", encoding=physical.encoding, newline="") as stream:
        return list(csv.DictReader(stream, delimiter=physical.delimiter))


def _manifest_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(datetime.fromisoformat(value).date(), time.min, UTC)


def _error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    return str(code) if code is not None else type(error).__name__.upper()
