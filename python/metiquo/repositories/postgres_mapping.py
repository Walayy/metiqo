"""Projection PostgreSQL de la file de revue et de son audit."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, Table, func, select

from metiquo.contracts import AuditEntry, Event, MappingCandidate, MappingReview
from metiquo.contracts.enums import DataMode, MappingReviewStatus
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingAuditRecord,
    MappingReviewRecord,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsEvent,
)
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository


class PostgresMappingRepository:
    """Lire une revue sans exposer les lignes ORM ni recalculer ses scores."""

    def __init__(self, engine: Engine, clock: Clock) -> None:
        self.engine = engine
        self.clock = clock

    def list_pending(self) -> tuple[MappingReview, ...]:
        return self._reviews(status="pending")

    def get(self, mapping_review_id: UUID) -> MappingReview | None:
        values = self._reviews(mapping_review_id=mapping_review_id)
        return values[0] if values else None

    def list_audit(self) -> tuple[AuditEntry, ...]:
        audits = cast(Table, MappingAuditRecord.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(audits).order_by(audits.c.occurred_at.desc(), audits.c.id.desc())
            ).mappings()
            return tuple(
                AuditEntry(
                    audit_id=cast(UUID, row["id"]),
                    action=cast(str, row["action"]),
                    resource_id=cast(str, row["resource_id"]),
                    idempotency_fingerprint=cast(str, row["idempotency_fingerprint"]),
                    occurred_at=row["occurred_at"],
                    data_mode=DataMode.REAL,
                    actor=cast(str, row["actor"]),
                    reason=cast(str, row["reason"]),
                    impact=cast(dict[str, object], row["impact"]),
                )
                for row in rows
            )

    def _reviews(
        self,
        *,
        status: str | None = None,
        mapping_review_id: UUID | None = None,
    ) -> tuple[MappingReview, ...]:
        reviews = cast(Table, MappingReviewRecord.__table__)
        attempts = cast(Table, EventMappingAttempt.__table__)
        provider_events = cast(Table, ProviderOddsEvent.__table__)
        providers = cast(Table, OddsProviderRecord.__table__)
        statement = (
            select(
                reviews,
                attempts.c.provider_event_id.label("internal_provider_event_id"),
                provider_events.c.provider_event_id.label("external_provider_event_id"),
                provider_events.c.competition_name,
                provider_events.c.participants,
                providers.c.code.label("provider_code"),
            )
            .join(attempts, attempts.c.id == reviews.c.attempt_id)
            .join(provider_events, provider_events.c.id == attempts.c.provider_event_id)
            .join(providers, providers.c.id == provider_events.c.provider_id)
            .order_by(reviews.c.created_at, reviews.c.id)
        )
        if status is not None:
            statement = statement.where(reviews.c.status == status)
        if mapping_review_id is not None:
            statement = statement.where(reviews.c.id == mapping_review_id)
        with self.engine.connect() as connection:
            rows = tuple(connection.execute(statement).mappings())
            if not rows:
                return ()
            attempt_ids = tuple(cast(UUID, row["attempt_id"]) for row in rows)
            provider_event_ids = tuple(
                cast(UUID, row["internal_provider_event_id"]) for row in rows
            )
            candidates = self._candidate_rows(connection, attempt_ids)
            snapshot_counts = {
                cast(UUID, event_id): int(count)
                for event_id, count in connection.execute(
                    select(ProviderOddsEvent.id, func.count(OddsSnapshotRecord.id))
                    .outerjoin(
                        OddsSnapshotRecord,
                        OddsSnapshotRecord.event_id == ProviderOddsEvent.id,
                    )
                    .where(ProviderOddsEvent.id.in_(provider_event_ids))
                    .group_by(ProviderOddsEvent.id)
                )
            }
        events = {
            event.event_id: event
            for event in PostgresCanonicalRepository(self.engine, self.clock).list()
        }
        return tuple(
            self._review(
                row,
                candidates.get(cast(UUID, row["attempt_id"]), ()),
                events,
                snapshot_counts.get(cast(UUID, row["internal_provider_event_id"]), 0),
            )
            for row in rows
        )

    @staticmethod
    def _candidate_rows(
        connection: Connection,
        attempt_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[RowMapping, ...]]:
        scores = cast(Table, EventMappingCandidateScore.__table__)
        rows = connection.execute(
            select(scores)
            .where(scores.c.attempt_id.in_(attempt_ids))
            .order_by(scores.c.attempt_id, scores.c.rank)
        ).mappings()
        grouped: dict[UUID, list[RowMapping]] = {}
        for row in rows:
            grouped.setdefault(cast(UUID, row["attempt_id"]), []).append(row)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _review(
        row: RowMapping,
        candidate_rows: Iterable[RowMapping],
        events: dict[UUID, Event],
        affected_snapshot_count: int,
    ) -> MappingReview:
        candidates = tuple(
            PostgresMappingRepository._candidate(candidate_row, events)
            for candidate_row in candidate_rows
            if cast(UUID, candidate_row["canonical_event_id"]) in events
        )
        return MappingReview(
            mapping_review_id=cast(UUID, row["id"]),
            provider=cast(str, row["provider_code"]),
            provider_event_id=cast(str, row["external_provider_event_id"]),
            raw_competition=cast(str, row["competition_name"]),
            raw_participants=tuple(cast(list[str], row["participants"])),
            candidates=candidates,
            status=MappingReviewStatus(cast(str, row["status"])),
            selected_event_id=cast(UUID | None, row["selected_event_id"]),
            affected_snapshot_count=affected_snapshot_count,
            historical_signals_rewritten=0,
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
            reviewer=cast(str | None, row["reviewer"]),
            decision_reason=cast(str | None, row["decision_reason"]),
        )

    @staticmethod
    def _candidate(row: RowMapping, events: dict[UUID, Event]) -> MappingCandidate:
        event = events[cast(UUID, row["canonical_event_id"])]
        reasons = (
            f"Équipes : {PostgresMappingRepository._percent(row['team_score'])}",
            f"Horaire : {PostgresMappingRepository._percent(row['time_score'])}",
            f"Compétition : {PostgresMappingRepository._percent(row['competition_score'])}",
            f"Format : {PostgresMappingRepository._percent(row['format_score'])}",
        )
        return MappingCandidate(
            event_id=event.event_id,
            label=f"{event.team_a} — {event.team_b}",
            confidence=cast(Decimal, row["total_score"]),
            reasons=reasons,
            team_a_id=event.team_a_id,
            team_a=event.team_a,
            team_b_id=event.team_b_id,
            team_b=event.team_b,
            selections_inverted=bool(row["selections_inverted"]),
        )

    @staticmethod
    def _percent(value: object) -> str:
        return f"{Decimal(str(value)) * 100:.0f} %"
