"""Contraintes temporelles et immutabilité du socle de cotes."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, inspect, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.db.odds_models import (
    OddsProviderHealth,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsEvent,
    ProviderOddsMarket,
    ProviderOddsSelection,
)
from tests.integration.test_migrations import alembic_config

_CAPTURED_AT = datetime(2026, 9, 7, 14, 0, tzinfo=UTC)


@pytest.mark.integration
def test_odds_snapshot_requires_reliable_time_or_informational_status_and_is_immutable(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    provider_id, event_id, market_id, selection_id = _seed_identities(engine)
    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    health = cast(Table, OddsProviderHealth.__table__)
    valid_id = uuid4()
    health_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(health).values(
                id=health_id,
                provider_id=provider_id,
                status="operational",
                checked_at=_CAPTURED_AT,
                last_success_at=_CAPTURED_AT,
                detail="capture accepted",
            )
        )
        connection.execute(
            insert(snapshots).values(
                **_snapshot(
                    valid_id,
                    provider_id=provider_id,
                    event_id=event_id,
                    market_id=market_id,
                    selection_id=selection_id,
                    decimal_odds=Decimal("2.25000000"),
                    captured_at=_CAPTURED_AT,
                    timestamp_reliable=True,
                    informational_only=False,
                )
            )
        )

    with engine.connect() as connection:
        stored = connection.execute(
            select(
                snapshots.c.decimal_odds,
                snapshots.c.captured_at,
                snapshots.c.informational_only,
            ).where(snapshots.c.id == valid_id)
        ).one()
    assert stored.decimal_odds == Decimal("2.25000000")
    assert stored.captured_at == _CAPTURED_AT
    assert stored.informational_only is False

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE odds.snapshots SET decimal_odds = 3 WHERE id = :id"),
            {"id": valid_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("DELETE FROM odds.snapshots WHERE id = :id"), {"id": valid_id})
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE odds.provider_health SET status = 'degraded' WHERE id = :id"),
            {"id": health_id},
        )

    with pytest.raises(DBAPIError, match="decimal_odds"), engine.begin() as connection:
        connection.execute(
            insert(snapshots).values(
                **_snapshot(
                    uuid4(),
                    provider_id=provider_id,
                    event_id=event_id,
                    market_id=market_id,
                    selection_id=selection_id,
                    decimal_odds=Decimal("0.99000000"),
                    captured_at=_CAPTURED_AT,
                    timestamp_reliable=True,
                    informational_only=False,
                )
            )
        )
    with pytest.raises(DBAPIError, match="signal_timestamp"), engine.begin() as connection:
        connection.execute(
            insert(snapshots).values(
                **_snapshot(
                    uuid4(),
                    provider_id=provider_id,
                    event_id=event_id,
                    market_id=market_id,
                    selection_id=selection_id,
                    decimal_odds=Decimal("2.10000000"),
                    captured_at=None,
                    timestamp_reliable=False,
                    informational_only=False,
                )
            )
        )
    informational_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(snapshots).values(
                **_snapshot(
                    informational_id,
                    provider_id=provider_id,
                    event_id=event_id,
                    market_id=market_id,
                    selection_id=selection_id,
                    decimal_odds=Decimal("2.10000000"),
                    captured_at=None,
                    timestamp_reliable=False,
                    informational_only=True,
                )
            )
        )
    with engine.connect() as connection:
        assert connection.execute(
            select(snapshots.c.informational_only).where(snapshots.c.id == informational_id)
        ).scalar_one()
        index = next(
            item
            for item in inspect(connection).get_indexes("snapshots", schema="odds")
            if item["name"] == "ix_odds_snapshots_event_market_selection_captured"
        )
    assert index["column_names"] == ["event_id", "market_id", "selection_id", "captured_at"]
    engine.dispose()


def _seed_identities(engine: Engine) -> tuple[UUID, UUID, UUID, UUID]:
    providers = cast(Table, OddsProviderRecord.__table__)
    events = cast(Table, ProviderOddsEvent.__table__)
    markets = cast(Table, ProviderOddsMarket.__table__)
    selections = cast(Table, ProviderOddsSelection.__table__)
    provider_id, event_id, market_id, selection_id = (uuid4() for _index in range(4))
    with engine.begin() as connection:
        connection.execute(
            insert(providers).values(
                id=provider_id,
                code=f"manual-{provider_id}",
                display_name="Manual test feed",
                provider_type="manual_import",
                enabled=True,
                created_at=_CAPTURED_AT,
            )
        )
        connection.execute(
            insert(events).values(
                id=event_id,
                provider_id=provider_id,
                provider_event_id=f"event-{event_id}",
                game_title="lol",
                competition_name="Test League",
                participants=["Team A", "Team B"],
                starts_at=_CAPTURED_AT + timedelta(hours=4),
                best_of=3,
                status="scheduled",
                collected_at=_CAPTURED_AT,
                source_reference="manual:test:event:v1",
                created_at=_CAPTURED_AT,
            )
        )
        connection.execute(
            insert(markets).values(
                id=market_id,
                event_id=event_id,
                provider_market_id=f"market-{market_id}",
                raw_label="Match winner",
                market_type="MATCH_WINNER",
                period="SERIES",
                line=None,
                settlement_rules_version="match-winner-v1",
                created_at=_CAPTURED_AT,
            )
        )
        connection.execute(
            insert(selections).values(
                id=selection_id,
                market_id=market_id,
                provider_selection_id=f"selection-{selection_id}",
                raw_label="Team A",
                selection_type="TEAM_A",
                created_at=_CAPTURED_AT,
            )
        )
    return provider_id, event_id, market_id, selection_id


def _snapshot(
    snapshot_id: UUID,
    *,
    provider_id: UUID,
    event_id: UUID,
    market_id: UUID,
    selection_id: UUID,
    decimal_odds: Decimal,
    captured_at: datetime | None,
    timestamp_reliable: bool,
    informational_only: bool,
) -> dict[str, object]:
    return {
        "captured_at": captured_at,
        "decimal_odds": decimal_odds,
        "event_id": event_id,
        "event_status": "scheduled",
        "id": snapshot_id,
        "informational_only": informational_only,
        "line": None,
        "market_id": market_id,
        "market_status": "open",
        "observation_fingerprint": _hash(str(snapshot_id)),
        "provenance_reference": f"manual:test:{snapshot_id}",
        "provider_id": provider_id,
        "provider_status": "operational",
        "raw_payload_reference": f"manual://test/{snapshot_id}",
        "raw_payload_sha256": _hash(f"raw-{snapshot_id}"),
        "recorded_at": _CAPTURED_AT + timedelta(seconds=1),
        "selection_id": selection_id,
        "selection_label": "Team A",
        "timestamp_reliable": timestamp_reliable,
    }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
