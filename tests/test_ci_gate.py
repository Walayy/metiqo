"""La release refuse une preuve absente, un test sauté et un job critique non vert."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from infra.scripts.inject_critical_fault import inject
from infra.scripts.verify_release_evidence import verify_jobs, verify_junit

ROOT = Path(__file__).resolve().parents[1]


def test_aggregate_requires_every_mandatory_job_to_succeed() -> None:
    passing = {name: {"result": "success"} for name in ("quality", "runtime", "e2e")}
    verify_jobs(passing)
    for status in ("failure", "skipped", "cancelled", ""):
        with pytest.raises(ValueError):
            verify_jobs(passing | {"runtime": {"result": status}})
    with pytest.raises(ValueError):
        verify_jobs({"quality": {"result": "success"}})


def test_junit_requires_executed_tests_without_skips_or_failures(tmp_path: Path) -> None:
    report = tmp_path / "tests.xml"
    with pytest.raises((OSError, ValueError)):
        verify_junit(report)
    report.write_text(
        '<testsuites><testsuite><testcase name="atomicity"/></testsuite></testsuites>'
    )
    assert verify_junit(report) == 1
    for state in ("skipped", "failure", "error"):
        report.write_text(
            f"<testsuites><testsuite><testcase><{state}/></testcase></testsuite></testsuites>"
        )
        with pytest.raises(ValueError):
            verify_junit(report)
    report.write_text("<testsuites/>")
    with pytest.raises(ValueError):
        verify_junit(report)


def test_actual_leakage_suite_fails_with_the_ci_cutoff_fault(tmp_path: Path) -> None:
    source = ROOT / "python/metiquo/features/temporal.py"
    before = source.read_bytes()
    shutil.copytree(
        ROOT / "python/metiquo",
        tmp_path / "python/metiquo",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    evidence = inject(tmp_path)
    assert evidence["beforeSha256"] != evidence["afterSha256"]
    configuration = tmp_path / "pytest.ini"
    configuration.write_text("[pytest]\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(configuration),
            str(ROOT / "tests/leakage"),
            "-q",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path / "python")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAILED" in result.stdout
    assert "test_property_every_nonnegative_event_offset_is_rejected" in result.stdout
    assert source.read_bytes() == before
