import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID, uuid4

import psycopg
from metiquo_core.config import Settings
from metiquo_core.models import Dataset, DatasetVersion, IngestionRun
from psycopg.types.json import Jsonb
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from metiquo_worker.archive import (
    ValidatedFile,
    csv_records,
    download_export,
    persist_artifact,
    validate_archive,
)
from metiquo_worker.jobs import CollectionBusy as CollectionBusy
from metiquo_worker.jobs import source_lock
from metiquo_worker.oracle_match_sync import sync_oracle_match_details
from metiquo_worker.sources.oracle import discover, export_url, select_files
from metiquo_worker.worker_logs import emit, error_context

SOURCE = "oracles-elixir"
LOCK_ID = 7_346_810_205
logger = logging.getLogger(__name__)


@contextmanager
def collection_lock(engine: Engine) -> Iterator[None]:
    with source_lock(engine, LOCK_ID):
        yield


def import_files(
    session: Session, files: list[ValidatedFile], root: Path, run_id: UUID
) -> dict[str, object]:
    """COPY and all active pointers commit together, only after every archive member validates."""
    imported = 0
    unchanged = 0
    now = datetime.now(UTC)
    for file in files:
        dataset_id = f"{SOURCE}:{file.source.year}"
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            dataset = Dataset(
                id=dataset_id,
                source=SOURCE,
                source_file_id=file.source.id,
                filename=file.source.name,
                file_year=file.source.year,
                checked_at=now,
            )
            session.add(dataset)
        else:
            dataset.source_file_id = file.source.id
            dataset.filename = file.source.name
            dataset.checked_at = now
        session.flush()
        stored = persist_artifact(file, root)
        version = session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id, DatasetVersion.sha256 == file.sha256
            )
        )
        if version is None:
            version = DatasetVersion(
                id=uuid4(),
                dataset_id=dataset_id,
                run_id=run_id,
                sha256=file.sha256,
                artifact_path=stored,
                byte_count=file.byte_count,
                row_count=file.row_count,
                columns=file.columns,
                retrieved_at=now,
            )
            session.add(version)
            session.flush()
            raw = cast(
                psycopg.Connection[tuple[object, ...]],
                session.connection().connection.driver_connection,
            )
            with (
                raw.cursor() as cursor,
                cursor.copy(
                    "COPY oracle_rows (version_id, row_number, game_id, participant_id, payload) "
                    "FROM STDIN"
                ) as copy,
            ):
                for index, row in enumerate(csv_records(file.path), start=1):
                    copy.write_row(
                        (version.id, index, row["gameid"], row["participantid"], Jsonb(row))
                    )
            imported += 1
            logger.info("Imported year %s: %s rows", file.source.year, file.row_count)
        else:
            unchanged += 1
        dataset.active_version_id = version.id
    return {"imported": imported, "unchanged": unchanged, "years": [f.source.year for f in files]}


def collect(
    engine: Engine, settings: Settings, years: set[int] | None = None, *, latest: bool = False
) -> UUID:
    if not settings.oracle_enabled:
        raise ValueError("Oracle collection is disabled")
    if latest and years is not None:
        raise ValueError("Choose either latest or explicit years")
    with collection_lock(engine):
        run_id = uuid4()
        with Session(engine) as session, session.begin():
            session.execute(
                update(IngestionRun)
                .where(IngestionRun.source == SOURCE, IngestionRun.status == "running")
                .values(status="interrupted", finished_at=func.now(), error="Worker interrupted")
            )
            session.add(
                IngestionRun(
                    id=run_id,
                    source=SOURCE,
                    scope="latest"
                    if latest
                    else "all"
                    if years is None
                    else ",".join(str(year) for year in sorted(years)),
                )
            )
        stage = "discovery"
        try:
            inventory = discover(settings)
            if latest:
                years = {max(file.year for file in inventory)}
            selected = select_files(inventory, years)
            stage = "export"
            url = export_url(settings, selected)
            with TemporaryDirectory(prefix="metiquo-oracle-") as directory:
                temporary = Path(directory)
                archive = temporary / "export.zip"
                stage = "download"
                download_export(url, archive, settings.oracle_max_archive_bytes)
                logger.info("Archive downloaded: %s bytes", archive.stat().st_size)
                stage = "validation"
                files = validate_archive(
                    archive, selected, temporary, settings.oracle_max_expanded_bytes
                )
                stage = "database import"
                with Session(engine) as session, session.begin():
                    details = import_files(session, files, settings.artifact_dir, run_id)
                    session.execute(
                        update(IngestionRun)
                        .where(IngestionRun.id == run_id)
                        .values(
                            status="succeeded",
                            finished_at=func.now(),
                            details=details,
                        )
                    )
                logger.info("Collection %s succeeded: %s", run_id, details)
            try:
                match_details = sync_oracle_match_details(
                    engine, source_timezone=settings.oracle_date_timezone
                )
            except Exception as error:
                match_details = {"status": "failed", "error": type(error).__name__}
                logger.exception("Oracle match detail projection failed")
                emit(
                    engine,
                    settings.worker_status_id,
                    "oracle_projection_failed",
                    context=error_context(error),
                )
            details = {**details, "matchDetails": match_details}
            with Session(engine) as session, session.begin():
                session.execute(
                    update(IngestionRun).where(IngestionRun.id == run_id).values(details=details)
                )
            return run_id
        except Exception as error:
            emit(
                engine,
                settings.worker_status_id,
                "collector_interrupted",
                context={**error_context(error), "step": stage},
            )
            # Browser/HTTP exception strings can contain signed URLs; persist only a safe category.
            message = f"{stage}: {type(error).__name__}"
            diagnostic = re.sub(r"https?://\S+", "[URL]", str(error)).split("Call log:")[0][:1000]
            with Session(engine) as session, session.begin():
                session.execute(
                    update(IngestionRun)
                    .where(IngestionRun.id == run_id)
                    .values(
                        status="failed",
                        finished_at=func.now(),
                        error=message,
                    )
                )
            logger.error("Collection %s failed during %s", run_id, message)
            if diagnostic:
                logger.error("Collection diagnostic: %s", diagnostic)
            raise RuntimeError(message) from None
