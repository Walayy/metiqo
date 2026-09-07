"""Scanner les sources présentes et tout l'historique local sans afficher de secret."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "8.30.1"


def run_scan(binary: str, output: Path, *, history: bool = True) -> dict[str, object]:
    version = subprocess.run([binary, "version"], capture_output=True, text=True, check=True)
    if version.stdout.strip() != VERSION:
        raise RuntimeError(f"Gitleaks {VERSION} requis")
    output.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    names = sorted(set(name for name in listing.stdout.decode().split("\0") if name))
    forbidden = [
        name
        for name in names
        if ".secrets" in Path(name).parts
        or (Path(name).name.startswith(".env") and Path(name).name != ".env.example")
    ]
    if forbidden:
        raise RuntimeError("Fichier privé présent dans les sources suivies")
    reports: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="metiquo-secret-scan-") as temporary:
        snapshot = Path(temporary)
        for name in names:
            source = ROOT / name
            if not source.exists():
                continue
            if not source.resolve().is_relative_to(ROOT.resolve()) or source.is_symlink():
                raise RuntimeError("Lien externe refusé dans le snapshot de scan")
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        modes = [("working", ["dir", str(snapshot)])]
        if history:
            modes.append(("history", ["git", "--log-opts=--all", str(ROOT)]))
        for name, arguments in modes:
            report = output / f"gitleaks-{name}.json"
            result = subprocess.run(
                [
                    binary,
                    *arguments,
                    "--redact",
                    "--no-banner",
                    "--no-color",
                    "--timeout",
                    "180",
                    "--ignore-gitleaks-allow",
                    "--config",
                    str(ROOT / ".gitleaks.toml"),
                    "--report-format",
                    "json",
                    "--report-path",
                    str(report),
                ],
                cwd=ROOT,
                capture_output=True,
                timeout=190,
            )
            if result.returncode not in {0, 1} or not report.is_file():
                raise RuntimeError("Exécution Gitleaks indisponible ; gate refusé")
            findings = json.loads(report.read_text(encoding="utf-8"))
            if not isinstance(findings, list):
                raise RuntimeError("Rapport Gitleaks invalide")
            if bool(findings) != (result.returncode == 1):
                raise RuntimeError("Rapport et statut Gitleaks incohérents ; gate refusé")
            reports[name] = len(findings)
    summary: dict[str, object] = {
        "scanner": "gitleaks",
        "version": VERSION,
        "sourceFiles": len(names),
        "findings": reports,
        "passed": all(count == 0 for count in reports.values()),
    }
    (output / "secret-scan-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=os.environ.get("GITLEAKS_BINARY", "gitleaks"))
    parser.add_argument("--output", type=Path, default=ROOT / "data/security")
    parser.add_argument("--working-only", action="store_true")
    args = parser.parse_args()
    summary = run_scan(args.binary, args.output.resolve(), history=not args.working_only)
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
