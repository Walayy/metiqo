"""Le scanner officiel doit détecter une sentinelle sans afficher sa valeur."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_gitleaks_detects_synthetic_key_and_redacts_report(tmp_path: Path) -> None:
    binary = os.environ.get("GITLEAKS_BINARY")
    if not binary:
        pytest.skip("GITLEAKS_BINARY requis")
    # Valeur inventée et jamais liée à un compte ; assemblée pour éviter une alerte dans le test.
    synthetic = "ghp_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0iL3oR6"
    (tmp_path / "leak.txt").write_text(f'github_token = "{synthetic}"', encoding="utf-8")
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            binary,
            "dir",
            str(tmp_path),
            "--redact",
            "--no-banner",
            "--config",
            str(ROOT / ".gitleaks.toml"),
            "--report-format",
            "json",
            "--report-path",
            str(report),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    findings = json.loads(report.read_text(encoding="utf-8"))
    assert any(item["RuleID"] == "github-pat" for item in findings)
    assert synthetic not in result.stdout + result.stderr + report.read_text(encoding="utf-8")


@pytest.mark.integration
def test_reviewed_evidence_checksums_do_not_exempt_other_secrets_or_paths(tmp_path: Path) -> None:
    binary = os.environ.get("GITLEAKS_BINARY")
    if not binary:
        pytest.skip("GITLEAKS_BINARY requis")
    evidence = tmp_path / "docs/evidence/qa-004/report.json"
    evidence.parent.mkdir(parents=True)
    checksum = "d4cf2c5f140e53218a3fb853b606f0877faa2d8570e85c49ec987af1788e1900"
    evidence.write_text(json.dumps({"qa004-openapi.log": checksum}))
    report = tmp_path / "result.json"

    def scan() -> int:
        result = subprocess.run(
            [
                binary,
                "dir",
                str(evidence.parent),
                "--redact",
                "--no-banner",
                "--config",
                str(ROOT / ".gitleaks.toml"),
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode

    assert scan() == 0
    (evidence.parent / "another.json").write_text(evidence.read_text())
    assert scan() == 1
    synthetic = "ghp_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0iL3oR6"
    evidence.write_text(json.dumps({"api_key": synthetic}))
    assert scan() == 1
    findings = json.loads(report.read_text())
    assert any(
        item["RuleID"] == "github-pat" and item["File"].endswith("report.json") for item in findings
    )
    assert synthetic not in report.read_text()
