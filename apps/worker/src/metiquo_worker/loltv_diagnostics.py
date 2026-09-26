"""Explicit source availability conditions, with safe persisted diagnostics."""

from typing import cast

import httpx
from metiquo_core.source_issues import safe_source_issues


class LoltvSourceError(ValueError):
    def __init__(self, code: str, message: str, **context: object):
        super().__init__(message)
        self.code, self.context = code, context


def record_issue(
    metrics: dict[str, object],
    url: str,
    error: Exception,
    *,
    event_id: str | None = None,
    unavailable: bool = False,
) -> None:
    code = (
        error.code
        if isinstance(error, LoltvSourceError)
        else "loltv_http_error"
        if isinstance(error, httpx.HTTPError)
        else "loltv_page_invalid"
    )
    context = error.context if isinstance(error, LoltvSourceError) else {}
    issue = safe_source_issues([{"code": code, "resource": url, "eventId": event_id, **context}])[0]
    cast(list[object], metrics.setdefault("sourceIssues", [])).append(issue)
    if not unavailable:
        cast(list[object], metrics.setdefault("errors", [])).append(
            {
                "url": issue.get("resource"),
                "error": type(error).__name__,
                "message": issue["reason"],
            }
        )
