from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from metiquo_core.config import Settings
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerPayload,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSnapshot,
    IngestionRun,
)
from metiquo_worker import stake_sync
from metiquo_worker.stake_policy import StakeDeferred, StakePolicy
from metiquo_worker.stake_storage import publish, remember_event
from metiquo_worker.stake_types import (
    Capture,
    EventMetadata,
    MarketReading,
    Participant,
    SelectionReading,
    Tab,
    selection_identity,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def metadata(source_id="123", **updates):
    now = datetime.now(UTC)
    return EventMetadata(
        game="league-of-legends",
        source_id=source_id,
        url=f"https://stake.bet/fr/sports/league-of-legends/region/league/{source_id}-a-b",
        competition_key="/fr/sports/league-of-legends/region/league",
        participants=[Participant(name="A Academy", position=0), Participant(name="B", position=1)],
        starts_at=now + timedelta(days=1),
        status="scheduled",
        observed_at=now,
    ).model_copy(update=updates)


def market(odds="2,00", name="2.5", **updates):
    return MarketReading(
        label="Nombre de maps",
        expanded=True,
        controls=[],
        selections=[
            SelectionReading(
                name=name,
                column="Plus de",
                accessible_name=f"Over {name}",
                odds_raw=odds,
                disabled=odds is None,
            )
        ],
    ).model_copy(update=updates)


def capture(meta, markets=None):
    return Capture(
        metadata=meta,
        tab="tab-main",
        tabs=[Tab(id="tab-main", label="Principal", disabled=False)],
        markets=markets or [market()],
    )


def ingestion(engine):
    run_id = uuid4()
    with Session(engine) as db, db.begin():
        db.add(IngestionRun(id=run_id, source="stake", scope="prematch"))
    return run_id


@pytest.mark.parametrize("status", ["closed", "unknown"])
def test_unverified_or_closed_states_are_ineligible(status):
    assert not metadata(status=status).eligible(datetime.now(UTC))


def test_live_marker_remains_collectible_with_past_or_unknown_start():
    now = datetime.now(UTC)
    assert metadata(status="live", starts_at=now - timedelta(hours=1)).eligible(now)
    assert metadata(status="live", starts_at=None).eligible(now)
    assert not metadata(status="live", participants=[Participant(name="A", position=0)]).eligible(
        now
    )


def test_unknown_timezone_missing_date_and_start_guard_do_not_become_prematch():
    assert not metadata(starts_at=None).eligible(datetime.now(UTC))
    assert not metadata(starts_at=datetime.now(UTC) + timedelta(seconds=30)).eligible(
        datetime.now(UTC), 60
    )
    assert not metadata(starts_at=datetime.now(UTC) - timedelta(seconds=1)).eligible(
        datetime.now(UTC)
    )


def test_cut_is_not_the_odds_and_identifies_line_changes_even_with_source_ids():
    total = market("1,85")
    selection = total.selections[0].model_copy(update={"source_id": "stable-source-id"})
    key, _, line, raw, ordinal = selection_identity(total, selection)
    assert line == Decimal("2.5") and raw == "2.5" and ordinal is None
    assert selection_identity(total, selection.model_copy(update={"name": "3.5"}))[0] != key
    assert selection_identity(total, selection.model_copy(update={"odds_raw": "3,20"}))[0] == key
    score = market(name="0:3", label="Résultat final")
    assert selection_identity(score, score.selections[0])[2] is None
    nth = market(name="10", label="Map 1 - º meurtre")
    assert selection_identity(nth, nth.selections[0])[4] == 10


def test_yes_no_columns_are_distinct_and_unknown_market_labels_survive():
    item = market(name="Oui", label="Gagne au moins un map")
    left = item.selections[0].model_copy(update={"column": "Team A", "accessible_name": "Oui"})
    right = left.model_copy(update={"column": "Team B"})
    assert selection_identity(item, left)[0] != selection_identity(item, right)[0]
    unknown = market(name="12.5", label="A future esport market")
    assert selection_identity(unknown, unknown.selections[0])[2] is None


def test_row_identity_survives_loss_of_accessible_name_when_market_suspends():
    item = market(name="Oui", label="Gagne au moins un map")
    open_selection = item.selections[0].model_copy(
        update={"row_label": "LODIS", "accessible_name": "Yes LODIS", "disabled": False}
    )
    suspended = open_selection.model_copy(
        update={"accessible_name": None, "odds_raw": None, "disabled": True}
    )
    other_team = suspended.model_copy(update={"row_label": "Pyramid IV Esports"})
    assert selection_identity(item, open_selection)[0] == selection_identity(item, suspended)[0]
    assert selection_identity(item, suspended)[0] != selection_identity(item, other_team)[0]


@pytest.mark.integration
def test_price_history_is_append_only_and_content_is_deduplicated(database):
    engine, _ = database
    original = metadata()
    for odds in ["2,00", "2,20", "2,00", "2,00"]:
        meta = original.model_copy(update={"observed_at": datetime.now(UTC)})
        run = ingestion(engine)
        readings = [capture(meta, [market(odds)])]
        assert publish(engine, run, readings, meta, guard_seconds=0)["quotes"] == 1
        assert publish(engine, run, readings, meta, guard_seconds=0)["quotes"] == 0
    with Session(engine) as db:
        assert list(
            db.scalars(select(BookmakerQuote.odds).order_by(BookmakerQuote.observed_at))
        ) == [Decimal("2"), Decimal("2.2"), Decimal("2"), Decimal("2")]
        assert db.scalar(select(func.count()).select_from(BookmakerSelection)) == 1
        assert db.scalar(select(func.count()).select_from(BookmakerPayload)) == 2
        assert db.scalar(select(func.count()).select_from(BookmakerSnapshot)) == 4


@pytest.mark.integration
def test_line_changes_and_suspension_do_not_relabel_old_quotes(database):
    engine, _ = database
    original = metadata()
    for line, odds in [("2.5", "2,00"), ("3.5", "1,80"), ("3.5", None)]:
        meta = original.model_copy(update={"observed_at": datetime.now(UTC)})
        publish(
            engine, ingestion(engine), [capture(meta, [market(odds, line)])], meta, guard_seconds=0
        )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BookmakerSelection)) == 2
        current = db.execute(
            text("SELECT line, odds, disabled FROM bookmaker_current_quotes")
        ).all()
        assert current == [(Decimal("3.5"), None, True)]
        assert db.scalar(select(func.count()).select_from(BookmakerQuote)) == 3


