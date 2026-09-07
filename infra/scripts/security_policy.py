"""Strict scanner adapters and the release policy, independent of scanner execution."""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL", "INFO"}


@dataclass(frozen=True)
class Finding:
    ecosystem: str
    id: str
    package: str
    version: str
    severity: str
    fixed_version: str = ""
    target: str = ""

    def __post_init__(self) -> None:
        if self.ecosystem not in {"python", "frontend", "image"}:
            raise ValueError("Unknown ecosystem")
        if not all((self.id, self.package, self.version)) or self.severity not in SEVERITIES:
            raise ValueError("Incomplete vulnerability finding")


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or "error" in value:
        raise ValueError("Invalid scanner report")
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Missing scanner inventory")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing report field")
    return value


def parse_python(report: Any) -> list[Finding]:
    findings = []
    for dependency in _list(_object(report).get("dependencies")):
        item = _object(dependency)
        name, version = _text(item.get("name")), _text(item.get("version"))
        if item.get("skip_reason"):
            raise ValueError("An unaudited Python dependency blocks the gate")
        for vulnerability in _list(item.get("vulns")):
            vuln = _object(vulnerability)
            findings.append(Finding("python", _text(vuln.get("id")), name, version, "UNKNOWN"))
    return findings


def parse_frontend(report: Any) -> list[Finding]:
    source = _object(report)
    advisories = _object(source.get("advisories"))
    counts = _object(_object(source.get("metadata")).get("vulnerabilities"))
    if not counts or any(type(count) is not int or count < 0 for count in counts.values()):
        raise ValueError("Invalid frontend vulnerability counts")
    if bool(sum(counts.values())) != bool(advisories):
        raise ValueError("Inconsistent frontend report")
    findings = []
    for advisory in advisories.values():
        item = _object(advisory)
        severity = _text(item.get("severity")).upper().replace("MODERATE", "MEDIUM")
        for affected in _list(item.get("findings")):
            findings.append(
                Finding(
                    "frontend",
                    _text(item.get("github_advisory_id")),
                    _text(item.get("module_name")),
                    _text(_object(affected).get("version")),
                    severity,
                )
            )
    if advisories and not findings:
        raise ValueError("Advisories without affected packages")
    return findings


def parse_trivy(report: Any) -> list[Finding]:
    source = _object(report)
    if source.get("SchemaVersion") != 2:
        raise ValueError("Unsupported Trivy report")
    _text(source.get("ArtifactName"))
    findings = []
    for result in _list(source.get("Results")):
        item = _object(result)
        for vulnerability in _list(item.get("Vulnerabilities") or []):
            vuln = _object(vulnerability)
            findings.append(
                Finding(
                    "image",
                    _text(vuln.get("VulnerabilityID")),
                    _text(vuln.get("PkgName")),
                    _text(vuln.get("InstalledVersion")),
                    _text(vuln.get("Severity")),
                    vuln.get("FixedVersion") or "",
                    _text(item.get("Target")),
                )
            )
    return findings


def evaluate_findings(
    findings: list[Finding],
    policy: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    accepted: set[tuple[str, str, str, str]] = set()
    for raw in _list(_object(policy).get("exceptions")):
        exception = _object(raw)
        for field in ("ecosystem", "id", "package", "version", "approvedBy", "reason", "evidence"):
            _text(exception.get(field))
        approved = date.fromisoformat(_text(exception.get("approvedAt")))
        expires = date.fromisoformat(_text(exception.get("expiresAt")))
        if expires < approved or (expires - approved).days > 30:
            raise ValueError("Exceptions must expire within 30 days")
        if approved <= now.date() <= expires:
            accepted.add(tuple(exception[key] for key in ("ecosystem", "id", "package", "version")))
    blocking: list[dict[str, Any]] = []
    reported: list[dict[str, Any]] = []
    exempted: list[dict[str, Any]] = []
    for finding in findings:
        key = (finding.ecosystem, finding.id, finding.package, finding.version)
        blocked = (
            finding.severity == "CRITICAL"
            or finding.ecosystem == "python"
            or (
                finding.severity == "HIGH"
                and (finding.ecosystem == "frontend" or bool(finding.fixed_version))
            )
        )
        destination = exempted if key in accepted else blocking if blocked else reported
        destination.append(asdict(finding))
    return {
        "passed": not blocking,
        "blocking": blocking,
        "reported": reported,
        "accepted": exempted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ecosystem", choices=("python", "frontend", "image"), required=True)
    parser.add_argument("--policy", type=Path, default=Path("config/security-policy.json"))
    args = parser.parse_args()
    adapters = {"python": parse_python, "frontend": parse_frontend, "image": parse_trivy}
    try:
        findings = adapters[args.ecosystem](json.loads(args.report.read_text(encoding="utf-8")))
        result = evaluate_findings(
            findings,
            json.loads(args.policy.read_text(encoding="utf-8")),
            datetime.now(UTC),
        )
    except (ValueError, OSError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
