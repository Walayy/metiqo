"""Historisation transactionnelle des captures de cotes fournisseur."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, RowMapping, Table, create_engine, select

from metiquo.contracts import OddsCaptureResult, OddsSnapshot
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ProviderStatus,
    SelectionType,
)
from metiquo.contracts.odds_provider import (
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.db.odds_models import (
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsEvent,
    ProviderOddsMarket,
    ProviderOddsSelection,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mock import MockScenarioKey, build_mock_scenario_catalog
from metiquo.providers import (
    ManualImportOddsProvider,
    provider_entity_uuid,
    provider_market_uuid,
)
from metiquo.repositories import MockOddsProvider
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource
from tests.integration.test_migrations import alembic_config

_REFERENCE_TIME = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)


@pytest.mark.integration
def test_mock_price_history_is_appended_and_exact_replay_is_deduplicated(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    seed = f"odd-007-{uuid4()}"
    catalog = build_mock_scenario_catalog(seed, FixedClock(UtcInstant(_REFERENCE_TIME)))
    scenario = catalog[MockScenarioKey.ODDS_CHANGE_WHILE_OPEN]
    first, second = scenario.odds_history
    source = OddsCaptureSource("mock", "Mock deterministic feed", f"mock-catalog:{seed}")
    service = OddsCaptureService(
        engine,
        FixedClock(UtcInstant(_REFERENCE_TIME + timedelta(minutes=1))),
    )

    before = MockOddsProvider(
        catalog,
        FixedClock(UtcInstant(second.captured_at - timedelta(microseconds=1))),
    )
    event = _provider_event(before, MockScenarioKey.ODDS_CHANGE_WHILE_OPEN)
    first_report = service.capture_event(before, event, source)
    replay_report = service.capture_event(before, event, source)

    after = MockOddsProvider(
        catalog,
        FixedClock(UtcInstant(second.captured_at + timedelta(seconds=1))),
    )
    changed_report = service.capture_event(
        after,
        _provider_event(after, MockScenarioKey.ODDS_CHANGE_WHILE_OPEN),
        source,
    )

    assert first_report.inserted_snapshots == 1
    assert replay_report.inserted_snapshots == 0
    assert replay_report.duplicate_snapshots == 1
    assert changed_report.received_snapshots == 2
    assert changed_report.inserted_snapshots == 1
    assert changed_report.duplicate_snapshots == 1
    assert _stored_prices(engine, first_report.event_id) == [
        Decimal("4.20000000"),
        Decimal("3.60000000"),
    ]
    assert first.odds_snapshot_id != second.odds_snapshot_id
    engine.dispose()


@pytest.mark.integration
def test_manual_capture_keeps_document_hash_and_complete_provider_identity(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    provider_code = f"manual-{uuid4()}"
    provider = ManualImportOddsProvider(
        provider_code,
        clock=FixedClock(UtcInstant(_REFERENCE_TIME)),
    )
    payload = json.dumps([_manual_row(provider_code)], separators=(",", ":")).encode()
    imported = provider.import_document(payload, document_format="json")
    event = provider.list_events(
        _REFERENCE_TIME,
        _REFERENCE_TIME + timedelta(days=2),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    raw_hash = imported.import_key.removeprefix("sha256:")
    service = OddsCaptureService(
        engine,
        FixedClock(UtcInstant(_REFERENCE_TIME + timedelta(minutes=1))),
    )

    report = service.capture_event(
        provider,
        event,
        OddsCaptureSource(
            "manual_import",
            "Manual import",
            imported.import_key,
            raw_hash,
        ),
    )

    assert imported.committed is True
    assert report.received_snapshots == report.inserted_snapshots == 1
    providers = cast(Table, OddsProviderRecord.__table__)
    events = cast(Table, ProviderOddsEvent.__table__)
    markets = cast(Table, ProviderOddsMarket.__table__)
    selections = cast(Table, ProviderOddsSelection.__table__)
    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    with engine.connect() as connection:
        identity = connection.execute(
            select(
                providers.c.code,
                events.c.provider_event_id,
                markets.c.provider_market_id,
                selections.c.provider_selection_id,
                snapshots.c.raw_payload_sha256,
                snapshots.c.observation_fingerprint,
            )
            .select_from(
                snapshots.join(providers, snapshots.c.provider_id == providers.c.id)
                .join(events, snapshots.c.event_id == events.c.id)
                .join(markets, snapshots.c.market_id == markets.c.id)
                .join(selections, snapshots.c.selection_id == selections.c.id)
            )
            .where(snapshots.c.event_id == report.event_id)
        ).one()
    assert identity.code == provider_code
    assert identity.provider_event_id == "manual-event"
    assert identity.provider_market_id == "manual-market"
    assert identity.provider_selection_id == "manual-team-a"
    assert identity.raw_payload_sha256 == raw_hash
    assert len(identity.observation_fingerprint) == 64
    engine.dispose()


@pytest.mark.integration
def test_confirmation_and_price_status_line_or_name_changes_never_overwrite_history(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    provider = _ChangingProvider(f"changing-{uuid4()}")
    service = OddsCaptureService(
        engine,
        FixedClock(UtcInstant(_REFERENCE_TIME + timedelta(minutes=10))),
    )

    for state in range(3):
        provider.state = state
        report = service.capture_event(
            provider,
            provider.event(),
            OddsCaptureSource(
                "licensed_feed",
                "Licensed fixture",
                f"registered-payload:{state}",
                hashlib.sha256(f"payload-{state}".encode()).hexdigest(),
            ),
        )
        assert report.inserted_snapshots == 1

    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    with engine.connect() as connection:
        rows = tuple(
            connection.execute(
                select(
                    snapshots.c.decimal_odds,
                    snapshots.c.event_status,
                    snapshots.c.market_status,
                    snapshots.c.line,
                    snapshots.c.selection_label,
                    snapshots.c.captured_at,
                )
                .where(snapshots.c.event_id == report.event_id)
                .order_by(snapshots.c.captured_at)
            ).mappings()
        )

    assert [_history_values(row) for row in rows] == [
        ("1.80000000", "scheduled", "open", None, "Alpha"),
        ("1.80000000", "scheduled", "open", None, "Alpha"),
        ("2.05000000", "live", "suspended", "1.50000000", "Alpha Prime"),
    ]
    assert rows[0]["captured_at"] < rows[1]["captured_at"] < rows[2]["captured_at"]
    engine.dispose()


def _provider_event(provider: MockOddsProvider, key: MockScenarioKey) -> ProviderEvent:
    provider_event_id = f"mock-event-{key.value}"
    return next(
        event
        for event in provider.list_events(
            _REFERENCE_TIME - timedelta(days=2),
            _REFERENCE_TIME + timedelta(days=2),
            GameTitle.LEAGUE_OF_LEGENDS,
        )
        if event.provider_event_id == provider_event_id
    )


def _manual_row(provider_code: str) -> dict[str, object]:
    return {
        "best_of": 3,
        "captured_at": (_REFERENCE_TIME - timedelta(minutes=1)).isoformat(),
        "competition": "Manual League",
        "decimal_odds": "1.80",
        "event_status": "scheduled",
        "game_title": "lol",
        "line": None,
        "market_label": "Match Winner",
        "market_status": "open",
        "market_type": "MATCH_WINNER",
        "participant_a": "Manual Alpha",
        "participant_b": "Manual Beta",
        "period": "SERIES",
        "provenance_reference": "manual:test:team-a:v1",
        "provider": provider_code,
        "provider_event_id": "manual-event",
        "provider_market_id": "manual-market",
        "provider_selection_id": "manual-team-a",
        "selection": "TEAM_A",
        "selection_label": "Manual Alpha",
        "settlement_rules_version": "match-winner-v1",
        "starts_at": (_REFERENCE_TIME + timedelta(days=1)).isoformat(),
        "timestamp_reliable": True,
    }


def _stored_prices(engine: Engine, event_id: UUID) -> list[Decimal]:
    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    with engine.connect() as connection:
        return list(
            connection.execute(
                select(snapshots.c.decimal_odds)
                .where(snapshots.c.event_id == event_id)
                .order_by(snapshots.c.captured_at)
            ).scalars()
        )


def _history_values(row: RowMapping) -> tuple[str, str, str, str | None, str]:
    line = cast(Decimal | None, row["line"])
    return (
        str(row["decimal_odds"]),
        cast(str, row["event_status"]),
        cast(str, row["market_status"]),
        None if line is None else str(line),
        cast(str, row["selection_label"]),
    )


@dataclass(slots=True)
class _ChangingProvider:
    provider_code: str
    state: int = 0
    event_id: UUID = field(default_factory=uuid4)

    def event(self) -> ProviderEvent:
        return ProviderEvent(
            provider_event_id="changing-event",
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
            competition="Changing League",
            participants=("Alpha", "Beta"),
            starts_at=_REFERENCE_TIME + timedelta(hours=1),
            best_of=3,
            status=EventStatus.LIVE if self.state == 2 else EventStatus.SCHEDULED,
            collected_at=self._captured_at(),
            source_reference=f"licensed-fixture:event:{self.state}",
        )

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        event = self.event()
        return (
            (event,)
            if game_title is event.game_title and starts_from <= event.starts_at <= starts_to
            else ()
        )

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        if provider_event_id != "changing-event":
            return ()
        label = "Alpha Prime" if self.state == 2 else "Alpha"
        return (
            ProviderMarket(
                provider_event_id=provider_event_id,
                provider_market_id="changing-market",
                raw_label="Series winner updated" if self.state == 2 else "Series winner",
                market_type=MarketType.MATCH_WINNER,
                period=MarketPeriod.SERIES,
                line=Decimal("1.5") if self.state == 2 else None,
                selections=(
                    ProviderSelection(
                        provider_selection_id="changing-team-a",
                        selection=SelectionType.TEAM_A,
                        label=label,
                        decimal_odds=self._odds(),
                    ),
                ),
                status=MarketStatus.SUSPENDED if self.state == 2 else MarketStatus.OPEN,
                captured_at=self._captured_at(),
                settlement_rules_version="match-winner-v1",
            ),
        )

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        if provider_event_id != "changing-event":
            raise LookupError(provider_event_id)
        captured_at = self._captured_at()
        market_id = provider_market_uuid(
            self.provider_code,
            provider_event_id,
            "changing-market",
        )
        odds = self._odds()
        snapshot = OddsSnapshot(
            odds_snapshot_id=provider_entity_uuid(
                self.provider_code,
                "snapshot",
                str(self.state),
            ),
            event_id=self.event_id,
            market_id=market_id,
            selection=SelectionType.TEAM_A,
            provider=self.provider_code,
            provider_status=ProviderStatus.OPERATIONAL,
            market_status=MarketStatus.SUSPENDED if self.state == 2 else MarketStatus.OPEN,
            decimal_odds=odds,
            captured_at=captured_at,
            age_seconds=0,
            raw_implied_probability=(Decimal(1) / odds).quantize(Decimal("0.00000001")),
            no_vig_probability=None,
            provenance_reference=f"licensed-fixture:odds:{self.state}",
        )
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=captured_at,
            snapshots=(snapshot,),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.OPERATIONAL,
            checked_at=self._captured_at(),
            last_success_at=self._captured_at(),
        )

    def _captured_at(self) -> datetime:
        return _REFERENCE_TIME + timedelta(minutes=self.state)

    def _odds(self) -> Decimal:
        return Decimal("2.05") if self.state == 2 else Decimal("1.80")