@pytest.mark.integration
@pytest.mark.parametrize("start_offset", [None, -3600])
def test_live_without_future_start_and_visible_unpriced_selection(database, start_offset):
    engine, _ = database
    start = datetime.now(UTC) + timedelta(seconds=start_offset) if start_offset else None
    live = metadata(status="live", starts_at=start)
    closed_button = market(None)
    closed_button.selections[0].disabled = False
    counts = publish(
        engine, ingestion(engine), [capture(live, [closed_button])], live, guard_seconds=60
    )
    assert counts["suspendedQuotes"] == 1 and counts["openQuotes"] == 0
    with Session(engine) as db:
        snapshot = db.scalar(select(BookmakerSnapshot))
        quote = db.scalar(select(BookmakerQuote))
        assert snapshot is not None and snapshot.phase == "live"
        assert snapshot.scheduled_start_at == start
        assert quote is not None and quote.odds is None and quote.disabled
        assert db.execute(
            text("SELECT captured_phase, quote_open FROM bookmaker_current_quotes")
        ).one() == ("live", False)


@pytest.mark.integration
def test_live_transition_is_collected_and_only_closed_status_stops_restart(database):
    engine, _ = database
    meta = metadata()
    publish(engine, ingestion(engine), [capture(meta)], meta, guard_seconds=0)
    live = meta.model_copy(update={"status": "live", "observed_at": datetime.now(UTC)})
    with pytest.raises(ValueError):
        publish(engine, ingestion(engine), [capture(meta)], live, guard_seconds=0)
    assert (
        publish(engine, ingestion(engine), [capture(live)], live, guard_seconds=0)["openQuotes"]
        == 1
    )
    suspended = live.model_copy(update={"observed_at": datetime.now(UTC)})
    counts = publish(
        engine, ingestion(engine), [capture(suspended, [market(None)])], suspended, guard_seconds=0
    )
    assert counts["suspendedQuotes"] == 1 and counts["openQuotes"] == 0
    reopened = live.model_copy(update={"observed_at": datetime.now(UTC)})
    publish(engine, ingestion(engine), [capture(reopened)], reopened, guard_seconds=0)
    remember_event(engine, live)
    with Session(engine) as db:
        event = db.get(BookmakerEvent, meta.id)
        assert event is not None and event.stopped_at is None
        assert db.execute(
            text("SELECT captured_phase, event_status, quote_open FROM bookmaker_current_quotes")
        ).one() == ("live", "live", True)
        assert list(
            db.execute(text("SELECT odds, disabled FROM bookmaker_quotes ORDER BY observed_at"))
        ) == [
            (Decimal("2"), False),
            (Decimal("2"), False),
            (None, True),
            (Decimal("2"), False),
        ]
    closed = live.model_copy(update={"status": "closed", "observed_at": datetime.now(UTC)})
    remember_event(engine, closed, stop_reason="closed")
    with pytest.raises(ValueError):
        publish(engine, ingestion(engine), [capture(live)], live, guard_seconds=0)
    with Session(engine) as db:
        assert db.get(BookmakerEvent, meta.id).stopped_at is not None
        assert db.scalar(select(func.count()).select_from(BookmakerQuote)) == 4
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("UPDATE bookmaker_events SET stopped_at=NULL,stop_reason=NULL WHERE id=:id"),
            {"id": meta.id},
        )


