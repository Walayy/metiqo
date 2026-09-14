"""Dernières pages collectées et état réel du scraper."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine, func, select

from metiquo.config import OddsProvider, Settings
from metiquo.contracts.enums import FreshnessStatus
from metiquo.contracts.stake_scraping import (
    StakeCollectionStatus,
    StakeEventCapture,
    StakePublicEvent,
)
from metiquo.db.odds_models import StakePageCapture, StakeScrapeRun
from metiquo.foundation.time import Clock
from metiquo.providers.stake_parser import PROVIDER_CODE
from metiquo.repositories.pagination import ReadPage, page_rows


@dataclass(frozen=True, slots=True)
class PostgresStakeScrapingRepository:
    engine: Engine
    settings: Settings
    clock: Clock

    def status(self) -> StakeCollectionStatus:
        enabled = self.settings.odds_provider is OddsProvider.STAKE_PUBLIC
        with self.engine.connect() as connection:
            latest = connection.execute(
                select(StakeScrapeRun.__table__)
                .order_by(StakeScrapeRun.finished_at.desc(), StakeScrapeRun.id.desc())
                .limit(1)
            ).first()
            success = connection.scalar(select(func.max(StakePageCapture.observed_at)))
        state = latest.status if latest else "never_collected"
        if not enabled:
            state = "disabled"
        elif (
            latest
            and state == "operational"
            and self.clock.now().value
            > latest.next_attempt_at + timedelta(seconds=self.settings.stake_scrape_timeout_seconds)
        ):
            state = "stale"
        return StakeCollectionStatus.model_validate(
            {
                "enabled": enabled,
                "state": state,
                "checkedAt": latest.finished_at if latest else None,
                "lastSuccessAt": success,
                "nextAttemptAt": latest.next_attempt_at if latest else None,
                "detail": latest.detail if latest else None,
                "eventCount": latest.event_count if latest else 0,
            },
            strict=False,
        )

    def page(
        self,
        *,
        offset: int,
        limit: int,
        starts_from: datetime | None,
        starts_to: datetime | None,
    ) -> ReadPage[StakePublicEvent]:
        table = StakePageCapture.__table__
        latest = select(
            table,
            func.row_number()
            .over(
                partition_by=table.c.provider_event_id,
                order_by=(table.c.observed_at.desc(), table.c.id.desc()),
            )
            .label("rank"),
        ).subquery()
        query = (
            select(latest)
            .where(latest.c.rank == 1)
            .order_by(latest.c.starts_at, latest.c.provider_event_id)
        )
        if starts_from:
            query = query.where(latest.c.starts_at >= starts_from)
        if starts_to:
            query = query.where(latest.c.starts_at <= starts_to)
        with self.engine.connect() as connection:
            page = page_rows(connection, query, offset=offset, limit=limit)
        now = self.clock.now().value
        threshold = self.settings.odds_provider_max_age_seconds.get(
            PROVIDER_CODE, self.settings.odds_max_age_seconds
        )
        status = self.status()
        values = []
        for row in page.items:
            capture = StakeEventCapture.model_validate(row.payload, strict=False)
            oldest = min((m.captured_at for m in capture.markets), default=capture.observed_at)
            age = max(0, int((now - oldest).total_seconds()))
            freshness = (
                FreshnessStatus.STALE
                if age > threshold
                else FreshnessStatus.DEGRADED
                if status.state != "operational" or capture.warnings
                else FreshnessStatus.FRESH
            )
            values.append(
                StakePublicEvent(
                    capture=capture,
                    age_seconds=age,
                    freshness=freshness,
                    expires_at=oldest + timedelta(seconds=threshold),
                )
            )
        return ReadPage(tuple(values), page.total)
