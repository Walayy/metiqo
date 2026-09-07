"""Journalisation JSON et contexte de corrélation."""

import json
import logging
import re
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

    def __init__(self, *, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(sorted((value for value in secrets if value), key=len, reverse=True))

    def _redact(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(
            r"(?i)\bpostgres(?:ql)?(?:\+psycopg)?://[^\s\"'<>]+", "[REDACTED_DATABASE_URL]", value
        )
        value = re.sub(r"(?i)(?:https?|s3)://[^\s/\"']+@[^\s/\"']+", "[REDACTED_URL]", value)
        value = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[^\s\"',;]+", "[REDACTED_AUTHORIZATION]", value)
        value = re.sub(r"(?i)\b(?:Cookie|Set-Cookie)\s*:[^\r\n]+", "Cookie: [REDACTED]", value)
        return re.sub(
            r"""(?i)(\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?token|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
            r"\1[REDACTED]",
            value,
        )

    def format(self, record: logging.LogRecord) -> str:
        context = _current_log_context()
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact(record.getMessage()),
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
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        for name in ("duration_ms", "status_code", "attempt"):
            value = getattr(record, name, None)
            if isinstance(value, (int, float)):
                payload[name] = value
        for name in ("method", "route", "job_type"):
            value = getattr(record, name, None)
            if isinstance(value, str):
                payload[name] = self._redact(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configure_json_logging(
    *, level: int = logging.INFO, stream: TextIO | None = None, secrets: tuple[str, ...] = ()
) -> None:
    """Configurer le logger racine avec une unique sortie JSON."""

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(secrets=secrets))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # La trace HTTP structurée utilise le patron de route, jamais l'URL avec sa query.
    logging.getLogger("uvicorn.access").disabled = True
