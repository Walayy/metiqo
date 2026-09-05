"""Projection publique des signaux PostgreSQL en opportunités contractuelles."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.sql import Select

from metiquo.contracts import (
    ContractMetadata,
    Market,
    OddsSnapshot,
    Opportunity,
    Prediction,
    Quality,
    Value,
)
from metiquo.contracts.enums import (
    AbstentionReason,
    DataMode,
    FreshnessStatus,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ModelStatus,
    ProviderStatus,
    SelectionType,
    ValueGrade,
)
from metiquo.db.ml_models import ModelVersion, PrematchPrediction
from metiquo.db.odds_models import (
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsMarket,
)
from metiquo.db.pricing_models import SignalRecord
from metiquo.foundation.time import Clock, SystemClock
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.repositories.postgres_models import PostgresModelRepository

_OPPORTUNITY_GRADES = frozenset(
    (ValueGrade.STRONG_VALUE.value, ValueGrade.VALUE.value, ValueGrade.WATCH.value)
)


class PostgresOpportunityRepository:
    """Lire les signaux sans reclasser ni compléter artificiellement leurs preuves."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self.clock = clock or SystemClock()
        self._events = PostgresCanonicalRepository(engine, self.clock)

    def list(self, *, include_diagnostics: bool = False) -> tuple[Opportunity, ...]:
        statement = self._statement().order_by(
            SignalRecord.__table__.c.conservative_expected_value.desc(),
            SignalRecord.__table__.c.computed_at.desc(),
            SignalRecord.__table__.c.id,
        )
        if not include_diagnostics:
            statement = statement.where(SignalRecord.__table__.c.grade.in_(_OPPORTUNITY_GRADES))
        with self.engine.connect() as connection:
            rows = tuple(connection.execute(statement).mappings())
        return tuple(
            opportunity for row in rows if (opportunity := self._opportunity(row)) is not None
        )

    def get(self, signal_id: UUID) -> Opportunity | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    self._statement().where(SignalRecord.__table__.c.id == signal_id)
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else self._opportunity(row)

    @staticmethod
    def _statement() -> Select[tuple[Any, ...]]:
        signals = cast(Table, SignalRecord.__table__)
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        providers = cast(Table, OddsProviderRecord.__table__)
        markets = cast(Table, ProviderOddsMarket.__table__)
        predictions = cast(Table, PrematchPrediction.__table__)
        models = cast(Table, ModelVersion.__table__)
        return (
            select(
                signals.c.id.label("signal_id"),
                signals.c.odds_snapshot_id,
                signals.c.selection_type,
                signals.c.policy_version,
                signals.c.offered_odds,
                signals.c.raw_implied_probability,
                signals.c.model_probability,
                signals.c.model_probability_low,
                signals.c.model_probability_high,
                signals.c.no_vig_probability,
                signals.c.fair_odds,
                signals.c.edge,
                signals.c.expected_value,
                signals.c.conservative_expected_value,
                signals.c.grade,
                signals.c.abstention_reasons,
                signals.c.mapping_confidence,
                signals.c.source_freshness,
                signals.c.odds_age_seconds,
                signals.c.computed_at,
                signals.c.signal_fingerprint,
                snapshots.c.market_id,
                snapshots.c.provider_status,
                snapshots.c.market_status,
                snapshots.c.captured_at,
                snapshots.c.informational_only,
                snapshots.c.provenance_reference,
                providers.c.code.label("provider_code"),
                markets.c.period,
                markets.c.line,
                markets.c.settlement_rules_version,
                predictions.c.id.label("prediction_id"),
                predictions.c.event_id,
                predictions.c.feature_snapshot_id,
                predictions.c.model_version_id,
                predictions.c.cutoff_at,
                predictions.c.predicted_at,
                predictions.c.confidence,
                predictions.c.data_coverage,
                predictions.c.out_of_distribution_distance,
                predictions.c.reason_codes,
                models.c.status.label("model_status"),
            )
            .select_from(
                signals.join(snapshots, snapshots.c.id == signals.c.odds_snapshot_id)
                .join(providers, providers.c.id == snapshots.c.provider_id)
                .join(markets, markets.c.id == snapshots.c.market_id)
                .join(predictions, predictions.c.id == signals.c.prediction_id)
                .join(models, models.c.id == predictions.c.model_version_id)
            )
            .where(
                signals.c.value_computed.is_(True),
                signals.c.fair_odds.is_not(None),
                predictions.c.data_coverage.is_not(None),
                predictions.c.out_of_distribution_distance.is_not(None),
                snapshots.c.captured_at.is_not(None),
            )
        )

    def _opportunity(self, row: RowMapping) -> Opportunity | None:
        event = self._events.get(cast(UUID, row["event_id"]))
        if event is None:
            return None
        selection = SelectionType(str(row["selection_type"]))
        selection_label = event.team_a if selection is SelectionType.TEAM_A else event.team_b
        market_id = cast(UUID, row["market_id"])
        captured_at = row["captured_at"]
        computed_at = row["computed_at"]
        grade = ValueGrade(str(row["grade"]))
        reasons = tuple(
            AbstentionReason(reason) for reason in cast(list[str], row["abstention_reasons"])
        )
        freshness = FreshnessStatus(str(row["source_freshness"]))
        coverage = row["data_coverage"]
        distance = row["out_of_distribution_distance"]
        if captured_at is None or coverage is None or distance is None:
            return None
        publishable = grade.value in _OPPORTUNITY_GRADES
        return Opportunity(
            signal_id=cast(UUID, row["signal_id"]),
            event=event,
            market=Market(
                market_id=market_id,
                event_id=event.event_id,
                type=MarketType.MATCH_WINNER,
                period=MarketPeriod(str(row["period"])),
                selection=selection,
                selection_label=selection_label,
                line=row["line"],
                status=MarketStatus(str(row["market_status"])),
                settlement_rules_version=str(row["settlement_rules_version"]),
            ),
            book=OddsSnapshot(
                odds_snapshot_id=cast(UUID, row["odds_snapshot_id"]),
                event_id=event.event_id,
                market_id=market_id,
                selection=selection,
                provider=str(row["provider_code"]),
                provider_status=ProviderStatus(str(row["provider_status"])),
                market_status=MarketStatus(str(row["market_status"])),
                decimal_odds=row["offered_odds"],
                captured_at=captured_at,
                age_seconds=int(row["odds_age_seconds"]),
                raw_implied_probability=row["raw_implied_probability"],
                no_vig_probability=row["no_vig_probability"],
                informational_only=bool(row["informational_only"]),
                provenance_reference=str(row["provenance_reference"]),
            ),
            model=Prediction(
                prediction_id=cast(UUID, row["prediction_id"]),
                event_id=event.event_id,
                market_id=market_id,
                selection=selection,
                probability=row["model_probability"],
                probability_low=row["model_probability_low"],
                probability_high=row["model_probability_high"],
                confidence=row["confidence"],
                confidence_reduction_reasons=tuple(cast(list[str], row["reason_codes"])),
                data_coverage=coverage,
                out_of_distribution_distance=distance,
                prediction_cutoff=row["cutoff_at"],
                model_version_id=cast(UUID, row["model_version_id"]),
                model_version=PostgresModelRepository.version(cast(UUID, row["model_version_id"])),
                feature_snapshot_id=cast(UUID, row["feature_snapshot_id"]),
                created_at=row["predicted_at"],
            ),
            value=Value(
                policy_version=str(row["policy_version"]),
                fair_odds=row["fair_odds"],
                edge=row["edge"],
                expected_value=row["expected_value"],
                conservative_expected_value=row["conservative_expected_value"],
                grade=grade,
            ),
            quality=Quality(
                mapping_confidence=row["mapping_confidence"],
                source_freshness=freshness,
                data_coverage=coverage,
                model_status=ModelStatus(str(row["model_status"])),
                abstention_reasons=reasons,
                publishable=publishable,
            ),
            meta=ContractMetadata(
                data_mode=DataMode.REAL,
                freshness=freshness,
                as_of=captured_at,
                computed_at=computed_at,
                app_version=version("metiquo"),
            ),
            explanation_reference=f"signal-proof-v1:{row['signal_fingerprint']}",
        )
