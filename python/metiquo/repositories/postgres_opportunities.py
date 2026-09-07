"""Projection publique des signaux PostgreSQL en opportunités contractuelles."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, Table, false, func, select
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
from metiquo.db.core_models import Team
from metiquo.db.ml_models import ModelVersion, PrematchPrediction
from metiquo.db.odds_models import (
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsMarket,
)
from metiquo.db.pricing_models import SignalRecord
from metiquo.foundation.time import Clock, SystemClock
from metiquo.repositories.canonical_events_sql import (
    event_from_row,
    event_projection,
    filter_events,
)
from metiquo.repositories.pagination import ReadPage, page_rows
from metiquo.repositories.postgres_models import PostgresModelRepository

_OPPORTUNITY_GRADES = frozenset(
    (ValueGrade.STRONG_VALUE.value, ValueGrade.VALUE.value, ValueGrade.WATCH.value)
)


class PostgresOpportunityRepository:
    """Lire les signaux sans reclasser ni compléter artificiellement leurs preuves."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self.clock = clock or SystemClock()

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

    def page(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        competition: str | None = None,
        team: str | None = None,
        market: MarketType | None = None,
        grade: ValueGrade | None = None,
        min_edge: Decimal | None = None,
        min_ev: Decimal | None = None,
        min_confidence: Decimal | None = None,
        freshness: FreshnessStatus | None = None,
        starts_from: datetime | None = None,
        starts_to: datetime | None = None,
    ) -> ReadPage[Opportunity]:
        entries = self._statement().subquery("opportunity_rows")
        statement = filter_events(
            select(entries),
            entries,
            competition=competition,
            team=team,
            starts_from=starts_from,
            starts_to=starts_to,
            prefix="canonical_",
        )
        statement = (
            statement.where(entries.c.grade == grade.value)
            if grade is not None
            else statement.where(entries.c.grade.in_(_OPPORTUNITY_GRADES))
        )
        if market is not None and market is not MarketType.MATCH_WINNER:
            statement = statement.where(false())
        for column, minimum in (
            (entries.c.edge, min_edge),
            (entries.c.expected_value, min_ev),
            (entries.c.confidence, min_confidence),
        ):
            if minimum is not None:
                statement = statement.where(column >= minimum)
        if freshness is not None:
            statement = statement.where(entries.c.source_freshness == freshness.value)
        statement = statement.order_by(
            entries.c.conservative_expected_value.desc(),
            entries.c.computed_at.desc(),
            entries.c.signal_id,
        )
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            page = page_rows(connection, statement, offset=offset, limit=limit)
        return ReadPage(
            tuple(item for row in page.items if (item := self._opportunity(row)) is not None),
            page.total,
        )

    @staticmethod
    def _statement() -> Select[tuple[Any, ...]]:
        signals = cast(Table, SignalRecord.__table__)
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        providers = cast(Table, OddsProviderRecord.__table__)
        markets = cast(Table, ProviderOddsMarket.__table__)
        predictions = cast(Table, PrematchPrediction.__table__)
        models = cast(Table, ModelVersion.__table__)
        events = event_projection()
        return (
            select(
                signals.c.id.label("signal_id"),
                signals.c.odds_snapshot_id,
                signals.c.selection_type,
                func.coalesce(Team.display_name, Team.normalized_name).label("selected_team_name"),
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
                *(column.label(f"canonical_{column.name}") for column in events.c),
            )
            .select_from(
                signals.join(snapshots, snapshots.c.id == signals.c.odds_snapshot_id)
                .join(providers, providers.c.id == snapshots.c.provider_id)
                .join(markets, markets.c.id == snapshots.c.market_id)
                .join(predictions, predictions.c.id == signals.c.prediction_id)
                .join(models, models.c.id == predictions.c.model_version_id)
                .join(Team, Team.id == signals.c.selected_team_id)
                .join(events, events.c.event_id == predictions.c.event_id)
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
        event = event_from_row(row, "canonical_")
        selection = SelectionType(str(row["selection_type"]))
        selection_label = str(row["selected_team_name"])
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
