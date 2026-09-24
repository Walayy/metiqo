"""Manual, single-page Stake audit. Never registered with the collector or scheduler."""

import argparse
import hashlib
import json
import posixpath
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from patchright.sync_api import BrowserContext, Page, Playwright, Request, Response, sync_playwright
from patchright.sync_api import TimeoutError as BrowserTimeout

from metiquo_worker.loltv_policy import retry_after_seconds

AUDIT_ROOT = Path(".cache/stake-audit")
DEFAULT_URL = "https://stake.bet/fr/sports/esports"
DIAGNOSTIC_HEADERS = ("cf-mitigated", "cf-ray", "content-type", "retry-after", "location")
BLOCKED = {
    "challenge",
    "challenge_suspected",
    "access_denied",
    "http_429",
    "rate_limited",
    "content_unavailable",
}
# Public integration path, not a credential. A match is an attribution hint, not proof.
KASADA_PATH_PREFIX = "/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39-8ed7-437e-a3be-862e0f06eea3/"


def now() -> str:
    return datetime.now(UTC).isoformat()


def public_url(value: str) -> str:
    """Do not archive query parameters, credentials or opaque challenge path tokens."""
    parts = urlsplit(value)
    path = parts.path
    if "/cdn-cgi/challenge-platform/" in path:
        phase = "pat" if "/pat/" in path else "challenge"
        path = f"/cdn-cgi/challenge-platform/{phase}/[redacted]"
    path = re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "[opaque-id]", path)
    return urlunsplit((parts.scheme, parts.hostname or "", path, "", ""))


def validate_url(value: str) -> str:
    parts = urlsplit(value)
    decoded_path = unquote(parts.path).replace("\\", "/")
    if (
        parts.scheme != "https"
        or parts.hostname != "stake.bet"
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not posixpath.normpath(decoded_path).startswith("/fr/sports/")
    ):
        raise ValueError(
            "Une URL publique https://stake.bet/fr/sports/ sans paramètres est requise"
        )
    return value


def protection_signals(url: str, headers: Mapping[str, str]) -> list[str]:
    """Preserve diagnostic markers without logging SDK token values."""
    signals = []
    if urlsplit(url).path.startswith(KASADA_PATH_PREFIX):
        signals.append("kasada_public_path")
    if any(key.lower().startswith("x-kpsdk-") for key in headers):
        signals.append("kasada_header_name")
    return signals


def cloudflare_ray(headers: Mapping[str, str]) -> str | None:
    """Keep only a bounded Cloudflare request identifier for source support."""
    value = next((v for k, v in headers.items() if k.lower() == "cf-ray"), "")
    return value if re.fullmatch(r"[0-9a-fA-F]{8,32}-[A-Za-z]{3}", value) else None


def response_kind(status: int, headers: Mapping[str, str], url: str = "") -> str | None:
    normalized = {key.lower(): value for key, value in headers.items()}
    if normalized.get("cf-mitigated", "").lower() == "challenge":
        return "challenge"
    if status in (403, 429) and protection_signals(url, headers):
        return "challenge_suspected"
    if status == 403:
        return "access_denied"
    if status == 429:
        # HTTP status alone does not identify the emitter or its rule, even with cf-ray.
        return "http_429"
    return None


def failure_impact(kind: str | None, *, main_document: bool) -> str | None:
    """A failed child resource is diagnostic; actual sports readiness decides its impact."""
    if kind is None:
        return None
    return "blocking" if main_document else "auxiliary"


def sports_content_ready(page: Page) -> bool:
    """Require useful rendered sports content, not a link in an unready navigation shell."""
    return (
        page.locator(
            '#main-content [data-testid="fixture-preview"]:visible, '
            '#main-content .groups [data-testid="fixture-outcome"]:visible, '
            '#main-content a[href*="/sports/league-of-legends/"]:visible'
        ).count()
        > 0
    )


