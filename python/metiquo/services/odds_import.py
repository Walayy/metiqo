"""Import opérateur : document validé, archivé, puis publié atomiquement."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from metiquo.config import ObjectStoreBackend, Settings
from metiquo.contracts.enums import DataMode, GameTitle
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.providers import ManualImportOddsProvider
from metiquo.providers.manual_import import ManualImportFormat
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource

MAX_IMPORT_BYTES = 10 * 1024 * 1024


def import_odds_file(
    engine: Engine,
    settings: Settings,
    path: Path,
    provider_code: str,
    document_format: ManualImportFormat,
    *,
    clock: Clock | None = None,
) -> dict[str, object]:
    """Conserver les octets source et les cotes sans inventer de mapping canonique."""

    if settings.app_data_mode is not DataMode.REAL:
        raise ValueError("odds-import exige APP_DATA_MODE=real")
    if settings.object_store_backend is not ObjectStoreBackend.FILESYSTEM:
        raise ValueError("odds-import exige OBJECT_STORE_BACKEND=filesystem")
    if not provider_code or len(provider_code) > 64 or provider_code != provider_code.strip():
        raise ValueError(
            "Le code fournisseur doit contenir 1 à 64 caractères sans espaces externes"
        )
    with path.open("rb") as stream:
        payload = stream.read(MAX_IMPORT_BYTES + 1)
    if len(payload) > MAX_IMPORT_BYTES:
        raise ValueError("Le document de cotes dépasse 10 Mio")
    clock = clock or SystemClock()
    provider = ManualImportOddsProvider(provider_code, clock=clock)
    result = provider.import_document(payload, document_format=document_format)
    if not result.committed:
        issues = "; ".join(
            f"ligne {issue.row_number}: {issue.code} ({issue.field or 'document'})"
            for issue in result.issues[:20]
        )
        raise ValueError(f"Document de cotes refusé : {issues}")
    events = provider.list_events(
        datetime.min.replace(tzinfo=UTC),
        datetime.max.replace(tzinfo=UTC),
        GameTitle.LEAGUE_OF_LEGENDS,
    )
    stored = FilesystemObjectStore(settings.object_store_root / "odds").put_source(
        year=clock.now().value.year,
        chunks=(payload,),
        source_kind="csv" if document_format == "csv" else "bin",
    )
    source = OddsCaptureSource(
        "manual_import", provider_code, f"odds/{stored.object_key}", stored.sha256
    )
    service = OddsCaptureService(engine, clock)
    with engine.begin() as connection:
        reports = tuple(
            service.capture_event(provider, event, source, connection=connection)
            for event in events
        )
    return {
        "command": "odds-import",
        "provider": provider_code,
        "collectionMode": "manual_import",
        "rawPayloadReference": source.raw_payload_reference,
        "rawPayloadSha256": stored.sha256,
        "events": len(reports),
        "receivedSnapshots": sum(report.received_snapshots for report in reports),
        "insertedSnapshots": sum(report.inserted_snapshots for report in reports),
        "duplicateSnapshots": sum(report.duplicate_snapshots for report in reports),
    }
