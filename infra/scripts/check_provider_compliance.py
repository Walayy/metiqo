"""Recherche statique bloquante des mécanismes de contournement interdits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOTS = ("python", "services", "apps", "packages", "infra/compose", "infra/gateway")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".yaml", ".yml"}
SOURCE_NAMES = {"Dockerfile", "Caddyfile"}
IGNORED_PARTS = {".git", ".next", ".venv", "__pycache__", "generated", "node_modules"}

FORBIDDEN_PATTERNS = {
    "endpoint Stake": re.compile(r"https?://[^\s\"']*stake\.com", re.IGNORECASE),
    "solveur CAPTCHA": re.compile(
        r"(?:2captcha|anti-?captcha|capsolver|captcha[_-]?(?:solver|bypass))",
        re.IGNORECASE,
    ),
    "proxy résidentiel": re.compile(r"residential[_ -]?prox(?:y|ies)", re.IGNORECASE),
    "contournement géographique": re.compile(r"geo[_ -]?(?:bypass|spoof)", re.IGNORECASE),
    "cookie navigateur": re.compile(r"(?:browser_cookie3|bookmaker[_ -]?cookie)", re.IGNORECASE),
    "navigateur furtif": re.compile(
        r"(?:undetected[_-]?chromedriver|cloudscraper|puppeteer-extra-plugin-stealth)",
        re.IGNORECASE,
    ),
    "automatisation de mise": re.compile(
        r"(?:place|submit|execute)[_-]?(?:bet|wager)", re.IGNORECASE
    ),
}


@dataclass(frozen=True, slots=True)
class ComplianceViolation:
    """Occurrence interdite localisée dans une source de production."""

    path: Path
    line: int
    rule: str


def _source_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative_root in SOURCE_ROOTS:
        source_root = root / relative_root
        if not source_root.exists():
            continue
        files.extend(
            path
            for path in source_root.rglob("*")
            if path.is_file()
            and (path.suffix in SOURCE_SUFFIXES or path.name in SOURCE_NAMES)
            and not IGNORED_PARTS.intersection(path.parts)
        )
    return tuple(sorted(files))


def scan_provider_compliance(root: Path) -> tuple[ComplianceViolation, ...]:
    """Scanner les sources exécutables, à l'exclusion du scanner lui-même."""

    scanner_path = Path(__file__).resolve()
    violations: list[ComplianceViolation] = []
    for path in _source_files(root.resolve()):
        if path.resolve() == scanner_path:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for rule, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(line):
                    violations.append(ComplianceViolation(path, line_number, rule))
    return tuple(violations)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    violations = scan_provider_compliance(repository_root())
    for violation in violations:
        relative = violation.path.relative_to(repository_root())
        print(f"FORBIDDEN {relative}:{violation.line}: {violation.rule}")
    if violations:
        return 1
    print("Provider compliance scan: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
