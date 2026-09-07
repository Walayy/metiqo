"""Alertes locales persistées, avec rappels bornés et transitions explicites."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import Engine, insert, select, text, update

from metiquo.config import Settings
from metiquo.db.ops_models import AlertStateRecord, AuditEventRecord
from metiquo.foundation.audit import current_audit_context
from metiquo.foundation.locks import try_transaction_lock
from metiquo.foundation.metrics import ApiMetrics
from metiquo.foundation.time import Clock
from metiquo.services.operational_status import OperationalStatusService


@dataclass(frozen=True, slots=True)
class AlertFacts:
    source: str
    model: str
    mapping_backlog: int
    active_blocking: int
    backups: str


@dataclass(frozen=True, slots=True)
class AlertCondition:
    code: str
    details: dict[str, object]


def alert_conditions(facts: AlertFacts, *, mapping_limit: int) -> tuple[AlertCondition, ...]:
    if mapping_limit < 1 or min(facts.mapping_backlog, facts.active_blocking) < 0:
        raise ValueError("Seuil ou compteur d'alerte invalide")
    alerts = []
    for code, status in (
        ("SOURCE_UNHEALTHY", facts.source),
        ("MODEL_UNHEALTHY", facts.model),
        ("BACKUP_UNHEALTHY", facts.backups),
    ):
        if status != "fresh":
            alerts.append(AlertCondition(code, {"status": status}))
    if facts.mapping_backlog >= mapping_limit:
        alerts.append(
            AlertCondition(
                "MAPPING_BACKLOG", {"count": facts.mapping_backlog, "limit": mapping_limit}
            )
        )
    if facts.active_blocking:
        alerts.append(AlertCondition("DQ_BLOCKING", {"count": facts.active_blocking}))
    return tuple(alerts)


class PostgresAlertMonitor:
    def __init__(self, engine: Engine, settings: Settings, clock: Clock) -> None:
        self.engine, self.settings, self.clock = engine, settings, clock

    def check(self) -> tuple[UUID, ...]:
        health = OperationalStatusService(self.engine, self.settings, self.clock).snapshot(
            ApiMetrics().snapshot()
        )
        # Une confirmation réussie postérieure clôt les incidents antérieurs de cette source.
        # Les métriques historiques de qualité restent inchangées.
        with self.engine.connect() as connection:
            active_blocking = connection.scalar(
                text("""
                SELECT count(*) FROM raw.quality_issues q
                JOIN raw.ingestion_runs r ON r.id = q.run_id
                JOIN raw.source_catalog c ON c.id = r.source_catalog_id
                WHERE q.severity = 'blocking' AND c.provider = 'oracles_elixir'
                  AND c.dataset = 'league_of_legends_match_data'
                  AND q.created_at <= :now
                  AND NOT EXISTS (
                    SELECT 1 FROM raw.ingestion_runs ok WHERE ok.source_catalog_id = c.id
                    AND ok.status = 'succeeded' AND ok.finished_at <= :now
                    AND ok.finished_at > q.created_at
                    AND ok.snapshot_id = c.current_snapshot_id
                    AND ok.counters->>'contentVerified' = 'true'
                  )
            """),
                {"now": self.clock.now().value},
            )
        return self.publish(
            alert_conditions(
                AlertFacts(
                    health.source.status.value,
                    health.model.status,
                    health.mapping_backlog,
                    int(active_blocking or 0),
                    health.backups.status,
                ),
                mapping_limit=self.settings.alert_mapping_backlog_limit,
            )
        )

    def publish(self, conditions: tuple[AlertCondition, ...]) -> tuple[UUID, ...]:
        now = self.clock.now().value
        active = {item.code: item for item in conditions}
        emitted: list[tuple[UUID, str, str]] = []
        context = current_audit_context()
        with self.engine.begin() as connection:
            if not try_transaction_lock(connection, "ops:alert-state"):
                return ()
            states = {
                row["code"]: row for row in connection.execute(select(AlertStateRecord)).mappings()
            }
            if any(row["observed_at"] > now for row in states.values()):
                return ()
            for code in sorted(states.keys() | active.keys()):
                previous = states.get(code)
                condition = active.get(code)
                is_active = condition is not None
                was_active = previous is not None and previous["active"]
                action = None
                if is_active and not was_active:
                    action = "opened"
                elif not is_active and was_active:
                    action = "resolved"
                elif (
                    is_active
                    and previous is not None
                    and now - previous["last_notified_at"]
                    >= timedelta(seconds=self.settings.alert_cooldown_seconds)
                ):
                    action = "reminder"
                details = condition.details if condition else {}
                values = {
                    "active": is_active,
                    "observed_at": now,
                    "changed_at": now
                    if is_active != was_active or previous is None
                    else previous["changed_at"],
                    "last_notified_at": now
                    if action or previous is None
                    else previous["last_notified_at"],
                    "details": details,
                }
                if previous is None:
                    connection.execute(insert(AlertStateRecord).values(code=code, **values))
                else:
                    connection.execute(
                        update(AlertStateRecord)
                        .where(AlertStateRecord.code == code)
                        .values(**values)
                    )
                if action:
                    identity = uuid4()
                    connection.execute(
                        insert(AuditEventRecord).values(
                            id=identity,
                            actor=context.actor if context else "alert-monitor",
                            action=f"alert.{action}",
                            target_type="ops.alerts",
                            target_id=code,
                            before_refs={"active": bool(was_active)},
                            after_refs={"active": is_active, **details},
                            trace_id=context.trace_id if context else uuid4(),
                            occurred_at=now,
                        )
                    )
                    emitted.append((identity, code, action))
        for _, code, action in emitted:
            logger = logging.getLogger("metiquo.alerts")
            logger.log(
                logging.INFO if action == "resolved" else logging.WARNING,
                "alert.%s.%s",
                code,
                action,
            )
        return tuple(identity for identity, _, _ in emitted)
