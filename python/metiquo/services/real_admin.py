"""Actions d'administration réelles, idempotentes et limitées à Oracle's Elixir."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select, update
from sqlalchemy.dialects.postgresql import insert

from metiquo.config import Settings
from metiquo.contracts import IngestionRunSummary, ModelSummary
from metiquo.contracts.enums import DataMode, GameTitle, MarketType
from metiquo.db.ml_models import CalibratorArtifact, TabularBenchmarkRun
from metiquo.db.ml_models import ModelActionAudit as ModelActionAuditRow
from metiquo.db.ml_models import ModelActionJob as ModelActionJobRow
from metiquo.db.ml_models import ModelVersion as ModelVersionRow
from metiquo.db.raw_models import IngestionRun
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.freshness import FreshDataRequired, FreshnessPolicy
from metiquo.ingestion.sync import OracleElixirYearSync, SyncFailed
from metiquo.models import ModelLifecycle, PromotionEvidence
from metiquo.models.baselines import COMPETITION_PRIOR, RATING, RECENT_FORM
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_models import PostgresModelRepository


class RealModelTrainingWorkflow(Protocol):
    """Frontière vers le workflow reproductible livré par le gate ML-017."""

    def train(self, game_title: GameTitle, market_type: MarketType) -> UUID: ...


@dataclass(frozen=True, slots=True)
class RealAdminMutationService:
    """Déclencher un sync sans autoriser de fixture ni de provider alternatif."""

    engine: Engine
    settings: Settings
    repository: PostgresAdminRepository
    model_repository: PostgresModelRepository | None = None
    training_workflow: RealModelTrainingWorkflow | None = None
    clock: Clock | None = None

    def __post_init__(self) -> None:
        if self.settings.app_data_mode is not DataMode.REAL:
            raise ValueError("RealAdminMutationService exige APP_DATA_MODE=real")
        if self.model_repository is None:
            object.__setattr__(self, "model_repository", PostgresModelRepository(self.engine))
        if self.clock is None:
            object.__setattr__(self, "clock", SystemClock())

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

    def train(
        self,
        idempotency_key: str,
        game_title: GameTitle,
        market_type: MarketType,
    ) -> ModelSummary:
        """Exécuter le workflow réel, puis publier le candidat produit."""

        job = self._start_model_job(
            action="train",
            idempotency_key=idempotency_key,
            payload={"gameTitle": game_title.value, "marketType": market_type.value},
            requested_resource=f"{game_title.value}:{market_type.value}",
        )
        completed = self._completed_model(job)
        if completed is not None:
            return completed
        if self.training_workflow is None:
            error = BusinessError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Le workflow d'entraînement réel n'est pas configuré",
                retryable=True,
            )
            self._fail_model_job(job, error)
            raise error
        try:
            model_version_id = self.training_workflow.train(game_title, market_type)
            return self._succeed_model_job(job, model_version_id)
        except BusinessError as error:
            self._fail_model_job(job, error)
            raise
        except (RuntimeError, ValueError) as error:
            failure = BusinessError(
                ErrorCode.INVALID_STATE,
                "L'entraînement réel n'a pas produit de candidat valide",
                context={"reason": str(error)},
            )
            self._fail_model_job(job, failure)
            raise failure from error

    def promote(self, idempotency_key: str, model_version_id: UUID, reason: str) -> ModelSummary:
        """Promouvoir seulement si le benchmark enregistré satisfait encore le gate."""

        job = self._start_model_job(
            action="promote",
            idempotency_key=idempotency_key,
            payload={"modelVersionId": str(model_version_id), "reason": reason},
            requested_resource=str(model_version_id),
        )
        completed = self._completed_model(job)
        if completed is not None:
            return completed
        try:
            evidence = self._promotion_evidence(model_version_id, idempotency_key)
            ModelLifecycle(engine=self.engine, clock=self.clock).promote(
                model_version_id,
                actor="api-admin",
                reason=reason,
                evidence=evidence,
            )
            return self._succeed_model_job(job, model_version_id)
        except BusinessError as error:
            self._fail_model_job(job, error)
            raise
        except ValueError as error:
            failure = BusinessError(
                ErrorCode.INVALID_STATE,
                "La promotion du modèle est interdite",
                context={"reason": str(error), "modelVersionId": str(model_version_id)},
            )
            self._fail_model_job(job, failure)
            raise failure from error

    def retire(self, idempotency_key: str, model_version_id: UUID, reason: str) -> ModelSummary:
        """Retirer une version active et conserver la transition auditée."""

        job = self._start_model_job(
            action="retire",
            idempotency_key=idempotency_key,
            payload={"modelVersionId": str(model_version_id), "reason": reason},
            requested_resource=str(model_version_id),
        )
        completed = self._completed_model(job)
        if completed is not None:
            return completed
        try:
            ModelLifecycle(engine=self.engine, clock=self.clock).retire(
                model_version_id,
                actor="api-admin",
                reason=reason,
            )
            return self._succeed_model_job(job, model_version_id)
        except BusinessError as error:
            self._fail_model_job(job, error)
            raise
        except ValueError as error:
            failure = BusinessError(
                ErrorCode.INVALID_STATE,
                "Le retrait du modèle est interdit",
                context={"reason": str(error), "modelVersionId": str(model_version_id)},
            )
            self._fail_model_job(job, failure)
            raise failure from error

    def _promotion_evidence(
        self,
        model_version_id: UUID,
        idempotency_key: str,
    ) -> PromotionEvidence:
        models = cast(Table, ModelVersionRow.__table__)
        calibrators = cast(Table, CalibratorArtifact.__table__)
        benchmarks = cast(Table, TabularBenchmarkRun.__table__)
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        models.c.evaluation_report,
                        models.c.evaluation_report_fingerprint,
                        benchmarks.c.promotion_gate,
                        benchmarks.c.promotable,
                    )
                    .join(
                        calibrators,
                        calibrators.c.id == models.c.calibrator_artifact_id,
                    )
                    .join(benchmarks, benchmarks.c.id == calibrators.c.benchmark_run_id)
                    .where(models.c.id == model_version_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                "Modèle ou benchmark de promotion introuvable",
                context={"modelVersionId": str(model_version_id)},
            )
        gate = cast(dict[str, object], row["promotion_gate"])
        comparisons = gate.get("comparisons")
        if (
            not row["promotable"]
            or gate.get("promotable") is not True
            or not isinstance(comparisons, list)
        ):
            raise BusinessError(
                ErrorCode.INVALID_STATE,
                "Le gate de promotion du modèle a échoué",
                context={"failures": json.dumps(gate.get("failures", []))},
            )
        deltas: dict[str, Decimal] = {}
        for item in comparisons:
            if not isinstance(item, dict) or item.get("passed") is not True:
                continue
            name = item.get("baseline_name")
            gain = item.get("log_loss_gain")
            if isinstance(name, str) and gain is not None:
                deltas[name] = Decimal(str(gain))
        required = {COMPETITION_PRIOR, RECENT_FORM, RATING}
        if set(deltas) != required or any(value <= 0 for value in deltas.values()):
            raise BusinessError(
                ErrorCode.INVALID_STATE,
                "Le modèle ne bat pas les trois baselines requises",
            )
        report = cast(dict[str, object], row["evaluation_report"])
        overall = report.get("overall")
        policy = report.get("promotion_policy")
        if not isinstance(overall, dict) or not isinstance(policy, dict):
            raise BusinessError(ErrorCode.INVALID_STATE, "Le rapport de promotion est incomplet")
        ordered_metrics = tuple(
            name
            for name in (
                *cast(list[object], policy.get("primary_metrics", [])),
                *cast(list[object], policy.get("guard_metrics", [])),
            )
            if isinstance(name, str) and overall.get(name) is not None
        )
        return PromotionEvidence(
            evaluation_report_fingerprint=cast(str, row["evaluation_report_fingerprint"]),
            baseline_log_loss_deltas=deltas,
            metric_basis=ordered_metrics,
            manual_approval_reference=f"api:{hashlib.sha256(idempotency_key.encode()).hexdigest()}",
        )

    def _start_model_job(
        self,
        *,
        action: str,
        idempotency_key: str,
        payload: dict[str, object],
        requested_resource: str,
    ) -> RowMapping:
        jobs = cast(Table, ModelActionJobRow.__table__)
        audits = cast(Table, ModelActionAuditRow.__table__)
        idempotency_fingerprint = hashlib.sha256(idempotency_key.strip().encode()).hexdigest()
        request_document = {
            "action": action,
            "idempotency_fingerprint": idempotency_fingerprint,
            "payload": payload,
        }
        request_fingerprint = hashlib.sha256(
            json.dumps(request_document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        job_id = uuid5(NAMESPACE_URL, f"metiquo:model-action-job:{request_fingerprint}")
        audit_id = uuid5(NAMESPACE_URL, f"metiquo:model-action-audit:{request_fingerprint}")
        now = cast(Clock, self.clock).now().value
        with self.engine.begin() as connection:
            inserted_id = connection.execute(
                insert(jobs)
                .values(
                    id=job_id,
                    name=f"model-{action}-{job_id.hex[:8]}",
                    action=action,
                    request_fingerprint=request_fingerprint,
                    idempotency_fingerprint=idempotency_fingerprint,
                    request_payload=payload,
                    model_version_id=None,
                    status="running",
                    result_payload={},
                    error_payload={},
                    created_at=now,
                    updated_at=now,
                    finished_at=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[jobs.c.action, jobs.c.idempotency_fingerprint]
                )
                .returning(jobs.c.id)
            ).scalar_one_or_none()
            if inserted_id is None:
                row = (
                    connection.execute(
                        select(jobs).where(
                            jobs.c.action == action,
                            jobs.c.idempotency_fingerprint == idempotency_fingerprint,
                        )
                    )
                    .mappings()
                    .one()
                )
                if row["request_fingerprint"] != request_fingerprint:
                    raise BusinessError(
                        ErrorCode.CONFLICT,
                        "Idempotency-Key déjà utilisée avec une autre requête",
                    )
                if row["status"] == "running":
                    raise BusinessError(
                        ErrorCode.CONFLICT,
                        "Le job modèle idempotent est déjà en cours",
                        context={"jobId": str(row["id"])},
                        retryable=True,
                    )
                return row
            connection.execute(
                insert(audits)
                .values(
                    id=audit_id,
                    job_id=job_id,
                    action=f"model.{action}",
                    resource_id=requested_resource,
                    idempotency_fingerprint=idempotency_fingerprint,
                    occurred_at=now,
                )
                .on_conflict_do_nothing(index_elements=[audits.c.job_id])
            )
            return connection.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one()

    def _completed_model(self, job: RowMapping) -> ModelSummary | None:
        if job["status"] == "failed":
            error = cast(dict[str, object], job["error_payload"])
            raise BusinessError(
                ErrorCode(cast(str, error.get("code", ErrorCode.INVALID_STATE.value))),
                cast(str, error.get("detail", "Le job modèle a échoué")),
            )
        if job["status"] != "succeeded":
            return None
        model_id = cast(UUID | None, job["model_version_id"])
        model = (
            cast(PostgresModelRepository, self.model_repository).get_model(model_id)
            if model_id
            else None
        )
        if model is None:
            raise BusinessError(
                ErrorCode.INVALID_STATE, "Le résultat du job modèle est introuvable"
            )
        return model

    def _succeed_model_job(self, job: RowMapping, model_version_id: UUID) -> ModelSummary:
        repository = cast(PostgresModelRepository, self.model_repository)
        model = repository.get_model(model_version_id)
        if model is None:
            raise BusinessError(
                ErrorCode.INVALID_STATE,
                "Le workflow n'a pas enregistré la version de modèle annoncée",
            )
        jobs = cast(Table, ModelActionJobRow.__table__)
        now = cast(Clock, self.clock).now().value
        with self.engine.begin() as connection:
            connection.execute(
                update(jobs)
                .where(jobs.c.id == job["id"])
                .values(
                    model_version_id=model_version_id,
                    status="succeeded",
                    result_payload={"modelVersionId": str(model_version_id)},
                    error_payload={},
                    updated_at=now,
                    finished_at=now,
                )
            )
        return model

    def _fail_model_job(self, job: RowMapping, error: BusinessError) -> None:
        jobs = cast(Table, ModelActionJobRow.__table__)
        now = cast(Clock, self.clock).now().value
        with self.engine.begin() as connection:
            connection.execute(
                update(jobs)
                .where(jobs.c.id == job["id"])
                .values(
                    status="failed",
                    result_payload={},
                    error_payload={"code": error.code.value, "detail": error.message},
                    updated_at=now,
                    finished_at=now,
                )
            )
