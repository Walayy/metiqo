"""Un rapport manquant, une exception périmée ou une faille critique bloque le gate."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from infra.scripts.scan_security import validate_database
from infra.scripts.security_policy import (
    Finding,
    evaluate_findings,
    parse_frontend,
    parse_python,
    parse_trivy,
)

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def test_report_adapters_preserve_real_affected_versions() -> None:
    findings = parse_frontend(
        {
            "advisories": {
                "1": {
                    "github_advisory_id": "GHSA-fixture",
                    "module_name": "fixture",
                    "severity": "critical",
                    "findings": [{"version": "4.2.0"}],
                }
            },
            "metadata": {"vulnerabilities": {"critical": 1}},
        }
    )
    assert evaluate_findings(findings, {"exceptions": []}, NOW)["passed"] is False
    assert findings[0].version == "4.2.0"
    with pytest.raises(ValueError):
        parse_frontend({"advisories": {}, "metadata": {"vulnerabilities": {"critical": 1}}})


def test_database_age_is_a_release_requirement() -> None:
    valid = {"Version": "0.74.0", "VulnerabilityDB": {"UpdatedAt": "2026-09-06T00:00:00Z"}}
    validate_database(valid, NOW)
    for changed in ("2026-09-04T00:00:00Z", "2026-09-08T00:00:00Z"):
        with pytest.raises(ValueError):
            validate_database({**valid, "VulnerabilityDB": {"UpdatedAt": changed}}, NOW)


def test_release_command_fails_for_a_real_critical_report_and_missing_file(tmp_path: Path) -> None:
    report = tmp_path / "critical.json"
    report.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactName": "fixture-image",
                "Results": [
                    {
                        "Target": "fixture-image",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-fixture",
                                "PkgName": "fixture",
                                "InstalledVersion": "1.0",
                                "Severity": "CRITICAL",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "infra.scripts.security_policy",
        "--ecosystem",
        "image",
        "--report",
    ]
    refused = subprocess.run([*command, str(report)], capture_output=True, text=True, check=False)
    assert refused.returncode == 1
    assert json.loads(refused.stdout)["passed"] is False
    missing = subprocess.run(
        [*command, str(tmp_path / "missing.json")], capture_output=True, text=True, check=False
    )
    assert missing.returncode == 2


def test_critical_and_unknown_findings_cannot_pass_silently() -> None:
    findings = [
        Finding("image", "CVE-fixture", "fixture-package", "1.0", "CRITICAL"),
        Finding("python", "PYSEC-fixture", "fixture-dependency", "1.0", "UNKNOWN"),
        Finding("frontend", "GHSA-fixture", "fixture-low", "1.0", "LOW"),
    ]
    result = evaluate_findings(findings, {"exceptions": []}, NOW)
    assert result["passed"] is False and len(result["blocking"]) == 2
    assert len(result["reported"]) == 1


def test_exceptions_require_scoped_evidence_and_expire() -> None:
    finding = Finding("image", "CVE-fixture", "fixture-package", "1.0", "CRITICAL")
    exception = {
        "ecosystem": "image",
        "id": "CVE-fixture",
        "package": "fixture-package",
        "version": "1.0",
        "approvedAt": "2026-09-01",
        "expiresAt": "2026-09-08",
        "approvedBy": "fixture-owner",
        "evidence": "docs/security/fixture-evidence.md",
        "reason": "Synthetic policy test only",
    }
    assert evaluate_findings([finding], {"exceptions": [exception]}, NOW)["passed"] is True
    assert (
        evaluate_findings([finding], {"exceptions": [exception]}, datetime(2026, 9, 9, tzinfo=UTC))[
            "passed"
        ]
        is False
    )
    with pytest.raises(ValueError):
        evaluate_findings([finding], {"exceptions": [{**exception, "evidence": ""}]}, NOW)
    assert (
        evaluate_findings(
            [Finding("image", "CVE-fixture", "fixture-package", "2.0", "CRITICAL")],
            {"exceptions": [exception]},
            NOW,
        )["passed"]
        is False
    )


def test_scanner_reports_are_validated_before_acceptance() -> None:
    assert parse_python({"dependencies": [{"name": "safe", "version": "1", "vulns": []}]}) == []
    assert (
        parse_frontend({"advisories": {}, "metadata": {"vulnerabilities": {"critical": 0}}}) == []
    )
    assert parse_trivy({"SchemaVersion": 2, "ArtifactName": "image", "Results": []}) == []
    for parser in (parse_python, parse_frontend, parse_trivy):
        with pytest.raises(ValueError):
            parser({"error": "scanner unavailable"})
    with pytest.raises(ValueError):
        parse_python(
            {"dependencies": [{"name": "missing", "version": "1", "skip_reason": "not found"}]}
        )
