"""Actions d'administration réelles, idempotentes et limitées à Oracle's Elixir."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, Table, select

from metiquo.config import Settings
from metiquo.contracts import IngestionRunSummary
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import IngestionRun
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.ingestion.freshness import FreshDataRequired, FreshnessPolicy
from metiquo.ingestion.sync import OracleElixirYearSync, SyncFailed
from metiquo.repositories.postgres_admin import PostgresAdminRepository


@dataclass(frozen=True, slots=True)
class RealAdminMutationService:
    """Déclencher un sync sans autoriser de fixture ni de provider alternatif."""

    engine: Engine
    settings: Settings
    repository: PostgresAdminRepository

    def __post_init__(self) -> None:
        if self.settings.app_data_mode is not DataMode.REAL:
            raise ValueError("RealAdminMutationService exige APP_DATA_MODE=real")

    def sync(self, idempotency_key: str, year: int | None = None) -> IngestionRunSummary:
        selected_year = year if year is not None else self.settings.oe_current_year
        request_hash = hashlib.sha256(
            f"real.oe.sync\0{selected_year}\0{idempotency_key}".encode()
        ).hexdigest()
        existing = self._existing(request_hash)
        if existing is not None:
            summary = self.repository.get_ingestion_run(existing)
            if summary is None:
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "La synchronisation idempotente est encore en cours",
                    context={"year": selected_year},
                )
            return summary
        try:
            report = OracleElixirYearSync(
                engine=self.engine,
                settings=self.settings,
            ).sync_year(
                year=selected_year,
                policy=FreshnessPolicy.from_settings(self.settings),
                request_key_hash=request_hash,
            )
        except FreshDataRequired as error:
            raise BusinessError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Aucun snapshot Oracle's Elixir frais n'est disponible",
                retryable=True,
                context={"reasonCode": error.decision.reason_code, "year": selected_year},
            ) from error
        except SyncFailed as error:
            raise BusinessError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "La source Oracle's Elixir ne répond pas aux critères d'ingestion",
                retryable=True,
                context={"reasonCode": error.error_code, "year": selected_year},
            ) from error
        summary = self.repository.get_ingestion_run(report.run_id)
        if summary is None:
            raise BusinessError(
                ErrorCode.INVALID_STATE,
                "Le résultat de synchronisation n'est pas observable",
                context={"runId": str(report.run_id)},
            )
        return summary

    def _existing(self, request_hash: str) -> UUID | None:
        runs = cast(Table, IngestionRun.__table__)
        with self.engine.connect() as connection:
            value = connection.execute(
                select(runs.c.id).where(runs.c.request_key_hash == request_hash)
            ).scalar_one_or_none()
        return cast(UUID | None, value)