def launch_context(runtime: Playwright, profile_dir: Path) -> BrowserContext:
    """Use the upstream configuration, with an audit-only profile, never a personal one."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    return runtime.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir.resolve()),
        channel="chrome",
        headless=False,
        no_viewport=True,
        accept_downloads=False,
    )


def observe(page: Page, url: str) -> dict[str, object]:
    """Navigate once, diagnose refusals, and wait for visible source content up to 60 s."""
    responses: list[dict[str, object]] = []
    requests = 0
    outcome = "readiness_timeout"
    retry_after = 0.0
    deadline = time.monotonic() + 60

    def on_request(request: Request) -> None:
        nonlocal requests
        requests += 1

    def on_response(response: Response) -> None:
        nonlocal outcome, retry_after
        source_headers = response.headers
        headers = {key: source_headers[key] for key in DIAGNOSTIC_HEADERS if key in source_headers}
        if "location" in headers:
            headers["location"] = public_url(headers["location"])
        kind = response_kind(response.status, source_headers, response.url)
        main_document = (
            response.request.is_navigation_request() and response.frame == page.main_frame
        )
        impact = failure_impact(kind, main_document=main_document)
        host = urlsplit(response.url).hostname or ""
        if (host == "stake.bet" or host.endswith(".stake.bet")) and impact == "blocking":
            if kind and outcome not in BLOCKED:
                outcome = kind
            retry_after = max(
                retry_after, retry_after_seconds(headers.get("retry-after"), time.time())
            )
        responses.append(
            {
                "at": now(),
                "url": public_url(response.url),
                "status": response.status,
                "resourceType": response.request.resource_type,
                "mainDocument": main_document,
                "headers": headers,
                "classification": kind,
                "impact": impact,
                "protectionSignals": protection_signals(response.url, source_headers),
            }
        )

    page.on("request", on_request)
    page.on("response", on_response)
    started = now()
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except BrowserTimeout:
            if outcome not in BLOCKED:
                outcome = "navigation_timeout"
        while outcome not in BLOCKED and time.monotonic() < deadline:
            title = page.title().lower()
            if title in {"un instant…", "just a moment...", "just a moment…"}:
                outcome = "challenge"
                break
            if page.get_by_text("You are being rate limited", exact=False).count():
                outcome = "rate_limited"
                break
            if sports_content_ready(page):
                outcome = "sports_links_observed"
                break
            page.wait_for_timeout(250)
        if outcome in {"readiness_timeout", "navigation_timeout"}:
            outcome = "content_unavailable"
        # A 1015 page can accompany a generic 403. Inspect its visible marker once.
        if page.get_by_text("You are being rate limited", exact=False).count():
            outcome = "rate_limited"
        elif outcome == "access_denied" and page.title().lower() in {
            "un instant…",
            "just a moment...",
            "just a moment…",
        }:
            outcome = "challenge"
        return {
            "startedAt": started,
            "observedAt": now(),
            "url": public_url(page.url),
            "title": page.title(),
            "outcome": outcome,
            "requestCount": requests,
            "mainDocumentStatuses": [row["status"] for row in responses if row["mainDocument"]],
            "refusals": [row for row in responses if row["classification"] in BLOCKED],
            "blockingRefusals": [row for row in responses if row["impact"] == "blocking"],
            "auxiliaryRefusals": [row for row in responses if row["impact"] == "auxiliary"],
            "responses": responses,
            "retryAfterSeconds": retry_after,
            "viewport": page.evaluate(
                "({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})"
            ),
        }
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("response", on_response)


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    args = parser.parse_args()
    url = validate_url(args.url)
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    state_path = AUDIT_ROOT / "chrome-audit-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if float(state["notBefore"]) > time.time():
            raise SystemExit("Pause locale encore active ; aucune requête envoyée.")
    run_dir = AUDIT_ROOT / "chrome-runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir.mkdir(parents=True)
    # Conservative local pacing, not a claim about Stake's quota. No automatic retries.
    write_json(state_path, {"notBefore": time.time() + 3600, "outcome": "in_progress"})
    with sync_playwright() as runtime:
        context = launch_context(runtime, AUDIT_ROOT / "chrome-profile")
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for extra_page in context.pages[1:]:
                extra_page.close()
            evidence = observe(page, url)
            evidence["runtime"] = {
                "patchright": version("patchright"),
                "chrome": context.browser.version if context.browser else None,
                "channel": "chrome",
                "headless": False,
                "noViewport": True,
                "profile": "dedicated persistent local profile; excluded from evidence",
                "userAgentOverride": False,
                "customHeaders": False,
            }
            wait = max(
                3600 if evidence["outcome"] in BLOCKED else 60,
                float(str(evidence["retryAfterSeconds"])),
            )
            write_json(
                state_path, {"notBefore": time.time() + wait, "outcome": evidence["outcome"]}
            )
            write_json(run_dir / "observation.json", evidence)
            page.screenshot(path=str(run_dir / "page.png"), timeout=5000)
        finally:
            context.close()
    write_json(
        run_dir / "manifest.json",
        {
            "files": [
                {"path": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
                for file in sorted(run_dir.iterdir())
            ]
        },
    )
    print(json.dumps({"outcome": evidence["outcome"], "evidence": str(run_dir.resolve())}))
    if evidence["outcome"] != "sports_links_observed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
