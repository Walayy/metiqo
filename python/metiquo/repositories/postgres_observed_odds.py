"""Lecture bornée des cotes fournisseur, y compris les matchs sans mapping OE."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, Select, func, select

from metiquo.config import Settings
from metiquo.contracts.enums import FreshnessStatus, ProviderStatus
from metiquo.contracts.observed_odds import ObservedOddsQuote
from metiquo.db.odds_models import (
    OddsProviderHealth,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsEvent,
    ProviderOddsMarket,
)
from metiquo.foundation.time import Clock
from metiquo.repositories.pagination import ReadPage, page_rows


@dataclass(frozen=True, slots=True)
class PostgresObservedOddsRepository:
    engine: Engine
    settings: Settings
    clock: Clock

    def page(
        self,
        *,
        offset: int,
        limit: int,
        provider: str | None,
        starts_from: datetime | None,
        starts_to: datetime | None,
    ) -> ReadPage[ObservedOddsQuote]:
        snapshots = OddsSnapshotRecord.__table__
        events = ProviderOddsEvent.__table__
        markets = ProviderOddsMarket.__table__
        providers = OddsProviderRecord.__table__
        health = OddsProviderHealth.__table__
        latest = select(
            snapshots,
            func.row_number()
            .over(
                partition_by=snapshots.c.selection_id,
                order_by=(
                    snapshots.c.captured_at.desc(),
                    snapshots.c.recorded_at.desc(),
                    snapshots.c.id.desc(),
                ),
            )
            .label("rank"),
        ).subquery()
        latest_health = (
            select(health.c.provider_id, health.c.status)
            .distinct(health.c.provider_id)
            .order_by(health.c.provider_id, health.c.checked_at.desc(), health.c.id.desc())
            .subquery()
        )
        statement: Select[tuple[Any, ...]] = (
            select(
                latest,
                providers.c.code.label("provider"),
                providers.c.provider_type,
                latest_health.c.status.label("current_provider_status"),
                events.c.provider_event_id,
                events.c.game_title,
                events.c.competition_name,
                events.c.participants,
                events.c.starts_at,
                events.c.best_of,
                events.c.status,
                events.c.collected_at,
                events.c.source_reference,
                markets.c.raw_label.label("market_label"),
                markets.c.period,
            )
            .join(events, events.c.id == latest.c.event_id)
            .join(markets, markets.c.id == latest.c.market_id)
            .join(providers, providers.c.id == latest.c.provider_id)
            .outerjoin(latest_health, latest_health.c.provider_id == providers.c.id)
            .where(latest.c.rank == 1)
            .order_by(
                events.c.starts_at,
                providers.c.code,
                events.c.id,
                markets.c.id,
                latest.c.selection_id,
            )
        )
        if provider is not None:
            statement = statement.where(providers.c.code == provider)
        if starts_from is not None:
            statement = statement.where(events.c.starts_at >= starts_from)
        if starts_to is not None:
            statement = statement.where(events.c.starts_at <= starts_to)
        with self.engine.connect() as connection:
            page = page_rows(connection, statement, offset=offset, limit=limit)
        now = self.clock.now().value
        quotes = []
        for row in page.items:
            age = max(0, int((now - row.captured_at).total_seconds()))
            threshold = self.settings.odds_provider_max_age_seconds.get(
                row.provider, self.settings.odds_max_age_seconds
            )
            status = row.current_provider_status or ProviderStatus.UNAVAILABLE
            freshness = (
                FreshnessStatus.DEGRADED
                if status != ProviderStatus.OPERATIONAL
                else FreshnessStatus.STALE
                if age > threshold
                else FreshnessStatus.FRESH
            )
            quotes.append(
                ObservedOddsQuote.model_validate(
                    {
                        "odds_snapshot_id": row.id,
                        "provider": row.provider,
                        "provider_type": row.provider_type,
                        "provider_status": status,
                        "event": {
                            "provider_event_id": row.provider_event_id,
                            "game_title": row.game_title,
                            "competition": row.competition_name,
                            "participants": tuple(row.participants),
                            "starts_at": row.starts_at,
                            "best_of": row.best_of,
                            "status": row.status,
                            "collected_at": row.collected_at,
                            "source_reference": row.source_reference,
                        },
                        "market_label": row.market_label,
                        "period": row.period,
                        "market_status": row.market_status,
                        "selection_label": row.selection_label,
                        "decimal_odds": row.decimal_odds,
                        "captured_at": row.captured_at,
                        "age_seconds": age,
                        "freshness": freshness,
                        "informational_only": row.informational_only,
                    },
                    strict=False,
                )
            )
        return ReadPage(tuple(quotes), page.total)
