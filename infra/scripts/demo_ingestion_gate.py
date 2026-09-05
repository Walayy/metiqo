"""Démontrer le gate P2 Oracle's Elixir dans une base PostgreSQL éphémère."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "oracles_elixir"
YEAR = 2026


class GateFailure(RuntimeError):
    """Le parcours de démonstration ne respecte pas une garantie P2."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("TEST_DATABASE_URL"),
        help="URL d'une instance PostgreSQL autorisant la création d'une base temporaire",
    )
    parser.add_argument("--json", action="store_true", help="Émettre le rapport JSON compact")
    return parser


def _alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _temporary_database(base_url: str) -> tuple[Engine, str, str]:
    parsed = make_url(base_url)
    if not parsed.drivername.startswith("postgresql") or parsed.database is None:
        raise GateFailure("--database-url doit cibler une base PostgreSQL existante")
    database_name = f"metiquo_gate_{uuid4().hex}"
    admin = create_engine(parsed, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    target = parsed.set(database=database_name)
    return admin, database_name, target.render_as_string(hide_password=False)


def _drop_temporary_database(admin: Engine, database_name: str) -> None:
    if not database_name.startswith("metiquo_gate_") or len(database_name) != 45:
        raise GateFailure("nom de base temporaire inattendu ; suppression refusée")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


def _run_oe(
    environment: dict[str, str],
    arguments: Sequence[str],
    *,
    expected_code: int = 0,
) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "metiquo.cli", *arguments, "--json"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    payload = result.stdout if result.returncode == 0 else result.stderr
    try:
        document = cast(dict[str, object], json.loads(payload))
    except json.JSONDecodeError as error:
        raise GateFailure(f"sortie oe non JSON pour {' '.join(arguments)}") from error
    if result.returncode != expected_code:
        raise GateFailure(
            f"{' '.join(arguments)} retourne {result.returncode}, attendu {expected_code}: "
            f"{document.get('errorCode', 'UNKNOWN')}"
        )
    return document


def _write_variants(directory: Path) -> tuple[Path, Path, Path]:
    source = FIXTURES / "dq_valid.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or ())
        rows = list(reader)
    if not fieldnames or not rows:
        raise GateFailure("fixture valide vide")

    additive = directory / "additive.csv"
    additive_fields = [*fieldnames, "vendor_metric"]
    with additive.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=additive_fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "vendor_metric": "synthetic"})

    retroactive = directory / "retroactive.csv"
    rows[0]["kills"] = "99"
    with retroactive.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=additive_fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "vendor_metric": "synthetic"})

    missing_core = directory / "missing-core.csv"
    retained_fields = [field for field in fieldnames if field != "gameid"]
    with missing_core.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=retained_fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in retained_fields})
    return additive, retroactive, missing_core


def _canonical_state(engine: Engine) -> tuple[int, str]:
    with engine.connect() as connection:
        rows = [
            (str(row.natural_key), str(row.row_hash), int(row.revision))
            for row in connection.execute(
                text(
                    "SELECT natural_key, row_hash, revision FROM raw.canonical_rows "
                    "ORDER BY natural_key"
                )
            )
        ]
    digest = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return len(rows), digest


