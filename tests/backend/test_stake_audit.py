import json
import time
from types import SimpleNamespace

import pytest
from metiquo_worker import stake_audit, stake_browser
from metiquo_worker.stake_audit import (
    BLOCKED,
    KASADA_PATH_PREFIX,
    cloudflare_ray,
    failure_impact,
    protection_signals,
    public_url,
    response_kind,
    validate_url,
)


@pytest.mark.parametrize(
    ("status", "headers", "expected"),
    [
        (403, {"cf-mitigated": "challenge"}, "challenge"),
        (200, {"cf-mitigated": "challenge"}, "challenge"),
        (403, {}, "access_denied"),
        (429, {"cf-mitigated": "challenge"}, "challenge"),
        (429, {"cf-ray": "synthetic-ray"}, "http_429"),
        (401, {}, None),  # A PAT response must not become a Stake account error.
        (200, {}, None),
    ],
)
def test_refusals_are_not_conflated(status, headers, expected):
    assert response_kind(status, headers) == expected


def test_kasada_like_child_429_is_diagnostic_without_asserting_a_rate_limit():
    url = "https://stake.bet" + KASADA_PATH_PREFIX + "fp"
    kind = response_kind(429, {"cf-ray": "synthetic-ray"}, url)
    assert kind == "challenge_suspected"
    assert kind in BLOCKED
    assert failure_impact(kind, main_document=False) == "auxiliary"
    assert protection_signals(url, {}) == ["kasada_public_path"]


@pytest.mark.parametrize("kind", ["challenge", "challenge_suspected", "http_429", "access_denied"])
def test_only_main_document_refusals_block_navigation(kind):
    assert failure_impact(kind, main_document=True) == "blocking"
    assert failure_impact(kind, main_document=False) == "auxiliary"
    assert failure_impact(None, main_document=True) is None


def test_sdk_header_values_never_enter_diagnostic_signals():
    headers = {"X-Kpsdk-Ct": "private-token-not-to-log"}
    assert protection_signals("https://stake.bet/other", headers) == ["kasada_header_name"]
    assert response_kind(403, headers) == "challenge_suspected"
    assert response_kind(200, headers) is None


def test_cloudflare_ray_is_bounded_and_does_not_archive_arbitrary_headers():
    assert cloudflare_ray({"CF-Ray": "230b030023ae2822-SJC"}) == "230b030023ae2822-SJC"
    assert cloudflare_ray({"cf-ray": "token=secret"}) is None
    assert cloudflare_ray({"cf-ray": "a" * 100 + "-SJC"}) is None


def test_generic_fingerprint_path_is_not_attributed_to_a_vendor():
    assert response_kind(429, {}, "https://stake.bet/another/path/fp") == "http_429"


def test_challenge_path_tokens_and_url_secrets_are_not_archived():
    url = "https://name:password@challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/pat/secret?token=private#fragment"
    assert public_url(url) == (
        "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/pat/[redacted]"
    )
    assert public_url("https://stake.bet/fr/sports/esports?session=secret") == (
        "https://stake.bet/fr/sports/esports"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://stake.bet.evil.test/fr/sports/esports",
        "http://stake.bet/fr/sports/esports",
        "https://stake.bet/fr/account",
        "https://stake.bet/fr/sports/esports?token=secret",
        "https://user:password@stake.bet/fr/sports/esports",
        "https://stake.bet/fr/sports/%2e%2e/account",
        "https://stake.bet/fr/sports/../account",
    ],
)
def test_audit_entry_point_rejects_other_origins_and_private_routes(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_persisted_pause_prevents_browser_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(stake_audit, "AUDIT_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["stake_audit"])
    (tmp_path / "chrome-audit-state.json").write_text(
        json.dumps({"notBefore": time.time() + 3600}), encoding="utf-8"
    )

    def forbidden_launch():
        pytest.fail("The browser must not start while the source pause is active")

    monkeypatch.setattr(stake_audit, "sync_playwright", forbidden_launch)
    with pytest.raises(SystemExit, match="aucune requête"):
        stake_audit.main()


@pytest.mark.parametrize("clears", [True, False])
def test_main_challenge_gets_one_passive_wait_before_blocking(monkeypatch, clears):
    clock = [0.0]
    monkeypatch.setattr(stake_browser.time, "monotonic", lambda: clock[0])

    class Page:
        def goto(self, *_args, **_kwargs):
            return None

        def title(self):
            return "Sports" if clears and clock[0] >= 3 else "Just a moment..."

        def get_by_text(self, *_args, **_kwargs):
            return SimpleNamespace(count=lambda: 0)

        def locator(self, *_args, **_kwargs):
            return SimpleNamespace(count=lambda: 0)

    browser = object.__new__(stake_browser.StakeBrowser)
    browser.settings = SimpleNamespace(stake_timeout_seconds=5)
    browser.page = Page()
    browser.discovered = {stake_audit.DEFAULT_URL}
    browser.pending_main_refusals = []
    browser.pending_retry_after = 0.0
    browser.before_action = lambda: None
    browser.wait = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    browser._block_visible_protection = lambda reason: (_ for _ in ()).throw(RuntimeError(reason))

    if clears:
        browser.navigate(stake_audit.DEFAULT_URL)
        assert clock[0] == 3
    else:
        with pytest.raises(RuntimeError, match="challenge"):
            browser.navigate(stake_audit.DEFAULT_URL)
        assert clock[0] == 7
