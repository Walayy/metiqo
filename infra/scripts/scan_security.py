"""Run every MVP security scanner afresh; missing evidence never becomes a pass."""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from infra.scripts.install_security_tools import install_tool
from infra.scripts.scan_secrets import run_scan
from infra.scripts.security_policy import (
    Finding,
    evaluate_findings,
    parse_frontend,
    parse_python,
    parse_trivy,
)

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], *, allowed: tuple[int, ...] = (0,), timeout: int = 600) -> str:
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(f"Scanner executable missing: {command[0]}")
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode not in allowed:
        # Commands never contain credentials; remote responses might, so do not echo them.
        raise RuntimeError(
            f"Scanner command failed: {command[0]} {command[1]} ({result.returncode})"
        )
    return result.stdout


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    paths = run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    for name in sorted(set(paths.split("\0")) - {""}):
        path = ROOT / name
        digest.update(name.encode())
        if path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_database(version: dict[str, Any], now: datetime) -> None:
    if version.get("Version") != "0.74.0":
        raise ValueError("Unexpected Trivy version")
    updated = datetime.fromisoformat(version["VulnerabilityDB"]["UpdatedAt"].replace("Z", "+00:00"))
    if not timedelta(0) <= now - updated <= timedelta(hours=48):
        raise ValueError("Trivy database is stale or dated in the future")


def validate_exceptions(policy: dict[str, Any]) -> None:
    for exception in policy["exceptions"]:
        evidence = (ROOT / exception["evidence"]).resolve()
        if not evidence.is_relative_to(ROOT / "docs") or not evidence.is_file():
            raise ValueError("Exception evidence must be an existing repository document")
        if not evidence.read_text(encoding="utf-8").strip():
            raise ValueError("Exception evidence is empty")


def scan(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    fingerprint = source_fingerprint()
    policy = json.loads((ROOT / "config/security-policy.json").read_text(encoding="utf-8"))
    evaluate_findings([], policy, started)
    validate_exceptions(policy)
    gitleaks, trivy = str(install_tool("gitleaks")), str(install_tool("trivy"))
    findings: list[Finding] = []
    secrets = run_scan(gitleaks, output)
    print("Secret scan complete", flush=True)
    requirements = output / "python-requirements.txt"
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--output-file",
            str(requirements),
        ]
    )
    python_report = output / "python.json"
    run(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-m",
            "pip_audit",
            "--require-hashes",
            "--no-deps",
            "--disable-pip",
            "--strict",
            "-r",
            str(requirements),
            "--format",
            "json",
            "--output",
            str(python_report),
            "--progress-spinner",
            "off",
        ],
        allowed=(0, 1),
    )
    python_data = json.loads(python_report.read_text(encoding="utf-8"))
    findings.extend(parse_python(python_data))
    if not python_data["dependencies"]:
        raise ValueError("Empty Python dependency inventory")
    frontend_report = run(["pnpm", "audit", "--json"], allowed=(0, 1))
    (output / "frontend.json").write_text(frontend_report, encoding="utf-8")
    findings.extend(parse_frontend(json.loads(frontend_report)))
    print("Python and frontend audits complete", flush=True)
    compose = json.loads(
        run(["docker", "compose", "--profile", "production", "config", "--format", "json"])
    )
    images = {}
    for service in ("api", "worker", "web", "postgres", "gateway"):
        name = compose["services"][service]["image"]
        image_id = run(["docker", "image", "inspect", name, "--format", "{{.Id}}"]).strip()
        report_path = output / f"image-{service}.json"
        run(
            [
                trivy,
                "image",
                "--quiet",
                "--scanners",
                "vuln",
                "--list-all-pkgs",
                "--image-src",
                "docker",
                "--format",
                "json",
                "--output",
                str(report_path),
                "--timeout",
                "5m",
                name,
            ]
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report["Metadata"]["ImageID"] != image_id or not report.get("Results"):
            raise ValueError("Image inventory missing or scanned identity changed")
        if report["Metadata"].get("OS", {}).get("EOSL"):
            raise ValueError("Unsupported image operating system")
        if run(["docker", "image", "inspect", name, "--format", "{{.Id}}"]).strip() != image_id:
            raise ValueError("Image changed during scan")
        findings.extend(parse_trivy(report))
        images[service] = {"name": name, "id": image_id}
        print(f"Image audit complete: {service}", flush=True)
    trivy_version = json.loads(run([trivy, "--version", "--format", "json"]))
    validate_database(trivy_version, datetime.now(UTC))
    if source_fingerprint() != fingerprint:
        raise ValueError("Sources changed during security gate; run it again")
    result = evaluate_findings(findings, policy, datetime.now(UTC))
    return {
        **result,
        "passed": result["passed"] and secrets["passed"],
        "startedAt": started.isoformat(),
        "completedAt": datetime.now(UTC).isoformat(),
        "commit": run(["git", "rev-parse", "HEAD"]).strip(),
        "sourceSha256": fingerprint,
        "images": images,
        "secretScan": secrets,
        "trivy": trivy_version,
        "pipAudit": run(
            ["uv", "run", "--frozen", "python", "-m", "pip_audit", "--version"]
        ).strip(),
        "pnpm": run(["pnpm", "--version"]).strip(),
        "reports": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob("*.json")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/security")
    args = parser.parse_args()
    output = args.output_root.resolve() / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    )
    try:
        result = scan(output)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        result = {
            "passed": False,
            "error": str(error),
            "completedAt": datetime.now(UTC).isoformat(),
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "report": str(output / "summary.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