@pytest.mark.integration
def test_missing_tab_or_invalid_odds_preserves_previous_snapshot(database):
    engine, _ = database
    meta = metadata()
    publish(engine, ingestion(engine), [capture(meta)], meta, guard_seconds=0)
    missing = capture(meta)
    missing.tabs.append(Tab(id="tab-map-1", label="Map 1", disabled=False))
    for invalid in [missing, capture(meta, [market("not a price")])]:
        with pytest.raises(ValueError):
            publish(engine, ingestion(engine), [invalid], meta, guard_seconds=0)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BookmakerSnapshot)) == 1


@pytest.mark.integration
def test_database_checks_provenance_and_worker_cannot_modify_history(database):
    engine, _ = database
    meta = metadata()
    publish(engine, ingestion(engine), [capture(meta)], meta, guard_seconds=0)
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO bookmaker_quotes SELECT snapshot_id,selection_id,"
                "observed_at-interval '1 hour',tab,odds,odds_raw,disabled "
                "FROM bookmaker_quotes LIMIT 1"
            )
        )
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE metiquo_worker"))
        connection.execute(text("DELETE FROM bookmaker_quotes"))


@pytest.mark.integration
def test_scheduler_prioritizes_live_and_revisits_past_events(database, monkeypatch):
    engine, settings = database
    stopped = metadata("1")
    past = metadata("2", starts_at=datetime.now(UTC) - timedelta(minutes=1))
    live = metadata("3", status="live")
    future = metadata("4")
    remember_event(engine, stopped, stop_reason="closed")
    remember_event(engine, past)
    opened = []

    class Browser:
        requests = 0
        refusals = []

        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def fixtures(self, _game):
            return [stopped, past, live, future]

        def event(self, fixture):
            opened.append(fixture.source_id)
            meta = fixture.model_copy(
                update={
                    "status": "live" if fixture.source_id in {"2", "3"} else "scheduled",
                    "observed_at": datetime.now(UTC),
                }
            )
            return [capture(meta)], meta

    monkeypatch.setattr(stake_sync, "StakeBrowser", Browser)
    config = settings.model_copy(update={"stake_enabled": True})
    for _ in range(2):
        run_id = stake_sync.sync_stake(engine, config)
        with Session(engine) as db:
            details = db.get(IngestionRun, run_id).details
            assert details["eventsStopped"] == 1 and details["eventsCollected"] == 3
            assert details["liveEvents"] == 2
    assert opened == ["3", "2", "4", "3", "2", "4"]


@pytest.mark.integration
def test_stake_budget_and_retry_after_survive_a_new_worker(database):
    engine, _ = database
    settings = Settings(database_url="postgresql://unused")
    policy = StakePolicy(engine, settings)
    policy.pending_requests = 17
    policy.flush()
    assert StakePolicy(engine, settings).request_count == 17
    earliest = datetime.now(UTC).timestamp() + 7200
    with pytest.raises(StakeDeferred) as refusal:
        policy.block("rate_limited", 7200)
    assert refusal.value.retry_at >= earliest
    with pytest.raises(StakeDeferred) as retry:
        StakePolicy(engine, settings).check()
    assert retry.value.retry_at == refusal.value.retry_at
