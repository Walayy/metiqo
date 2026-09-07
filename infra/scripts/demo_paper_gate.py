"""Exécuter la fixture complète P7 dans une base créée vide puis supprimée."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("TEST_DATABASE_URL ou --database-url est requis")
    parsed = make_url(args.database_url)
    if not parsed.drivername.startswith("postgresql"):
        parser.error("PostgreSQL est requis")
    name = f"metiquo_paper_gate_{uuid4().hex}"
    admin = create_engine(parsed, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        with tempfile.TemporaryDirectory(prefix="metiquo-paper-gate-") as directory:
            report_path = Path(directory) / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/integration/test_real_paper_api.py",
                    "-q",
                    "--tb=short",
                    "--show-capture=no",
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "TEST_DATABASE_URL": parsed.set(database=name).render_as_string(
                        hide_password=False
                    ),
                    "PAPER_GATE_REPORT_PATH": str(report_path),
                    "PYTHONIOENCODING": "utf-8",
                },
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                print(result.stdout + result.stderr, file=sys.stderr)
                return result.returncode
            document = json.loads(report_path.read_text(encoding="utf-8"))
            if (
                document.get("fixture") is not True
                or document.get("financialPerformanceValidated") is not False
            ):
                raise RuntimeError("Classification de la preuve financière absente")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            summary = {
                "gate": "P7",
                "ok": True,
                "database": "ephemeral",
                "fixture": True,
                "financialPerformanceValidated": False,
                "reportId": document["reportId"],
                "output": str(args.output.resolve()),
            }
    finally:
        if re.fullmatch(r"metiquo_paper_gate_[0-9a-f]{32}", name) is None:
            raise RuntimeError("Suppression refusée : nom de base temporaire invalide")
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
