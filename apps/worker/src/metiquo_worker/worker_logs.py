"""Small, explicit operational journal. Raw Python or browser output is never stored."""

import logging
import re
import traceback
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from metiquo_core.models import WorkerLogEntry
from metiquo_core.source_issues import LOLTV_ISSUES, source_resource
from sqlalchemy import Engine, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_script: ContextVar[str | None] = ContextVar("worker_log_script", default=None)
_run: ContextVar[UUID | None] = ContextVar("worker_log_run", default=None)
_identifier = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_kind = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")
_frame = re.compile(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_<>]+:[0-9]{1,6}\Z")

# Text and severity are selected from this local catalog, never from a source
# response, exception message, request header, URL or database connection string.
EVENTS = {
    "worker_started": ("info", "service", "Service worker démarré."),
    "worker_stopped": ("info", "service", "Service worker arrêté."),
    "heartbeat_failed": ("error", "service", "Contact avec la base indisponible."),
    "scheduler_failed": ("error", "planification", "Le planificateur a rencontré une erreur."),
    "run_started": ("info", "exécution", "Exécution démarrée."),
    "run_succeeded": ("info", "exécution", "Exécution terminée."),
    "run_partial": ("warning", "exécution", "Exécution terminée avec une couverture incomplète."),
    "run_failed": ("error", "exécution", "Exécution en échec."),
    "run_interrupted": ("error", "exécution", "Exécution interrompue par un arrêt du worker."),
    "run_deferred": (
        "warning",
        "exécution",
        "Exécution différée jusqu'au prochain délai autorisé.",
    ),
    "run_busy": ("info", "exécution", "Exécution reportée : source déjà occupée."),
    "stake_event_published": ("info", "publication", "Rencontre et relevés publiés."),
    "stake_market_ambiguous": (
        "warning",
        "publication",
        "Rencontre non publiée : identité de marché ambiguë.",
    ),
    "stake_event_rejected": ("warning", "publication", "Rencontre non publiée après contrôle."),
    "stake_cycle_interrupted": ("error", "collecte", "Passage Stake interrompu après erreur."),
    "collector_interrupted": ("error", "collecte", "Collecte interrompue après erreur."),
    "source_pages_failed": (
        "warning",
        "collecte",
        "Certaines pages source n'ont pas été acquises.",
    ),
    "oracle_projection_failed": (
        "warning",
        "publication",
        "Détail des rencontres Oracle non actualisé après import.",
    ),
}
EVENTS.update({code: ("warning", stage, reason) for code, (stage, reason) in LOLTV_ISSUES.items()})


@dataclass(frozen=True)
class RunBinding:
    script_token: Token[str | None]
    run_token: Token[UUID | None]

    def reset(self) -> None:
        _run.reset(self.run_token)
        _script.reset(self.script_token)


def bind_run(script_id: str, run_id: UUID) -> RunBinding:
    return RunBinding(_script.set(script_id), _run.set(run_id))


def _safe_context(context: dict[str, object] | None) -> dict[str, object]:
    if not context:
        return {}
    safe: dict[str, object] = {}
    for key in (
        "snapshots",
        "quotes",
        "markets",
        "eventsFailed",
        "pages",
        "leagues",
        "teams",
        "imported",
        "unchanged",
        "published",
        "created",
        "knownEvents",
        "pendingDetails",
        "errors",
        "unavailableFeeds",
        "cacheAgeSeconds",
        "examined",
        "changed",
        "pending",
        "won",
        "lost",
        "void",
    ):
        value = context.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            safe[key] = value
    kind = context.get("kind")
    if isinstance(kind, str) and _kind.fullmatch(kind):
        safe["kind"] = kind
    resource = source_resource(context.get("resource"))
    if resource:
        safe["resource"] = resource
    source_state = context.get("sourceState")
    if isinstance(source_state, str) and source_state in {
        "UNSTARTED",
        "STARTED",
        "PAUSED",
        "COMPLETED",
    }:
        safe["sourceState"] = source_state
    status = context.get("status")
    if isinstance(status, str) and status in {"succeeded", "failed", "interrupted", "queued"}:
        safe["status"] = status
    step = context.get("step")
    if isinstance(step, str) and step in {
        "discovery",
        "listing",
        "event_traversal",
        "publication",
        "export",
        "download",
        "validation",
        "database import",
        "database publication",
        "logos",
    }:
        safe["step"] = step
    retry_at = context.get("retryAt")
    if isinstance(retry_at, datetime) and retry_at.tzinfo is not None:
        safe["retryAt"] = retry_at.isoformat()
    frames = context.get("frames")
    if isinstance(frames, list):
        safe["frames"] = [
            frame for frame in frames[:8] if isinstance(frame, str) and _frame.fullmatch(frame)
        ]
    return safe


def error_context(error: Exception) -> dict[str, object]:
    return {
        "kind": type(error).__name__,
        "frames": [
            f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
            for frame in traceback.extract_tb(error.__traceback__)[-8:]
        ],
    }


def emit(
    engine: Engine,
    worker_id: int,
    code: str,
    *,
    event_id: str | None = None,
    context: dict[str, object] | None = None,
) -> None:
    level, stage, message = EVENTS[code]
    safe_event_id = event_id if event_id and _identifier.fullmatch(event_id) else None
    try:
        with Session(engine) as db, db.begin():
            db.add(
                WorkerLogEntry(
                    worker_id=worker_id,
                    script_id=_script.get(),
                    run_id=_run.get(),
                    level=level,
                    code=code,
                    stage=stage,
                    message=message,
                    event_id=safe_event_id,
                    context=_safe_context(context),
                )
            )
    except SQLAlchemyError as error:
        # Operational logging must never stop a collection or leak DB details.
        logger.warning("Operational log unavailable (%s)", type(error).__name__)


def prune(engine: Engine) -> None:
    try:
        with Session(engine) as db, db.begin():
            db.execute(
                delete(WorkerLogEntry).where(
                    WorkerLogEntry.recorded_at < datetime.now(UTC) - timedelta(days=14)
                )
            )
    except SQLAlchemyError as error:
        logger.warning("Operational log retention unavailable (%s)", type(error).__name__)
