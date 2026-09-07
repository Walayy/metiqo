"""La recette refuse les preuves absentes, modifiées ou portant sur un autre commit."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from infra.scripts.acceptance import (
    evaluate_criteria,
    extract_verified_archive,
    junit_cases,
    verify_manual_review,
    verify_runs,
)
from infra.scripts.startup_acceptance import compose_services


def test_missing_tests_never_turn_into_an_acceptance_pass() -> None:
    result = evaluate_criteria(set(), set(), startup_ok=False, manual_ok=False)
    assert len(result) == 22
    assert all(row["status"] == "FAIL" for row in result)
    cases = {
        "tests.integration.test_ingestion_gate::test_ingestion_gate_demo_rebuilds_from_empty_database"
    }
    result = evaluate_criteria(cases, set(), startup_ok=False, manual_ok=False)
    assert result[3]["status"] == result[4]["status"] == "PASS"
    assert result[2]["status"] == "FAIL"  # Reprise du backfill encore absente.


def test_junit_refuses_skips_failures_empty_or_duplicate_test_identity(tmp_path: Path) -> None:
    path = tmp_path / "run.xml"
    path.write_text('<testsuite><testcase classname="real" name="atomicity"/></testsuite>')
    assert junit_cases(path) == {"real::atomicity"}
    for body in (
        "",
        '<testcase classname="real" name="atomicity"><skipped/></testcase>',
        '<testcase classname="real" name="atomicity"><failure/></testcase>',
        '<testcase classname="real" name="atomicity"><error/></testcase>',
        '<testcase classname="real" name="atomicity"/>' * 2,
    ):
        path.write_text(f"<testsuite>{body}</testsuite>")
        with pytest.raises(ValueError):
            junit_cases(path)


def test_successful_workflow_from_another_revision_is_rejected() -> None:
    with pytest.raises(ValueError, match="commit"):
        verify_runs({"headSha": "a" * 40}, {"headSha": "a" * 40}, "b" * 40, "")


def test_all_gates_and_the_actual_negative_fault_are_required() -> None:
    revision = "a" * 40
    positive = {
        "headSha": revision,
        "status": "completed",
        "conclusion": "success",
        "jobs": [
            {"name": name, "conclusion": "success"}
            for name in (
                "Qualité",
                "Migrations PostgreSQL",
                "Interface Playwright",
                "Build Docker",
                "Gate MVP",
            )
        ],
    }
    negative = {
        "headSha": revision,
        "status": "completed",
        "conclusion": "failure",
        "jobs": [
            {
                "name": "Qualité",
                "steps": [
                    {"name": "Injecter la faute temporelle", "conclusion": "success"},
                    {"name": "Vérifier le cutoff critique", "conclusion": "failure"},
                ],
            },
            {"name": "Gate MVP", "conclusion": "failure"},
        ],
    }
    log = (
        "FAILED tests/leakage/test_time.py::"
        "test_property_every_nonnegative_event_offset_is_rejected"
    )
    verify_runs(positive, negative, revision, log)
    for state in ("skipped", "cancelled", "failure"):
        broken = json.loads(json.dumps(positive))
        broken["jobs"][0]["conclusion"] = state
        with pytest.raises(ValueError):
            verify_runs(broken, negative, revision, log)
    with pytest.raises(ValueError):
        verify_runs(positive, negative, revision, "")
    broken = json.loads(json.dumps(negative))
    broken["jobs"][0]["steps"][0]["conclusion"] = "failure"
    with pytest.raises(ValueError):
        verify_runs(positive, broken, revision, log)


def test_compose_json_array_and_stream_preserve_each_service() -> None:
    services = [
        {"Service": name, "State": "running", "Health": "healthy"} for name in ("api", "worker")
    ]
    assert compose_services(json.dumps(services)) == services
    assert compose_services("\n".join(json.dumps(item) for item in services)) == services


def test_artifact_digest_and_archive_paths_are_verified(tmp_path: Path) -> None:
    def archive(name: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr(name, "evidence")
        return buffer.getvalue()

    payload = archive("data/result.json")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    extract_verified_archive(payload, digest, tmp_path / "valid")
    assert (tmp_path / "valid/data/result.json").read_text() == "evidence"
    with pytest.raises(ValueError, match="empreinte"):
        extract_verified_archive(payload + b"altered", digest, tmp_path / "bad")
    payload = archive("../outside.txt")
    with pytest.raises(ValueError, match="chemin"):
        extract_verified_archive(
            payload, "sha256:" + hashlib.sha256(payload).hexdigest(), tmp_path / "escape"
        )
    assert not (tmp_path / "outside.txt").exists()


def test_manual_visual_review_is_bound_to_sources_and_images(tmp_path: Path) -> None:
    source = tmp_path / "view.tsx"
    source.write_text("reviewed source")
    item = {"path": "view.tsx", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    report = tmp_path / "docs/evidence/qa-006/report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "status": "passed",
                "manualReview": {
                    "reviewer": "Synthetic test reviewer",
                    "reviewedAt": "2026-09-07T00:00:00Z",
                    "scope": "Synthetic fixture",
                    "captures": [item],
                    "sourceHashes": [item],
                },
            }
        )
    )
    verify_manual_review(tmp_path)
    source.write_text("changed since inspection")
    with pytest.raises(ValueError, match="revue"):
        verify_manual_review(tmp_path)
