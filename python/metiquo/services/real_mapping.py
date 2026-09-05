"""Décisions réelles de mapping, idempotentes et entièrement auditées."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, RowMapping, Table, func, select, update
from sqlalchemy.exc import IntegrityError

from metiquo.canonical.dimensions import normalize_identity
from metiquo.contracts import AliasRecord, MappingReview
from metiquo.contracts.enums import DataMode, MappingReviewStatus
from metiquo.db.core_models import Competition, Player, Team
from metiquo.db.mapping_models import EntityAlias
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingAuditRecord,
    MappingReviewRecord,
    OddsSnapshotRecord,
)
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_mapping import PostgresMappingRepository


class RealMappingMutationService:
    """Appliquer seulement une décision explicite sur une revue persistée."""

    def __init__(self, engine: Engine, repository: PostgresMappingRepository, clock: Clock) -> None:
        self.engine = engine
        self.repository = repository
        self.clock = clock

    def decide_mapping(
        self,
        key: str,
        mapping_review_id: UUID,
        status: MappingReviewStatus,
        reviewer: str,
        reason: str,
        candidate_event_id: UUID | None = None,
    ) -> MappingReview:
        action = f"mapping.{status.value}"
        fingerprint = self._fingerprint(key)
        try:
            with self.engine.begin() as connection:
                replay = self._audit_by_fingerprint(connection, fingerprint)
                if replay is not None:
                    self._validate_decision_replay(
                        replay,
                        action,
                        mapping_review_id,
                        reviewer,
                        reason,
                        candidate_event_id,
                    )
                else:
                    self._apply_decision(
                        connection,
                        fingerprint,
                        mapping_review_id,
                        status,
                        reviewer,
                        reason,
                        candidate_event_id,
                    )
        except IntegrityError as error:
            raise BusinessError(
                ErrorCode.CONFLICT,
                "La décision de mapping entre en conflit avec une mutation concurrente",
            ) from error
        result = self.repository.get(mapping_review_id)
        if result is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Mapping introuvable")
        return result

    def create_alias(
        self,
        key: str,
        provider: str,
        alias: str,
        canonical_id: UUID,
        entity_type: str = "team",
        reviewer: str = "admin-local",
        reason: str = "Alias créé manuellement",
    ) -> AliasRecord:
        fingerprint = self._fingerprint(key)
        try:
            with self.engine.begin() as connection:
                replay = self._audit_by_fingerprint(connection, fingerprint)
                if replay is not None:
                    alias_id = self._validate_alias_replay(
                        connection,
                        replay,
                        provider,
                        alias,
                        canonical_id,
                        entity_type,
                        reviewer,
                        reason,
                    )
                else:
                    self._validate_canonical_target(connection, entity_type, canonical_id)
                    now = self.clock.now().value
                    alias_id = uuid4()
                    aliases = cast(Table, EntityAlias.__table__)
                    connection.execute(
                        aliases.insert().values(
                            id=alias_id,
                            entity_type=entity_type,
                            canonical_id=canonical_id,
                            provider=provider,
                            raw_alias=alias,
                            normalized_alias=normalize_identity(alias),
                            valid_from=now,
                            valid_to=None,
                            source="manual",
                            confidence=Decimal("1"),
                            approved_by=reviewer,
                            approved_at=now,
                            notes=reason,
                            created_at=now,
                        )
                    )
                    self._insert_audit(
                        connection,
                        action="alias.create",
                        review_id=None,
                        entity_alias_id=alias_id,
                        resource_id=str(alias_id),
                        actor=reviewer,
                        reason=reason,
                        impact={
                            "entityType": entity_type,
                            "canonicalId": str(canonical_id),
                            "validFrom": now.isoformat(),
                            "historicalSignalsRewritten": 0,
                        },
                        fingerprint=fingerprint,
                        occurred_at=now,
                    )
        except IntegrityError as error:
            raise BusinessError(
                ErrorCode.CONFLICT,
                "Un alias actif existe déjà pour cette identité provider",
            ) from error
        return self._alias_record(alias_id)

    def _apply_decision(
        self,
        connection: Connection,
        fingerprint: str,
        mapping_review_id: UUID,
        status: MappingReviewStatus,
        reviewer: str,
        reason: str,
        candidate_event_id: UUID | None,
    ) -> None:
        reviews = cast(Table, MappingReviewRecord.__table__)
        attempts = cast(Table, EventMappingAttempt.__table__)
        scores = cast(Table, EventMappingCandidateScore.__table__)
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        row = (
            connection.execute(
                select(
                    reviews.c.status,
                    reviews.c.attempt_id,
                    attempts.c.provider_event_id,
                )
                .join(attempts, attempts.c.id == reviews.c.attempt_id)
                .where(reviews.c.id == mapping_review_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Mapping introuvable")
        if row["status"] != "pending":
            raise BusinessError(ErrorCode.INVALID_STATE, "Le mapping est déjà décidé")
        selected: UUID | None = None
        inverted = False
        if status is MappingReviewStatus.APPROVED:
            if candidate_event_id is None:
                raise BusinessError(
                    ErrorCode.INVALID_INPUT,
                    "Un candidat est obligatoire pour approuver le mapping",
                )
            candidate = (
                connection.execute(
                    select(scores.c.canonical_event_id, scores.c.selections_inverted).where(
                        scores.c.attempt_id == row["attempt_id"],
                        scores.c.canonical_event_id == candidate_event_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if candidate is None:
                raise BusinessError(ErrorCode.INVALID_INPUT, "Candidat de mapping inconnu")
            selected = cast(UUID, candidate["canonical_event_id"])
            inverted = bool(candidate["selections_inverted"])
        elif candidate_event_id is not None:
            raise BusinessError(
                ErrorCode.INVALID_INPUT,
                "Un rejet ne doit sélectionner aucun candidat",
            )
        now = self.clock.now().value
        connection.execute(
            update(reviews)
            .where(reviews.c.id == mapping_review_id)
            .values(
                status=status.value,
                selected_event_id=selected,
                reviewed_at=now,
                reviewer=reviewer,
                decision_reason=reason,
            )
        )
        affected = int(
            connection.execute(
                select(func.count(snapshots.c.id)).where(
                    snapshots.c.event_id == row["provider_event_id"]
                )
            ).scalar_one()
        )
        self._insert_audit(
            connection,
            action=f"mapping.{status.value}",
            review_id=mapping_review_id,
            entity_alias_id=None,
            resource_id=str(mapping_review_id),
            actor=reviewer,
            reason=reason,
            impact={
                "affectedSnapshotCount": affected,
                "historicalSignalsRewritten": 0,
                "selectedEventId": str(selected) if selected else None,
                "selectionsInverted": inverted,
            },
            fingerprint=fingerprint,
            occurred_at=now,
        )

    @staticmethod
    def _audit_by_fingerprint(connection: Connection, fingerprint: str) -> RowMapping | None:
        audits = cast(Table, MappingAuditRecord.__table__)
        return (
            connection.execute(
                select(audits).where(audits.c.idempotency_fingerprint == fingerprint)
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _validate_decision_replay(
        row: RowMapping,
        action: str,
        mapping_review_id: UUID,
        reviewer: str,
        reason: str,
        candidate_event_id: UUID | None,
    ) -> None:
        impact = cast(dict[str, object], row["impact"])
        if (
            row["action"] != action
            or row["review_id"] != mapping_review_id
            or row["actor"] != reviewer
            or row["reason"] != reason
            or impact.get("selectedEventId")
            != (str(candidate_event_id) if candidate_event_id else None)
        ):
            raise BusinessError(
                ErrorCode.CONFLICT,
                "Cette clé d'idempotence correspond à une autre mutation",
            )

    @staticmethod
    def _validate_alias_replay(
        connection: Connection,
        row: RowMapping,
        provider: str,
        alias: str,
        canonical_id: UUID,
        entity_type: str,
        reviewer: str,
        reason: str,
    ) -> UUID:
        alias_id = cast(UUID | None, row["entity_alias_id"])
        if row["action"] != "alias.create" or alias_id is None:
            raise BusinessError(
                ErrorCode.CONFLICT,
                "Cette clé d'idempotence correspond à une autre mutation",
            )
        aliases = cast(Table, EntityAlias.__table__)
        stored = (
            connection.execute(select(aliases).where(aliases.c.id == alias_id)).mappings().one()
        )
        if (
            stored["provider"] != provider
            or stored["raw_alias"] != alias
            or stored["canonical_id"] != canonical_id
            or stored["entity_type"] != entity_type
            or row["actor"] != reviewer
            or row["reason"] != reason
        ):
            raise BusinessError(
                ErrorCode.CONFLICT,
                "Cette clé d'idempotence correspond à une autre mutation",
            )
        return alias_id

    @staticmethod
    def _validate_canonical_target(
        connection: Connection,
        entity_type: str,
        canonical_id: UUID,
    ) -> None:
        tables = {
            "team": cast(Table, Team.__table__),
            "competition": cast(Table, Competition.__table__),
            "player": cast(Table, Player.__table__),
        }
        table = tables.get(entity_type)
        if table is None:
            raise BusinessError(ErrorCode.INVALID_INPUT, "Type d'entité canonique inconnu")
        if (
            connection.execute(select(table.c.id).where(table.c.id == canonical_id)).scalar()
            is None
        ):
            raise BusinessError(ErrorCode.NOT_FOUND, "Entité canonique introuvable")

    @staticmethod
    def _insert_audit(
        connection: Connection,
        *,
        action: str,
        review_id: UUID | None,
        entity_alias_id: UUID | None,
        resource_id: str,
        actor: str,
        reason: str,
        impact: dict[str, object],
        fingerprint: str,
        occurred_at: datetime,
    ) -> None:
        audits = cast(Table, MappingAuditRecord.__table__)
        connection.execute(
            audits.insert().values(
                id=uuid4(),
                action=action,
                review_id=review_id,
                entity_alias_id=entity_alias_id,
                resource_id=resource_id,
                actor=actor,
                reason=reason,
                impact=impact,
                idempotency_fingerprint=fingerprint,
                occurred_at=occurred_at,
            )
        )

    def _alias_record(self, alias_id: UUID) -> AliasRecord:
        aliases = cast(Table, EntityAlias.__table__)
        with self.engine.connect() as connection:
            row = (
                connection.execute(select(aliases).where(aliases.c.id == alias_id)).mappings().one()
            )
        return AliasRecord(
            alias_id=alias_id,
            provider=cast(str, row["provider"]),
            alias=cast(str, row["raw_alias"]),
            canonical_id=cast(UUID, row["canonical_id"]),
            created_at=row["created_at"],
            data_mode=DataMode.REAL,
        )

    @staticmethod
    def _fingerprint(key: str) -> str:
        return hashlib.sha256(key.strip().encode()).hexdigest()
