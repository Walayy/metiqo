"""Panne PostgreSQL transitoire réelle et reprise sans altérer la provenance."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, insert, select, text

from metiquo.api.app import create_app
from metiquo.config import AuthMode, OddsProvider
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import IngestionRun, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.freshness import FreshDataRequired, FreshnessPolicy
from metiquo.ingestion.google_drive_public import GoogleDrivePublicHttpTransport, PublicHttpStream
from metiquo.ingestion.operations import verify_snapshot
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.ingestion.transport import TransportPolicy
from tests.integration.test_real_admin_api import (
    NOW,
    ReadyProbe,
    _alembic_config,
    _seed_real_health,
    _settings,
)


@pytest.mark.integration
def test_postgres_statement_timeout_returns_safe_retryable_problem_and_keeps_snapshot(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    _seed_real_health(postgresql_url, "qa004-transient-read")
    app = create_app(
        settings=_settings(postgresql_url, "real"),
        readiness_probe=ReadyProbe(),
        clock=FixedClock(UtcInstant(NOW)),
    )
    engine = app.state.real_admin_engine
    armed = False
    triggered = False

    def interrupt_read(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> tuple[str, Any]:
        nonlocal triggered
        if armed and not triggered and "source_catalog" in statement:
            triggered = True
            cursor.execute("SET LOCAL statement_timeout = '1ms'")
            return "SELECT pg_sleep(0.05)", ()
        return statement, parameters

    event.listen(engine, "before_cursor_execute", interrupt_read, retval=True)

    async def exercise() -> None:
        nonlocal armed
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            before = await client.get("/api/v1/admin/data-sources")
            assert before.status_code == 200
            with engine.connect() as connection:
                snapshot = connection.scalar(select(SourceCatalog.current_snapshot_id))
            assert snapshot is not None
            armed = True
            failed = await client.get("/api/v1/admin/data-sources")
            assert triggered
            assert failed.status_code == 503
            assert failed.headers["content-type"].startswith("application/problem+json")
            assert failed.json()["code"] == "DEPENDENCY_UNAVAILABLE"
            assert failed.headers["x-trace-id"]
            assert "pg_sleep" not in failed.text and "psycopg" not in failed.text
            recovered = await client.get("/api/v1/admin/data-sources")
            assert recovered.status_code == 200
            assert recovered.json() == before.json()
            with engine.connect() as connection:
                assert connection.scalar(select(SourceCatalog.current_snapshot_id)) == snapshot

    try:
        asyncio.run(exercise())
    finally:
        event.remove(engine, "before_cursor_execute", interrupt_read)
        engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("mode", [AuthMode.DISABLED, AuthMode.OWNER])
def test_api_connections_bound_database_work_and_recover_a_dead_idle_connection(
    postgresql_url: str,
    mode: AuthMode,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    settings = _settings(postgresql_url, "real").model_copy(update={"auth_mode": mode})
    app = create_app(settings=settings, readiness_probe=ReadyProbe())
    engines = [app.state.real_admin_engine]
    if mode is AuthMode.OWNER:
        engines.append(app.state.owner_auth.engine)
    killer = create_engine(postgresql_url)
    try:
        for engine in engines:
            with engine.connect() as connection:
                assert connection.scalar(text("SHOW statement_timeout")) == "8s"
                assert connection.scalar(text("SHOW lock_timeout")) == "3s"
                process_id = connection.scalar(text("SELECT pg_backend_pid()"))
            with killer.connect() as connection:
                assert (
                    connection.scalar(
                        text("SELECT pg_terminate_backend(:pid)"), {"pid": process_id}
                    )
                    is True
                )
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT pg_backend_pid()")) != process_id
                assert connection.scalar(text("SELECT 1")) == 1
    finally:
        for engine in engines:
            engine.dispose()
        killer.dispose()


@pytest.mark.integration
def test_public_transport_timeout_keeps_real_validated_bytes_and_blocks_require_fresh(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    catalog_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(SourceCatalog).values(
                id=catalog_id,
                provider="oracles_elixir",
                dataset="league_of_legends_match_data",
                season_year=2026,
                drive_file_id="qa004-public-timeout",
                landing_page="https://oracleselixir.com/tools/downloads",
                source_name="2026.csv",
                origin="manual",
                status="active",
                discovered_at=NOW,
                mutable=True,
            )
        )
    settings = _settings(postgresql_url, "mock").model_copy(
        update={
            "oe_current_year": 2026,
            "object_store_root": tmp_path,
            "oe_retry_max_attempts": 2,
            "oe_retry_base_seconds": 0.001,
            "oe_retry_max_seconds": 0.001,
        }
    )
    clock = FixedClock(UtcInstant(NOW))
    initial = OracleElixirYearSync(engine=engine, settings=settings, clock=clock).sync_year(
        year=2026,
        policy=FreshnessPolicy(allow_stale=True),
        fixture_path=Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv",
    )
    assert initial.snapshot_id is not None
    before = verify_snapshot(engine, settings, initial.snapshot_id)
    clock = FixedClock(UtcInstant(NOW + timedelta(minutes=1)))
    real = settings.model_copy(
        update={"app_data_mode": DataMode.REAL, "odds_provider": OddsProvider.DISABLED}
    )
    calls = 0

    class TimedOutClient:
        def get(
            self,
            url: str,
            *,
            connect_timeout_seconds: float,
            read_timeout_seconds: float,
            max_redirects: int,
        ) -> PublicHttpStream:
            nonlocal calls
            calls += 1
            raise TimeoutError("injected public transport timeout")

    transport = GoogleDrivePublicHttpTransport(
        policy=TransportPolicy.from_settings(real),
        clock=clock,
        client=TimedOutClient(),
    )
    sync = OracleElixirYearSync(engine=engine, settings=real, clock=clock)
    # Isolate the remote timeout classification from mirror fallback selection.
    monkeypatch.setattr(sync, "_transports", lambda source, fixture_path: (transport,))
    try:
        result = sync.sync_year(year=2026, policy=FreshnessPolicy(allow_stale=True))
        assert calls == 2
        assert result.snapshot_id == initial.snapshot_id
        assert result.freshness.status.value == "degraded"
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(IngestionRun.error_code).where(IngestionRun.id == result.run_id)
                )
                == "SOURCE_TIMEOUT"
            )
            assert (
                connection.scalar(
                    select(SourceCatalog.current_snapshot_id).where(SourceCatalog.id == catalog_id)
                )
                == initial.snapshot_id
            )
        assert verify_snapshot(engine, real, initial.snapshot_id) == before
        with pytest.raises(FreshDataRequired):
            sync.sync_year(year=2026, policy=FreshnessPolicy(require_fresh=True))
        assert verify_snapshot(engine, real, initial.snapshot_id) == before
    finally:
        engine.dispose()
