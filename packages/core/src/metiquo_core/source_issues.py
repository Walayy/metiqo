"""Allowlisted LoLTV diagnostics shared by the worker and the admin API."""

import re
from urllib.parse import urlsplit

LOLTV_ISSUES = {
    "loltv_stale_listing": ("listing", "Calendrier source en cache depuis plus de 24 heures."),
    "loltv_detail_missing": (
        "detail",
        "La fiche source ne fournit pas le détail de cette rencontre.",
    ),
    "loltv_unknown_state": ("listing", "Un statut source inconnu a été écarté."),
    "loltv_feed_unavailable": (
        "feed",
        "Le flux de la carte n'a pas encore de données disponibles.",
    ),
    "loltv_feed_invalid": (
        "feed",
        "Le flux de la carte ne satisfait pas les contrôles de lecture.",
    ),
    "loltv_page_invalid": (
        "validation",
        "Le document source ne satisfait pas les contrôles de lecture.",
    ),
    "loltv_http_error": (
        "download",
        "La lecture du document source a rencontré une erreur réseau.",
    ),
}
_resource = re.compile(
    r"/(?:matches(?:/results)?(?:/all/[0-9]+)?|match/[a-zA-Z0-9_-]+|feed/[a-zA-Z0-9_-]+)\Z"
)
_identifier = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def source_resource(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        path = urlsplit(value).path
    except ValueError:
        return None
    return path if len(path) <= 200 and _resource.fullmatch(path) else None


def safe_source_issues(value: object) -> list[dict[str, object]]:
    """Never expose arbitrary provider text, exception strings, queries or cookies."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("code"), str) or item["code"] not in LOLTV_ISSUES:
            continue
        code = str(item["code"])
        stage, reason = LOLTV_ISSUES[code]
        issue: dict[str, object] = {"code": code, "stage": stage, "reason": reason}
        resource = source_resource(item.get("resource"))
        if resource:
            issue["resource"] = resource
        event_id = item.get("eventId")
        if isinstance(event_id, str) and _identifier.fullmatch(event_id):
            issue["eventId"] = event_id
        age = item.get("cacheAgeSeconds")
        if isinstance(age, int) and not isinstance(age, bool) and age >= 0:
            issue["cacheAgeSeconds"] = age
        state = item.get("sourceState")
        if isinstance(state, str) and state in {"UNSTARTED", "STARTED", "PAUSED", "COMPLETED"}:
            issue["sourceState"] = state
        result.append(issue)
    return result


def historical_loltv_issues(errors: object) -> list[dict[str, object]]:
    """Read only recognized legacy messages; their raw text is never returned."""
    if not isinstance(errors, list):
        return []
    issues: list[dict[str, object]] = []
    for error in errors[:100]:
        if not isinstance(error, dict):
            continue
        message = error.get("message")
        if not isinstance(message, str):
            continue
        code = (
            "loltv_unknown_state"
            if message.startswith("Unknown LoLTV match state:")
            else "loltv_stale_listing"
            if message.startswith("LoLTV listing cache is stale (Age:")
            else "loltv_detail_missing"
            if message == "LoLTV HTML does not identify the requested match"
            else "loltv_feed_invalid"
            if message == "LoLTV timestamp is missing"
            else "loltv_page_invalid"
        )
        issues.append({"code": code, "resource": error.get("url")})
    return safe_source_issues(issues)
