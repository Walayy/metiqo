"""Manual, bounded public-DOM feasibility session. No scheduled or application use."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from patchright.sync_api import Locator, Request, Response, sync_playwright

from metiquo_worker.loltv_policy import retry_after_seconds
from metiquo_worker.stake_audit import (
    AUDIT_ROOT,
    BLOCKED,
    DEFAULT_URL,
    DIAGNOSTIC_HEADERS,
    failure_impact,
    launch_context,
    now,
    observe,
    protection_signals,
    public_url,
    response_kind,
    sports_content_ready,
    validate_url,
    write_json,
)

DOM_SCRIPT = Path(__file__).with_name("stake_dom.js")


def main() -> None:
    state_path = AUDIT_ROOT / "chrome-audit-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if float(state["notBefore"]) > time.time():
            raise SystemExit("Pause locale encore active ; aucune requête envoyée.")
    run_dir = AUDIT_ROOT / "feasibility-runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir.mkdir(parents=True)
    commands = run_dir / "commands"
    commands.mkdir()
    write_json(state_path, {"notBefore": time.time() + 3600, "outcome": "in_progress"})
    started = now()
    responses: list[dict[str, object]] = []
    request_count = 0
    blocked: str | None = None
    retry_after = 0.0
    deadline = time.monotonic() + 1800

    with sync_playwright() as runtime:
        context = launch_context(runtime, AUDIT_ROOT / "chrome-profile")
        page = context.pages[0] if context.pages else context.new_page()
        for extra in context.pages[1:]:
            extra.close()

        def request_handler(request: Request) -> None:
            nonlocal request_count
            request_count += 1

        def response_handler(response: Response) -> None:
            nonlocal blocked, retry_after
            headers = response.headers
            kind = response_kind(response.status, headers, response.url)
            main_document = (
                response.request.is_navigation_request() and response.frame == page.main_frame
            )
            impact = failure_impact(kind, main_document=main_document)
            host = urlsplit(response.url).hostname or ""
            if (host == "stake.bet" or host.endswith(".stake.bet")) and impact == "blocking":
                if kind and blocked is None:
                    blocked = kind
                retry_after = max(
                    retry_after, retry_after_seconds(headers.get("retry-after"), time.time())
                )
            safe_headers = {key: headers[key] for key in DIAGNOSTIC_HEADERS if key in headers}
            if "location" in safe_headers:
                safe_headers["location"] = public_url(safe_headers["location"])
            responses.append(
                {
                    "at": now(),
                    "url": public_url(response.url),
                    "status": response.status,
                    "resourceType": response.request.resource_type,
                    "mainDocument": main_document,
                    "headers": safe_headers,
                    "classification": kind,
                    "impact": impact,
                    "protectionSignals": protection_signals(response.url, headers),
                }
            )

        page.on("request", request_handler)
        page.on("response", response_handler)
        last_action = 0.0
        discovered: set[str] = set()

        def checkpoint() -> None:
            nonlocal blocked
            if page.get_by_text("You are being rate limited", exact=False).count():
                blocked = "rate_limited"
            elif page.title().lower() in {"un instant…", "just a moment...", "just a moment…"}:
                blocked = "challenge"
            if blocked:
                raise RuntimeError(f"Source protection: {blocked}")
            if request_count > 30000 or time.monotonic() >= deadline:
                raise RuntimeError("Manual audit budget reached; no further action")

        def settle(seconds: float) -> None:
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                checkpoint()
                page.wait_for_timeout(200)

        def capture(name: str, *, allow_empty_group: bool = False) -> None:
            nonlocal blocked
            checkpoint()
            readiness_deadline = time.monotonic() + 60
            while (
                not sports_content_ready(page)
                and not (allow_empty_group and page.locator(".groups:visible").count())
                and time.monotonic() < readiness_deadline
            ):
                settle(0.25)
            if not sports_content_ready(page) and not (
                allow_empty_group and page.locator(".groups:visible").count()
            ):
                blocked = "content_unavailable"
                raise RuntimeError("Useful sports content did not load within 60 seconds")
            data = page.evaluate(DOM_SCRIPT.read_text(encoding="utf-8"))
            previous_shape = None
            stable = 0
            for _ in range(8):
                shape = (
                    [tab["testId"] for tab in data["tabs"]],
                    [(market["title"], len(market["selections"])) for market in data["markets"]],
                    [fixture["event"] for fixture in data["fixtures"]],
                )
                stable = stable + 1 if shape == previous_shape else 0
                if stable >= 2:
                    break
                previous_shape = shape
                settle(1)
                data = page.evaluate(DOM_SCRIPT.read_text(encoding="utf-8"))
            data["observedAt"] = now()
            data["emptyGroupRequiresReview"] = not data["markets"] and bool(data["tabs"])
            discovered.update(link["url"] for link in data["links"] if link["url"])
            write_json(run_dir / f"{name}.dom.json", data)
            page.screenshot(path=str(run_dir / f"{name}.png"), timeout=5000)
            write_json(run_dir / "network.json", responses)
            print(
                json.dumps(
                    {
                        "capture": name,
                        "url": data["url"],
                        "fixtures": len(data["fixtures"]),
                        "markets": len(data["markets"]),
                        "tabs": [tab["testId"] for tab in data["tabs"]],
                    }
                ),
                flush=True,
            )

        def click(control: Locator) -> None:
            checkpoint()
            if control.count() != 1:
                raise ValueError("Read-only control must resolve to exactly one element")
            if control.evaluate("e => !!e.closest('[data-testid=fixture-outcome]')"):
                raise ValueError("Bet selections must never be clicked")
            control.click(timeout=10000)
            settle(1.5)

        outcome = "in_progress"
        error = None
        completed_actions = 0
        try:
            print(json.dumps({"session": str(run_dir.resolve()), "startedAt": started}), flush=True)
            initial = observe(page, DEFAULT_URL)
            write_json(run_dir / "entry.json", initial)
            if initial["outcome"] in BLOCKED:
                blocked = str(initial["outcome"])
            checkpoint()
            if initial["outcome"] != "sports_links_observed":
                raise RuntimeError("Entry readiness not established")
            capture("000-esports")
            last_action = time.monotonic()
            handled: set[str] = set()
            while completed_actions < 300:
                checkpoint()
                pending = [p for p in sorted(commands.glob("*.json")) if p.name not in handled]
                if not pending:
                    page.wait_for_timeout(250)
                    continue
                path = pending[0]
                handled.add(path.name)
                command = json.loads(path.read_text(encoding="utf-8"))
                name = command["name"]
                if not re.fullmatch(r"[a-z0-9-]+", name):
                    raise ValueError("Invalid evidence name")
                action = command["action"]
                if action == "stop":
                    outcome = "manual_session_finished"
                    break
                settle(max(0, last_action + 5 - time.monotonic()))
                try:
                    if action == "navigate":
                        target = validate_url(command["url"])
                        if target not in discovered:
                            raise ValueError("Navigation target was not discovered in this session")
                        page.goto(target, wait_until="domcontentloaded", timeout=45000)
                        settle(3)
                    elif action == "tab":
                        test_id = command["testId"]
                        if not re.fullmatch(r"tab-[A-Za-z0-9-]+", test_id):
                            raise ValueError("Invalid public market tab")
                        click(page.locator(".groups").get_by_test_id(test_id))
                    elif action == "expand":
                        group = page.locator(".groups .secondary-accordion").nth(command["index"])
                        if "is-open" not in (group.get_attribute("class") or "").split():
                            click(group.locator(":scope > .header"))
                    elif action == "market-more":
                        group = page.locator(".groups .secondary-accordion").nth(command["index"])
                        label = command["label"]
                        if label not in {"Tout", "Charger Plus", "Charger plus", "Afficher plus"}:
                            raise ValueError("Invalid market expansion control")
                        click(group.get_by_role("button", name=label, exact=True))
                    elif action == "listing-more":
                        label = command["label"]
                        if not re.fullmatch(
                            r"Tout|Tous|Toutes|Charger [Pp]lus|Afficher plus|Suivant|\d+", label
                        ):
                            raise ValueError("Invalid public listing control")
                        click(
                            page.locator("#main-content").get_by_role(
                                "button", name=label, exact=True
                            )
                        )
                    elif action == "scroll-bottom":
                        page.locator("#scrollable").evaluate(
                            "e => { e.scrollTop = e.scrollHeight; }"
                        )
                        settle(2)
                    elif action == "dismiss-cookies":
                        consent = page.get_by_test_id("accept-cookie-consent")
                        if consent.count() and consent.is_visible():
                            click(consent)
                    elif action != "capture":
                        raise ValueError("Unknown manual audit action")
                    capture(name, allow_empty_group=action in {"tab", "capture"})
                except Exception as action_error:
                    if blocked:
                        raise
                    write_json(
                        run_dir / f"{name}.error.json",
                        {
                            "at": now(),
                            "action": action,
                            "error": str(action_error),
                            "url": public_url(page.url),
                        },
                    )
                    print(
                        json.dumps({"commandError": name, "error": str(action_error)}), flush=True
                    )
                completed_actions += 1
                last_action = time.monotonic()
            else:
                outcome = "action_budget_reached"
        except Exception as exc:
            outcome = blocked or "incomplete"
            error = str(exc)
        finally:
            summary = {
                "startedAt": started,
                "finishedAt": now(),
                "outcome": outcome,
                "error": error,
                "url": public_url(page.url),
                "title": page.title(),
                "patchright": version("patchright"),
                "chrome": context.browser.version if context.browser else None,
                "requestEvents": request_count,
                "responsesObserved": len(responses),
                "mainDocumentStatuses": [row["status"] for row in responses if row["mainDocument"]],
                "refusals": [row for row in responses if row["classification"] in BLOCKED],
                "blockingRefusals": [row for row in responses if row["impact"] == "blocking"],
                "auxiliaryRefusals": [row for row in responses if row["impact"] == "auxiliary"],
                "completedActionsAfterEntry": completed_actions,
                "retryAfterSeconds": retry_after,
                "coverageCertified": False,
            }
            write_json(run_dir / "network.json", responses)
            write_json(run_dir / "summary.json", summary)
            write_json(
                state_path,
                {
                    "notBefore": time.time() + max(3600 if blocked else 60, retry_after),
                    "outcome": outcome,
                },
            )
            try:
                page.screenshot(path=str(run_dir / "final.png"), timeout=5000)
            finally:
                context.close()
                write_json(
                    run_dir / "manifest.json",
                    {
                        "files": [
                            {
                                "path": p.name,
                                "bytes": p.stat().st_size,
                                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                            }
                            for p in sorted(run_dir.iterdir())
                            if p.is_file() and p.name != "manifest.json"
                        ]
                    },
                )
            print(json.dumps({"outcome": outcome, "evidence": str(run_dir.resolve())}), flush=True)
    if blocked or outcome != "manual_session_finished":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
