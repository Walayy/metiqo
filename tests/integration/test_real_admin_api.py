"""Contrat d'administration identique en mock et réel sur données persistées."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy import Table, create_engine, insert, update

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.config import Settings
from metiquo.db.raw_models import (
    IngestionRun,
    QualityIssue,
    QuarantineItem,
    Snapshot,
    SourceCatalog,
)
from metiquo.foundation.time import FixedClock, UtcInstant

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
YEAR = 2098


class ReadyProbe:
    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=True)


def _alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> Response:
    async def send() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(send())


def _settings(database_url: str, mode: str) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": mode,
            "database_url": database_url,
            "object_store_root": str(ROOT / ".unused-real-admin-store"),
            "odds_provider": "disabled" if mode == "real" else "mock",
            "oe_current_year": YEAR,
            "mock_seed": "real-admin-contract",
        }
    )


def _seed_real_health(database_url: str, idempotency_key: str) -> None:
    engine = create_engine(database_url)
    catalog_id = uuid4()
    validated_id = uuid4()
    quarantined_id = uuid4()
    succeeded_run_id = uuid4()
    failed_run_id = uuid4()
    drive_id = f"real-admin-{catalog_id.hex}"
    request_hash = hashlib.sha256(f"real.oe.sync\0{YEAR}\0{idempotency_key}".encode()).hexdigest()
    catalog = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    quality_issues = cast(Table, QualityIssue.__table__)
    quarantine_items = cast(Table, QuarantineItem.__table__)
    with engine.begin() as connection:
        connection.execute(
            insert(catalog).values(
                id=catalog_id,
                provider="oracles_elixir",
                dataset="league_of_legends_match_data",
                season_year=YEAR,
                landing_page="https://oracleselixir.com/tools/downloads",
                drive_file_id=drive_id,
                source_name=f"{YEAR}_LoL_esports_match_data.csv",
                origin="validated-bootstrap",
                status="active",
                discovered_at=NOW - timedelta(days=1),
                last_confirmed_at=NOW - timedelta(days=1),
                discovery_payload_hash="d" * 64,
                mutable=False,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(days=1),
            )
        )
        manifest = {
            "sha256": "a" * 64,
            "byteSize": 846,
            "schemaFingerprint": "c" * 64,
            "rowCount": 12,
            "minEventDate": "2026-01-10T00:00:00Z",
            "maxEventDate": "2026-01-10T00:00:00Z",
            "qualityStatus": "passed",
            "compression": "none",
            "encoding": "utf-8",
            "delimiter": ",",
        }
        connection.execute(
            insert(snapshots),
            [
                {
                    "id": validated_id,
                    "source_catalog_id": catalog_id,
                    "year": YEAR,
                    "source_file_id": drive_id,
                    "status": "validated",
                    "sha256": "a" * 64,
                    "byte_size": 846,
                    "content_type": "text/csv",
                    "object_key": f"year={YEAR}/sha256={'a' * 64}/source.csv",
                    "received_at": NOW - timedelta(hours=2),
                    "validated_at": NOW - timedelta(hours=2),
                    "failure_reason": None,
                    "manifest": manifest,
                    "created_at": NOW - timedelta(hours=2),
                },
                {
                    "id": quarantined_id,
                    "source_catalog_id": catalog_id,
                    "year": YEAR,
                    "source_file_id": drive_id,
                    "status": "quarantined",
                    "sha256": "b" * 64,
                    "byte_size": 64,
                    "content_type": "text/html",
                    "object_key": f"quarantine/year={YEAR}/sha256={'b' * 64}/source.bin",
                    "received_at": NOW - timedelta(hours=1),
                    "validated_at": None,
                    "failure_reason": "UNEXPECTED_HTML",
                    "manifest": {},
                    "created_at": NOW - timedelta(hours=1),
                },
            ],
        )
        connection.execute(
            update(catalog)
            .where(catalog.c.id == catalog_id)
            .values(current_snapshot_id=validated_id, updated_at=NOW)
        )
        connection.execute(
            insert(runs),
            [
                {
                    "id": succeeded_run_id,
                    "source_catalog_id": catalog_id,
                    "snapshot_id": validated_id,
                    "run_kind": "sync",
                    "status": "succeeded",
                    "attempt": 1,
                    "transport": "google-drive-public",
                    "request_key_hash": request_hash,
                    "correlation_id": f"real-admin-{succeeded_run_id}",
                    "started_at": NOW - timedelta(hours=2, minutes=1),
                    "finished_at": NOW - timedelta(hours=2),
                    "counters": {"total": 12},
                    "error_code": None,
                    "created_at": NOW - timedelta(hours=2, minutes=1),
                },
                {
                    "id": failed_run_id,
                    "source_catalog_id": catalog_id,
                    "snapshot_id": None,
                    "run_kind": "sync",
                    "status": "failed",
                    "attempt": 1,
                    "transport": "google-drive-public",
                    "request_key_hash": None,
                    "correlation_id": f"real-admin-{failed_run_id}",
                    "started_at": NOW - timedelta(hours=1, minutes=1),
                    "finished_at": NOW - timedelta(hours=1),
                    "error_code": "SOURCE_QUOTA_EXCEEDED",
                    "counters": {},
                    "created_at": NOW - timedelta(hours=1, minutes=1),
                },
            ],
        )
        connection.execute(
            insert(quality_issues).values(
                id=uuid4(),
                run_id=failed_run_id,
                snapshot_id=None,
                code="SCHEMA_CORE_MISSING",
                severity="blocking",
                message="colonne cœur absente",
                context={},
                created_at=NOW - timedelta(hours=1),
            )
        )
        connection.execute(
            insert(quarantine_items).values(
                id=uuid4(),
                snapshot_id=quarantined_id,
                run_id=failed_run_id,
                reason_code="UNEXPECTED_HTML",
                object_key=f"quarantine/year={YEAR}/sha256={'b' * 64}/source.bin",
                payload_sha256="b" * 64,
                diagnostic={"contentType": "text/html"},
                status="pending",
                quarantined_at=NOW - timedelta(hours=1),
            )
        )
    engine.dispose()


@pytest.mark.integration
def test_real_admin_uses_mock_contracts_and_survives_latest_failure(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    idempotency_key = "real-admin-idempotency"
    _seed_real_health(postgresql_url, idempotency_key)
    clock = FixedClock(UtcInstant(NOW))
    real_app = create_app(
        settings=_settings(postgresql_url, "real"),
        readiness_probe=ReadyProbe(),
        clock=clock,
    )
    mock_app = create_app(
        settings=_settings(postgresql_url, "mock"),
        readiness_probe=ReadyProbe(),
        clock=clock,
    )

    real_sources = _request(real_app, "GET", "/api/v1/admin/data-sources")
    real_runs = _request(real_app, "GET", "/api/v1/admin/ingestion-runs")
    real_issues = _request(real_app, "GET", "/api/v1/admin/quality-issues")
    assert (real_sources.status_code, real_runs.status_code, real_issues.status_code) == (
        200,
        200,
        200,
    )
    source_payload = real_sources.json()
    run_payload = real_runs.json()
    issue_payload = real_issues.json()
    assert source_payload["meta"]["dataMode"] == "real"
    assert source_payload["data"][0]["status"] == "degraded"
    assert source_payload["data"][0]["lastSuccessAt"] == "2026-09-05T10:00:00Z"
    succeeded = next(item for item in run_payload["data"] if item["status"] == "succeeded")
    assert succeeded["snapshotSha256"] == "a" * 64
    assert succeeded["rowCount"] == 12
    assert succeeded["minEventDate"] == "2026-01-10T00:00:00Z"
    assert succeeded["schemaFingerprint"] == "c" * 64
    assert succeeded["schemaChanged"] is False
    assert {item["status"] for item in issue_payload["data"]} == {"open", "quarantined"}

    for path, real_payload in (
        ("/api/v1/admin/data-sources", source_payload),
        ("/api/v1/admin/ingestion-runs", run_payload),
        ("/api/v1/admin/quality-issues", issue_payload),
    ):
        mock_payload = _request(mock_app, "GET", path).json()
        assert set(real_payload) == set(mock_payload)
        assert set(real_payload["data"][0]) == set(mock_payload["data"][0])

    sync = _request(
        real_app,
        "POST",
        "/api/v1/admin/oracles-elixir/sync",
        headers={"Idempotency-Key": idempotency_key},
    )
    assert sync.status_code == 200
    assert sync.json()["data"]["status"] == "succeeded"
    assert sync.json()["meta"]["dataMode"] == "real"
