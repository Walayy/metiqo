"""Benchmark real read routes with synthetic data in a newly created disposable database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import Engine, Table, create_engine, event, func, insert, select, text
from tests.integration.test_canonical_series import _seed_series
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_postgres_canonical_api import _ReadyProbe, _settings
from tests.integration.test_value_pipeline import _Context, context

from infra.scripts.scan_security import source_fingerprint
from metiquo.api.app import create_app
from metiquo.canonical.series import CanonicalSeriesBuilder
from metiquo.db.core_models import Series
from metiquo.db.ml_models import ModelVersion
from metiquo.db.odds_models import OddsProviderRecord
from metiquo.db.ops_models import JobRecord
from metiquo.db.paper_models import PaperBetRecord
from metiquo.db.pricing_models import SignalRecord
from metiquo.db.raw_models import IngestionRun, QualityIssue, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.worker.queue import PostgresJobQueue

ROOT = Path(__file__).resolve().parents[2]
ROUTES = (
    "/api/v1/events?limit=20",
    "/api/v1/opportunities?limit=20",
    "/api/v1/models?limit=20",
    "/api/v1/backtests?limit=20",
    "/api/v1/paper-bets?limit=20",
    "/api/v1/paper-bets/metrics",
    "/api/v1/admin/data-sources?limit=20",
    "/api/v1/admin/ingestion-runs?limit=20",
    "/api/v1/admin/quality-issues?limit=20",
    "/api/v1/admin/jobs?limit=20",
    "/api/v1/admin/audit-log?limit=20",
    "/api/v1/system/status",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_load(fixture: _Context, size: int, clock: FixedClock) -> dict[str, int]:
    engine = fixture.engine
    # Financial rows use the same validated synthetic fixture as the ledger tests.
    for _ in range(min(size, 100)):
        values = bet_values(fixture)
        values["idempotency_fingerprint"] = _digest(str(values["id"]))
        with engine.begin() as connection:
            connection.execute(insert(PaperBetRecord).values(**values))
    _seed_series(engine, "league_of_legends_match_data")
    CanonicalSeriesBuilder(engine=engine, clock=clock).build()
    job = PostgresJobQueue(engine, clock=clock).enqueue(
        "paper.report",
        {"currency": "EUR"},
        key="read-benchmark",
        scope="paper:EUR",
        actor="synthetic-benchmark",
    )
    with engine.begin() as connection:
        series = dict(connection.execute(select(Series.__table__)).mappings().first() or {})
        model = dict(connection.execute(select(ModelVersion.__table__)).mappings().first() or {})
        signal = dict(connection.execute(select(SignalRecord.__table__)).mappings().first() or {})
        run = dict(
            connection.execute(
                select(IngestionRun.__table__)
                .join(SourceCatalog, SourceCatalog.id == IngestionRun.source_catalog_id)
                .where(SourceCatalog.dataset == "league_of_legends_match_data")
            )
            .mappings()
            .first()
            or {}
        )
        queued = dict(
            connection.execute(select(JobRecord.__table__).where(JobRecord.id == job.job_id))
            .mappings()
            .one()
        )
        connection.execute(
            insert(Series),
            [
                dict(series, id=uuid4(), source_series_id=f"PERF-{i}", series_key=f"PERF-{i}")
                for i in range(size)
            ],
        )
        # Capacity clones retain FK references; they are never model/financial validation.
        connection.execute(
            insert(ModelVersion),
            [
                dict(
                    model,
                    id=uuid4(),
                    status="candidate",
                    training_cutoff_min=model["training_cutoff_min"] - timedelta(days=1),
                    registration_fingerprint=_digest(f"model-{i}"),
                    evaluation_report_fingerprint=_digest(f"report-{i}"),
                )
                for i in range(size)
            ],
        )
        connection.execute(
            insert(SignalRecord),
            [
                dict(signal, id=uuid4(), signal_fingerprint=_digest(f"signal-{i}"))
                for i in range(size)
            ],
        )
        connection.execute(
            insert(IngestionRun),
            [dict(run, id=uuid4(), request_key_hash=None) for _ in range(size)],
        )
        connection.execute(
            insert(QualityIssue),
            [
                dict(
                    id=uuid4(),
                    run_id=run["id"],
                    snapshot_id=run["snapshot_id"],
                    code="SYNTHETIC_LOAD",
                    severity="warning",
                    message="Capacity fixture",
                    created_at=clock.now().value,
                )
                for _ in range(size)
            ],
        )
        connection.execute(
            insert(JobRecord),
            [
                dict(
                    queued,
                    id=uuid4(),
                    idempotency_fingerprint=_digest(f"job-{i}"),
                    request_fingerprint=_digest(f"job-request-{i}"),
                )
                for i in range(size)
            ],
        )
        connection.execute(
            insert(OddsProviderRecord),
            [
                dict(
                    id=uuid4(),
                    code=f"performance-{i}",
                    display_name="Synthetic capacity",
                    provider_type="manual_import",
                    enabled=False,
                    created_at=clock.now().value,
                )
                for i in range(50)
            ],
        )
    PostgresFinancialReportingService(engine, clock=clock).build(currency="EUR")
    with engine.begin() as connection:
        connection.execute(text("ANALYZE"))
        return {
            cast(Table, model.__table__).fullname: int(
                connection.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in (
                Series,
                ModelVersion,
                SignalRecord,
                IngestionRun,
                QualityIssue,
                JobRecord,
                PaperBetRecord,
                OddsProviderRecord,
            )
        }


async def _measure(
    engine: Engine, url: str, samples: int, clock: FixedClock
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    settings = _settings(url, "real", year=2194)
    app = create_app(
        settings=settings,
        clock=clock,
        readiness_probe=_ReadyProbe(),
        real_admin_repository=PostgresAdminRepository(engine, clock, oe_current_year=2194),
    )
    queries: list[str] = []
    statements: dict[str, object] = {}

    def record(*arguments: object) -> None:
        statement = str(arguments[2])
        queries.append(statement)
        if (
            statement.lstrip().upper().startswith(("SELECT", "WITH"))
            and "set_config" not in statement
        ):
            statements.setdefault(statement, arguments[3])

    event.listen(engine, "before_cursor_execute", record)
    results = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for route in ROUTES:
                durations, counts, statuses = [], [], []
                for iteration in range(samples + 5):
                    queries.clear()
                    started = time.perf_counter()
                    response = await client.get(route)
                    elapsed = (time.perf_counter() - started) * 1000
                    if iteration >= 5:
                        durations.append(round(elapsed, 3))
                        counts.append(len(queries))
                        statuses.append(response.status_code)
                ordered = sorted(durations)
                results.append(
                    {
                        "route": route,
                        "samples": samples,
                        "p50Ms": ordered[math.ceil(samples * 0.5) - 1],
                        "p95Ms": ordered[math.ceil(samples * 0.95) - 1],
                        "maxMs": max(ordered),
                        "queryCounts": sorted(set(counts)),
                        "statuses": sorted(set(statuses)),
                        "durationsMs": durations,
                    }
                )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    plans = []
    with engine.connect() as connection:
        for statement, parameters in statements.items():
            plan = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, cast(Any, parameters)
            ).scalar_one()
            plans.append({"sql": statement, "plan": plan})
    return results, plans


def benchmark(url: str, *, samples: int, size: int, output: Path) -> bool:
    started = datetime.now(UTC)
    source_hash = source_fingerprint()
    database = "metiquo_perf_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    target_url = admin.url.set(database=database).render_as_string(hide_password=False)
    output.mkdir(parents=True, exist_ok=False)
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
    fixture: _Context | None = None
    try:
        with (
            tempfile.TemporaryDirectory(prefix="metiquo-perf-") as folder,
            pytest.MonkeyPatch.context() as patches,
        ):
            generator = cast(
                Generator[_Context],
                cast(Any, context).__wrapped__(
                    target_url, Path(folder), patches, SimpleNamespace(param=False)
                ),
            )
            fixture = next(generator)
            try:
                clock = FixedClock(UtcInstant(datetime(2026, 9, 6, 9, tzinfo=UTC)))
                sizes = _seed_load(fixture, size, clock)
                results, plans = asyncio.run(_measure(fixture.engine, target_url, samples, clock))
                (output / "plans.json").write_text(
                    json.dumps(plans, indent=2, default=str) + "\n", encoding="utf-8"
                )
                passed = all(
                    item["statuses"] == [200] and cast(float, item["p95Ms"]) < 300
                    for item in results
                )
                with fixture.engine.connect() as connection:
                    postgres = connection.scalar(text("SELECT version()"))
                report = {
                    "passed": passed,
                    "startedAt": started.isoformat(),
                    "completedAt": datetime.now(UTC).isoformat(),
                    "commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "sourceSha256": source_hash,
                    "sourceUnchanged": source_fingerprint() == source_hash,
                    "fixtureOnly": True,
                    "transport": "in-process ASGI with real PostgreSQL; no external network",
                    "warmupRequests": 5,
                    "quantile": "nearest rank",
                    "platform": platform.platform(),
                    "cpu": platform.processor(),
                    "python": platform.python_version(),
                    "postgres": postgres,
                    "versions": {
                        package: version(package)
                        for package in ("fastapi", "sqlalchemy", "psycopg", "httpx2")
                    },
                    "rowCounts": sizes,
                    "results": results,
                }
                report["passed"] = passed and report["sourceUnchanged"]
                (output / "report.json").write_text(
                    json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
                )
                return bool(report["passed"])
            finally:
                generator.close()
    finally:
        if fixture is not None:
            fixture.engine.dispose()
        if not database.startswith("metiquo_perf_") or len(database) != 45:
            raise RuntimeError("Unexpected benchmark database identity")
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database}" WITH (FORCE)')
        admin.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL"))
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "data/performance"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]),
    )
    args = parser.parse_args()
    if not args.database_url or not 5 <= args.samples <= 1000 or not 50 <= args.size <= 10000:
        parser.error("TEST_DATABASE_URL et samples [5,1000], size [50,10000] requis")
    passed = benchmark(args.database_url, samples=args.samples, size=args.size, output=args.output)
    print(json.dumps({"passed": passed, "report": str(args.output / "report.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