def _current_snapshot(engine: Engine) -> UUID:
    with engine.connect() as connection:
        value = connection.execute(
            text(
                "SELECT current_snapshot_id FROM raw.source_catalog "
                "WHERE provider = 'oracles_elixir' AND season_year = :year"
            ),
            {"year": YEAR},
        ).scalar_one()
    return cast(UUID, value)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def _run_gate(database_url: str, object_store_root: Path) -> dict[str, object]:
    command.upgrade(_alembic_config(database_url), "head")
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "APP_DATA_MODE": "mock",
        "DATABASE_URL": database_url,
        "OBJECT_STORE_ROOT": str(object_store_root),
        "ODDS_PROVIDER": "mock",
        "OE_ALLOW_STALE": "false",
        "OE_REQUIRE_FRESH": "false",
        "OE_CURRENT_YEAR": str(YEAR),
        "OE_SOURCE_CATALOG_PATH": str(ROOT / "config" / "oracles_elixir_sources.yml"),
        "PYTHONIOENCODING": "utf-8",
    }
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        catalog = _run_oe(environment, ("catalog", "refresh"))
        backfill = _run_oe(
            environment,
            (
                "backfill",
                "--from-year",
                str(YEAR),
                "--to-year",
                str(YEAR),
                "--fixture",
                str(FIXTURES / "dq_valid.csv"),
            ),
        )
        initial_snapshot = _current_snapshot(engine)

        first = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--require-fresh",
                "--fixture",
                str(FIXTURES / "dq_valid.csv"),
            ),
        )
        first_count, first_state = _canonical_state(engine)
        second = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--require-fresh",
                "--fixture",
                str(FIXTURES / "dq_valid.csv"),
            ),
        )
        second_count, second_state = _canonical_state(engine)
        _require(first_count == second_count == 12, "le double run doit conserver 12 lignes")
        _require(first_state == second_state, "le double run doit conserver l'état canonique")
        _require(first["snapshotId"] == second["snapshotId"], "le snapshot doit être réutilisé")

        quota_hash = hashlib.sha256((FIXTURES / "quota.html").read_bytes()).hexdigest()
        quota = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--allow-stale",
                "--fixture",
                str(FIXTURES / "quota.html"),
            ),
        )
        quota_freshness = cast(dict[str, object], quota["freshness"])
        with engine.connect() as connection:
            quota_snapshot_count = int(
                connection.execute(
                    text("SELECT count(*) FROM raw.snapshots WHERE sha256 = :sha256"),
                    {"sha256": quota_hash},
                ).scalar_one()
            )
        _require(quota_snapshot_count == 0, "la page quota a atteint raw.snapshots")
        _require(
            quota_freshness["status"] == "degraded",
            "allow-stale doit annoncer degraded après la page quota",
        )
        _require(
            quota_freshness["snapshotId"] == str(initial_snapshot),
            "allow-stale doit réutiliser le dernier snapshot validé",
        )

        additive_path, retroactive_path, missing_core_path = _write_variants(object_store_root)
        invalid_hash = hashlib.sha256(missing_core_path.read_bytes()).hexdigest()
        quarantined = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--allow-stale",
                "--fixture",
                str(missing_core_path),
            ),
        )
        quarantine_freshness = cast(dict[str, object], quarantined["freshness"])
        _require(
            quarantine_freshness["status"] == "quarantined",
            "un hash invalide reçu doit rester quarantined",
        )
        _require(
            _current_snapshot(engine) == initial_snapshot,
            "la quarantaine a remplacé le snapshot courant",
        )
        with engine.connect() as connection:
            quarantine_row = (
                connection.execute(
                    text(
                        "SELECT s.id, s.status, q.reason_code FROM raw.snapshots AS s "
                        "JOIN raw.quarantine_items AS q ON q.snapshot_id = s.id "
                        "WHERE s.sha256 = :sha256"
                    ),
                    {"sha256": invalid_hash},
                )
                .mappings()
                .one()
            )
        _require(quarantine_row["status"] == "quarantined", "snapshot invalide non isolé")
        _require(
            quarantine_row["reason_code"] == "SCHEMA_INCOMPATIBLE",
            "la colonne cœur manquante doit produire SCHEMA_INCOMPATIBLE",
        )

        require_fresh = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--require-fresh",
                "--fixture",
                str(missing_core_path),
            ),
            expected_code=3,
        )
        _require(
            require_fresh["errorCode"] == "FRESH_DATA_REQUIRED",
            "require-fresh doit exposer son échec structuré",
        )

        additive = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--require-fresh",
                "--fixture",
                str(additive_path),
            ),
        )
        additive_freshness = cast(dict[str, object], additive["freshness"])
        _require(additive_freshness["status"] == "fresh", "la colonne additive doit passer")

        retroactive = _run_oe(
            environment,
            (
                "sync",
                "--year",
                str(YEAR),
                "--require-fresh",
                "--fixture",
                str(retroactive_path),
            ),
        )
        retro_load = cast(dict[str, object], retroactive["load"])
        _require(retro_load["updated"] == 1, "la correction rétroactive doit modifier une ligne")
        retro_load_run_id = str(retroactive["loadRunId"])
        with engine.connect() as connection:
            invalidation = (
                connection.execute(
                    text(
                        "SELECT affected_from, revision_count FROM features.invalidations "
                        "WHERE source_run_id = :run_id"
                    ),
                    {"run_id": UUID(retro_load_run_id)},
                )
                .mappings()
                .one()
            )
            migration_revision = str(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            )
        _require(invalidation["revision_count"] == 1, "invalidation rétroactive absente")

        final_snapshot = str(retroactive["snapshotId"])
        verification = _run_oe(environment, ("verify", "--snapshot", final_snapshot))
        return {
            "ok": True,
            "command": "ingestion-gate",
            "database": "ephemeral",
            "migrationRevision": migration_revision,
            "catalogOrigin": catalog["origin"],
            "backfillStatus": backfill["status"],
            "idempotence": {
                "rowCount": second_count,
                "canonicalStateSha256": second_state,
                "snapshotId": second["snapshotId"],
                "secondRunUnchanged": cast(dict[str, object], second["load"])["unchanged"],
            },
            "quota": {
                "ingestedSnapshotCount": quota_snapshot_count,
                "freshness": quota_freshness["status"],
                "reusedSnapshotId": quota_freshness["snapshotId"],
            },
            "quarantine": {
                "snapshotId": str(quarantine_row["id"]),
                "reasonCode": quarantine_row["reason_code"],
                "currentSnapshotId": str(initial_snapshot),
            },
            "requireFresh": {"exitCode": 3, "errorCode": require_fresh["errorCode"]},
            "additiveSchema": {"freshness": additive_freshness["status"]},
            "retroactiveChange": {
                "updated": retro_load["updated"],
                "affectedFrom": invalidation["affected_from"].isoformat(),
                "revisionCount": invalidation["revision_count"],
            },
            "manifestVerification": {
                "snapshotId": verification["snapshotId"],
                "sha256": verification["sha256"],
                "byteSize": verification["byteSize"],
            },
        }
    finally:
        engine.dispose()


def main() -> int:
    arguments = _parser().parse_args()
    database_url = cast(str | None, arguments.database_url)
    if not database_url:
        print("TEST_DATABASE_URL ou --database-url est requis", file=sys.stderr)
        return 2
    admin: Engine | None = None
    database_name: str | None = None
    try:
        admin, database_name, temporary_url = _temporary_database(database_url)
        with tempfile.TemporaryDirectory(prefix="metiquo-ingestion-gate-") as directory:
            report = _run_gate(temporary_url, Path(directory))
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "errorCode": type(error).__name__.upper(), "message": str(error)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if admin is not None and database_name is not None:
            _drop_temporary_database(admin, database_name)
            admin.dispose()
    if cast(bool, arguments.json):
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
