"""Journalisation JSON et contexte de corrélation."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TextIO

from metiquo.foundation.identifiers import (
    CorrelationId,
    JobId,
    ModelVersionId,
    SnapshotId,
    TraceId,
)


@dataclass(frozen=True, slots=True)
class LogContext:
    """Identifiants sûrs ajoutés aux journaux d'une opération."""

    trace_id: TraceId | None = None
    correlation_id: CorrelationId | None = None
    job_id: JobId | None = None
    snapshot_id: SnapshotId | None = None
    model_version: ModelVersionId | None = None


_LOG_CONTEXT: ContextVar[LogContext | None] = ContextVar("metiquo_log_context", default=None)


def _current_log_context() -> LogContext:
    return _LOG_CONTEXT.get() or LogContext()


@contextmanager
def bind_log_context(
    *,
    trace_id: TraceId | None = None,
    correlation_id: CorrelationId | None = None,
    job_id: JobId | None = None,
    snapshot_id: SnapshotId | None = None,
    model_version: ModelVersionId | None = None,
) -> Iterator[None]:
    """Lier des identifiants au contexte courant puis restaurer le précédent."""

    current = _current_log_context()
    updated = replace(
        current,
        trace_id=trace_id if trace_id is not None else current.trace_id,
        correlation_id=(correlation_id if correlation_id is not None else current.correlation_id),
        job_id=job_id if job_id is not None else current.job_id,
        snapshot_id=snapshot_id if snapshot_id is not None else current.snapshot_id,
        model_version=model_version if model_version is not None else current.model_version,
    )
    token = _LOG_CONTEXT.set(updated)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


class JsonFormatter(logging.Formatter):
    """Formatter stable ne sérialisant que des champs structurés autorisés."""

    def format(self, record: logging.LogRecord) -> str:
        context = _current_log_context()
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        identifiers = {
            "trace_id": context.trace_id,
            "correlation_id": context.correlation_id,
            "job_id": context.job_id,
            "snapshot_id": context.snapshot_id,
            "model_version": context.model_version,
        }
        payload.update(
            {
                name: str(identifier)
                for name, identifier in identifiers.items()
                if identifier is not None
            }
        )
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configure_json_logging(*, level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """Configurer le logger racine avec une unique sortie JSON."""

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
