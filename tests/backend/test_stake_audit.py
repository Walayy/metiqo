import json
import time

import pytest
from metiquo_worker import stake_audit
from metiquo_worker.stake_audit import (
    BLOCKED,
    KASADA_PATH_PREFIX,
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
