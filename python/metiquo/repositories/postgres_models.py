"""Projections publiques du registre ML et de ses mutations réelles."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select

from metiquo.contracts import AuditEntry, BacktestSummary, JobSummary, ModelSummary
from metiquo.contracts.enums import BacktestKind, DataMode, GameTitle, MarketType, ModelStatus
from metiquo.db.ml_models import BaselineRun
from metiquo.db.ml_models import ModelActionAudit as ModelActionAuditRow
from metiquo.db.ml_models import ModelActionJob as ModelActionJobRow
from metiquo.db.ml_models import ModelVersion as ModelVersionRow

_PUBLIC_METRICS = {
    "brier_score": "brier",
    "calibration_ece": "calibration_ece",
    "log_loss": "log_loss",
}


class PostgresModelRepository:
    """Lire les modèles, backtests, jobs et audits sans inventer de résultat."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_models(self) -> tuple[ModelSummary, ...]:
        models = cast(Table, ModelVersionRow.__table__)
        with self.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    select(models).order_by(models.c.registered_at.desc())
                ).mappings()
            )
            baselines = self._baseline_metrics(connection, rows)
        return tuple(
            self._model(row, baselines.get(cast(UUID, row["dataset_id"]), {})) for row in rows
        )

    def get_model(self, model_version_id: UUID) -> ModelSummary | None:
        models = cast(Table, ModelVersionRow.__table__)
        with self.engine.connect() as connection:
            row = (
                connection.execute(select(models).where(models.c.id == model_version_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            baseline = self._baseline_metrics(connection, (row,)).get(
                cast(UUID, row["dataset_id"]), {}
            )
        return self._model(row, baseline)

    def list_backtests(self) -> tuple[BacktestSummary, ...]:
        models = cast(Table, ModelVersionRow.__table__)
        with self.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    select(models).order_by(models.c.registered_at.desc())
                ).mappings()
            )
            baselines = self._baseline_metrics(connection, rows)
        return tuple(
            self._backtest(row, baselines.get(cast(UUID, row["dataset_id"]), {})) for row in rows
        )

    def get_backtest(self, backtest_id: UUID) -> BacktestSummary | None:
        return next(
            (item for item in self.list_backtests() if item.backtest_id == backtest_id),
            None,
        )

    def list_jobs(self) -> tuple[JobSummary, ...]:
        jobs = cast(Table, ModelActionJobRow.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(select(jobs).order_by(jobs.c.updated_at.desc())).mappings()
            return tuple(
                JobSummary(
                    job_id=cast(UUID, row["id"]),
                    name=cast(str, row["name"]),
                    status=cast(
                        Literal["idle", "succeeded", "failed", "running"],
                        row["status"],
                    ),
                    last_run_at=row["finished_at"] or row["updated_at"],
                    data_mode=DataMode.REAL,
                )
                for row in rows
            )

    def list_audit(self) -> tuple[AuditEntry, ...]:
        audits = cast(Table, ModelActionAuditRow.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(audits).order_by(audits.c.occurred_at.desc())
            ).mappings()
            return tuple(
                AuditEntry(
                    audit_id=cast(UUID, row["id"]),
                    action=cast(str, row["action"]),
                    resource_id=cast(str, row["resource_id"]),
                    idempotency_fingerprint=cast(str, row["idempotency_fingerprint"]),
                    occurred_at=row["occurred_at"],
                    data_mode=DataMode.REAL,
                )
                for row in rows
            )

    @staticmethod
    def version(model_version_id: UUID) -> str:
        """Le nom public est l'identifiant exact, aussi persisté avec chaque prédiction."""

        return str(model_version_id)

    @staticmethod
    def _model(row: RowMapping, baseline_metrics: Mapping[str, Decimal]) -> ModelSummary:
        status = ModelStatus(cast(str, row["status"]))
        model_version_id = cast(UUID, row["id"])
        promoted_at = row["status_changed_at"] if status is ModelStatus.CHAMPION else None
        promotion_reason = cast(str, row["status_reason"]) if promoted_at is not None else None
        return ModelSummary(
            model_version_id=model_version_id,
            model_version=PostgresModelRepository.version(model_version_id),
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
            market_type=MarketType.MATCH_WINNER,
            algorithm=cast(str, row["algorithm"]),
            feature_version=cast(str, row["feature_set_version"]),
            dataset_hash=cast(str, row["dataset_hash"]),
            artifact_hash=cast(str, row["artifact_hash"]),
            code_commit=cast(str, row["code_commit"]),
            train_cutoff=row["training_cutoff_max"],
            status=status,
            metrics=_report_metrics(cast(Mapping[str, object], row["evaluation_report"])),
            baseline_metrics=dict(baseline_metrics),
            created_at=row["registered_at"],
            promoted_at=promoted_at,
            promotion_reason=promotion_reason,
        )

    @staticmethod
    def _backtest(row: RowMapping, baseline_metrics: Mapping[str, Decimal]) -> BacktestSummary:
        report = cast(Mapping[str, object], row["evaluation_report"])
        fingerprint = cast(str, row["evaluation_report_fingerprint"])
        return BacktestSummary(
            backtest_id=uuid5(NAMESPACE_URL, f"metiquo:evaluation-report:{fingerprint}"),
            model_version_id=cast(UUID, row["id"]),
            kind=BacktestKind.STATISTICAL,
            starts_at=row["training_cutoff_min"],
            ends_at=row["training_cutoff_max"],
            sample_count=_sample_count(report),
            metrics=_report_metrics(report),
            baseline_metrics=dict(baseline_metrics),
            observed_odds_count=_integer(report.get("observed_odds_count")),
            uses_only_observed_odds=False,
            final_test_untouched=report.get("evaluation_split")
            in {"calibration_oos", "oof_validation"},
            completed_at=row["registered_at"],
        )

    @staticmethod
    def _baseline_metrics(
        connection: Connection,
        model_rows: tuple[RowMapping, ...],
    ) -> dict[UUID, dict[str, Decimal]]:
        dataset_ids = {cast(UUID, row["dataset_id"]) for row in model_rows}
        if not dataset_ids:
            return {}
        baselines = cast(Table, BaselineRun.__table__)
        rows = connection.execute(
            select(baselines.c.dataset_id, baselines.c.metrics).where(
                baselines.c.dataset_id.in_(dataset_ids)
            )
        ).mappings()
        candidates: dict[UUID, dict[str, list[Decimal]]] = {}
        for row in rows:
            dataset_id = cast(UUID, row["dataset_id"])
            metrics = cast(Mapping[str, object], row["metrics"])
            values = candidates.setdefault(dataset_id, {})
            for source, public in _PUBLIC_METRICS.items():
                raw = metrics.get(source)
                if source == "calibration_ece" and raw is None:
                    calibration = metrics.get("calibration")
                    if isinstance(calibration, Mapping):
                        raw = calibration.get("ece")
                if raw is not None:
                    values.setdefault(public, []).append(Decimal(str(raw)))
        return {
            dataset_id: {name: min(values) for name, values in metrics.items() if values}
            for dataset_id, metrics in candidates.items()
        }


def _overall(report: Mapping[str, object]) -> Mapping[str, object]:
    value = report.get("overall")
    return value if isinstance(value, Mapping) else {}


def _report_metrics(report: Mapping[str, object]) -> dict[str, Decimal]:
    overall = _overall(report)
    values: dict[str, Decimal] = {}
    for source, public in _PUBLIC_METRICS.items():
        raw = overall.get(source)
        if raw is not None:
            values[public] = Decimal(str(raw))
    return values


def _sample_count(report: Mapping[str, object]) -> int:
    return _integer(_overall(report).get("sample_count"))


def _integer(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return 0
