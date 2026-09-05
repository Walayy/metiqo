"""Persistance PostgreSQL des politiques de value immuables."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, RowMapping, Table, select

from metiquo.db.pricing_models import ValuePolicyAuditRecord, ValuePolicyRecord
from metiquo.foundation.time import Clock, SystemClock
from metiquo.pricing.policy import (
    ValuePolicy,
    ValuePolicyError,
    ValueThresholds,
    value_policy_from_storage,
)


class PolicyRegistrationError(ValuePolicyError):
    """Une version tente de réécrire ou de contourner l'historique."""


@dataclass(frozen=True, slots=True)
class ValuePolicyAudit:
    """Projection lisible d'une création ou révision persistée."""

    audit_id: UUID
    policy_version: str
    previous_version: str | None
    action: str
    actor: str
    reason: str
    changes: Mapping[str, object]
    occurred_at: datetime


class PostgresValuePolicyRepository:
    """Enregistrer chaque changement sous une nouvelle version auditée."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self._clock = clock or SystemClock()

    def register(
        self,
        policy: ValuePolicy,
        *,
        actor: str,
        reason: str,
        previous_version: str | None = None,
    ) -> ValuePolicy:
        normalized_actor = actor.strip()
        normalized_reason = reason.strip()
        if not normalized_actor or len(normalized_actor) > 255:
            raise PolicyRegistrationError("actor doit contenir entre 1 et 255 caractères")
        if not normalized_reason or len(normalized_reason) > 512:
            raise PolicyRegistrationError("reason doit contenir entre 1 et 512 caractères")
        normalized_previous = previous_version.strip() if previous_version is not None else None
        if previous_version is not None and not normalized_previous:
            raise PolicyRegistrationError("previous_version ne peut pas être vide")

        policies = cast(Table, ValuePolicyRecord.__table__)
        audits = cast(Table, ValuePolicyAuditRecord.__table__)
        now = self._clock.now().value
        with self.engine.begin() as connection:
            existing = (
                connection.execute(select(policies).where(policies.c.version == policy.version))
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if cast(str, existing["fingerprint"]) != policy.fingerprint:
                    raise PolicyRegistrationError(
                        "une version de politique existante ne peut pas être redéfinie"
                    )
                return _policy_from_row(existing)

            first_policy_id = connection.execute(
                select(policies.c.id).order_by(policies.c.created_at, policies.c.id).limit(1)
            ).scalar_one_or_none()
            previous = None
            if normalized_previous is not None:
                previous = (
                    connection.execute(
                        select(policies).where(policies.c.version == normalized_previous)
                    )
                    .mappings()
                    .one_or_none()
                )
                if previous is None:
                    raise PolicyRegistrationError("la politique précédente est introuvable")
            elif first_policy_id is not None:
                raise PolicyRegistrationError(
                    "toute nouvelle version après la première doit référencer previous_version"
                )

            policy_id = uuid4()
            policy_document = policy.document()
            connection.execute(
                policies.insert().values(
                    id=policy_id,
                    version=policy.version,
                    min_edge=policy.thresholds.min_edge,
                    min_ev=policy.thresholds.min_ev,
                    min_conservative_ev=policy.thresholds.min_conservative_ev,
                    max_odds_age_seconds=policy.thresholds.max_odds_age_seconds,
                    min_mapping_confidence=policy.thresholds.min_mapping_confidence,
                    tuned_through=policy.tuned_through,
                    final_test_starts_at=policy.final_test_starts_at,
                    overrides=policy_document["overrides"],
                    fingerprint=policy.fingerprint,
                    created_at=now,
                )
            )
            previous_policy_id = cast(UUID, previous["id"]) if previous is not None else None
            action = "policy.revised" if previous is not None else "policy.created"
            changes: dict[str, object] = {
                "previousVersion": normalized_previous,
                "policy": policy_document,
            }
            audit_fingerprint = _audit_fingerprint(
                policy.fingerprint,
                normalized_previous,
                normalized_actor,
                normalized_reason,
            )
            connection.execute(
                audits.insert().values(
                    id=uuid4(),
                    policy_id=policy_id,
                    previous_policy_id=previous_policy_id,
                    action=action,
                    actor=normalized_actor,
                    reason=normalized_reason,
                    changes=changes,
                    idempotency_fingerprint=audit_fingerprint,
                    occurred_at=now,
                )
            )
        return policy

    def get(self, version: str) -> ValuePolicy:
        policies = cast(Table, ValuePolicyRecord.__table__)
        with self.engine.connect() as connection:
            row = (
                connection.execute(select(policies).where(policies.c.version == version.strip()))
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(version)
        return _policy_from_row(row)

    def list_audits(self) -> tuple[ValuePolicyAudit, ...]:
        policies = cast(Table, ValuePolicyRecord.__table__)
        audits = cast(Table, ValuePolicyAuditRecord.__table__)
        current = policies.alias("current_policy")
        previous = policies.alias("previous_policy")
        statement = (
            select(
                audits,
                current.c.version.label("policy_version"),
                previous.c.version.label("previous_version"),
            )
            .join(current, current.c.id == audits.c.policy_id)
            .outerjoin(previous, previous.c.id == audits.c.previous_policy_id)
            .order_by(audits.c.occurred_at, audits.c.action, current.c.version, audits.c.id)
        )
        with self.engine.connect() as connection:
            rows = tuple(connection.execute(statement).mappings())
        return tuple(
            ValuePolicyAudit(
                audit_id=cast(UUID, row["id"]),
                policy_version=cast(str, row["policy_version"]),
                previous_version=cast(str | None, row["previous_version"]),
                action=cast(str, row["action"]),
                actor=cast(str, row["actor"]),
                reason=cast(str, row["reason"]),
                changes=cast(Mapping[str, object], row["changes"]),
                occurred_at=cast(datetime, row["occurred_at"]),
            )
            for row in rows
        )


def _policy_from_row(row: RowMapping) -> ValuePolicy:
    return value_policy_from_storage(
        version=cast(str, row["version"]),
        thresholds=ValueThresholds(
            min_edge=cast(Decimal, row["min_edge"]),
            min_ev=cast(Decimal, row["min_ev"]),
            min_conservative_ev=cast(Decimal, row["min_conservative_ev"]),
            max_odds_age_seconds=cast(int, row["max_odds_age_seconds"]),
            min_mapping_confidence=cast(Decimal, row["min_mapping_confidence"]),
        ),
        tuned_through=cast(datetime, row["tuned_through"]),
        final_test_starts_at=cast(datetime, row["final_test_starts_at"]),
        overrides=cast(Mapping[str, object], row["overrides"]),
    )


def _audit_fingerprint(
    policy_fingerprint: str,
    previous_version: str | None,
    actor: str,
    reason: str,
) -> str:
    document = {
        "policyFingerprint": policy_fingerprint,
        "previousVersion": previous_version,
        "actor": actor,
        "reason": reason,
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
