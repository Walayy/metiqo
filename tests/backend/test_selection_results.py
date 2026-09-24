from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerMarket,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    BookmakerPayload,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSelectionResult,
    BookmakerSelectionResultDecision,
    BookmakerSnapshot,
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    MatchSourceLink,
    Team,
)
from metiquo_worker.selection_results import market_kind, settle_selections, source_proof
from metiquo_worker.stake_types import MarketReading, market_identity
from sqlalchemy import func, select
from sqlalchemy.orm import Session

T0 = datetime(2026, 9, 23, 12, tzinfo=UTC)


def match() -> EsportMatch:
    return EsportMatch(
        id=uuid4(),
        source="loltv",
        source_id="fixture",
        league_id="cup",
        home_id="alpha",
        away_id="beta",
        starts_at=T0 - timedelta(hours=3),
        registered_at=T0,
        format="BO3",
    )


def snapshot(match_id, source, status, score, winners, observed_at) -> MatchSnapshot:
    return MatchSnapshot(
        id=uuid4(),
        match_id=match_id,
        source=source,
        source_id="fixture",
        source_url="https://example.com",
        status=status,
        observed_at=observed_at,
        sha256="a" * 64,
        payload={
            "status": status,
            "format": "BO3",
            "seriesScore": score,
            "maps": [
                {"number": number, "status": "finished", "winnerId": winner}
                for number, winner in enumerate(winners, 1)
            ],
        },
    )


def test_source_validation_rejects_live_or_impossible_score_and_tracks_correction():
    fixture = match()
    first = snapshot(
        fixture.id, "loltv", "finished", {"home": 2, "away": 0}, ["alpha", "alpha"], T0
    )
    repeated = snapshot(
        fixture.id,
        "loltv",
        "finished",
        {"home": 2, "away": 0},
        ["alpha", "alpha"],
        T0 + timedelta(minutes=10),
    )
    proof = source_proof([first, repeated], fixture, "loltv")
    assert proof is not None and proof.observed_at == T0 and proof.match_winner == "alpha"
    correction = snapshot(
        fixture.id,
        "loltv",
        "finished",
        {"home": 1, "away": 2},
        ["alpha", "beta", "beta"],
        T0 + timedelta(minutes=20),
    )
    proof = source_proof([first, repeated, correction], fixture, "loltv")
    assert proof is not None and proof.observed_at == correction.observed_at
    assert proof.match_winner == "beta"
    live = snapshot(
        fixture.id,
        "loltv",
        "live",
        {"home": 1, "away": 2},
        ["alpha", "beta", "beta"],
        T0 + timedelta(minutes=21),
    )
    assert source_proof([first, repeated, correction, live], fixture, "loltv") is None
    bad = snapshot(fixture.id, "loltv", "finished", {"home": 2, "away": 0}, ["beta", "alpha"], T0)
    assert source_proof([bad], fixture, "loltv") is None


def test_oracle_requires_complete_numbered_maps_and_sourced_format():
    fixture = match()
    partial = snapshot(
        fixture.id, "oracles-elixir", "finished", {"home": 2, "away": 0}, ["alpha"], T0
    )
    assert source_proof([partial], fixture, "oracles-elixir") is None
    final = snapshot(
        fixture.id, "oracles-elixir", "finished", {"home": 2, "away": 0}, ["alpha", "alpha"], T0
    )
    assert source_proof([final], fixture, "oracles-elixir") is not None
    fixture.format = None
    assert source_proof([final], fixture, "oracles-elixir") is None


def test_only_strict_winner_markets_are_supported():
    base = dict(
        id=uuid4(),
        event_id=uuid4(),
        identity_key="x",
        identity_basis="source",
        first_seen_at=T0,
        last_seen_at=T0,
    )
    match_market = BookmakerMarket(
        **base, label="Vainqueur du match - Two options", family="", scope="match", period=None
    )
    assert market_kind(match_market) == ("match_winner", None)
    map_market = BookmakerMarket(
        **base, label="Map 3 Gagnant - Two options", family="", scope="period", period=3
    )
    assert market_kind(map_market) == ("map_winner", 3)
    map_market.label = "Map 3 - Premier sang"
    assert market_kind(map_market) is None
    french = MarketReading(
        label="Vainqueur de la carte 3", expanded=True, selections=[], controls=[]
    )
    assert market_identity(french)[2] == 3
    map_market.label = french.label
    assert market_kind(map_market) == ("map_winner", 3)


@pytest.mark.integration
def test_settlement_delay_void_fallback_correction_and_retraction(database):
    engine, _ = database
    fixture = match()
    fixture_id = fixture.id
    event_id, snapshot_id, run_id = uuid4(), uuid4(), uuid4()
    markets = [
        ("Vainqueur du match - Two options", "match", None),
        ("Map 1 Gagnant - Two options", "period", 1),
        ("Map 3 Gagnant - Two options", "period", 3),
    ]
    selection_ids = []
    with Session(engine) as db, db.begin():
        db.add(League(id="cup", data={"name": "Cup"}))
        db.flush()
        db.add_all(
            [
                Team(id="alpha", league_id="cup", data={"name": "Alpha", "aliases": ["Alpha"]}),
                Team(id="beta", league_id="cup", data={"name": "Beta", "aliases": ["Beta"]}),
            ]
        )
        db.flush()
        db.add(fixture)
        db.flush()
        db.add_all(
            [
                MatchSourceLink(
                    match_id=fixture.id,
                    provider=provider,
                    source_id="fixture",
                    source_url="https://example.com",
                    source_names={},
                    first_seen_at=T0,
                    last_seen_at=T0,
                )
                for provider in ("loltv", "oracles-elixir")
            ]
        )
        db.add(
            IngestionRun(id=run_id, source="stake", scope="test", status="succeeded", details={})
        )
        db.add(
            BookmakerEvent(
                id=event_id,
                bookmaker="stake",
                game="league-of-legends",
                source_id="fixture",
                source_url="https://stake.bet/fr/sports/league-of-legends/cup/fixture",
                competition_key="cup",
                competition_name="Cup",
                category_name="League of Legends",
                participants=[{"position": 0, "name": "Alpha"}, {"position": 1, "name": "Beta"}],
                participant_keys=["alpha", "beta"],
                starts_at=fixture.starts_at,
                status="live",
                first_seen_at=T0,
                last_seen_at=T0,
                metadata_raw={},
            )
        )
        db.flush()
        mapping = [
            {"position": 0, "name": "Alpha", "teamId": "alpha", "proof": {"basis": "exact-name"}},
            {"position": 1, "name": "Beta", "teamId": "beta", "proof": {"basis": "exact-name"}},
        ]
        db.add(
            BookmakerMatchLink(
                event_id=event_id,
                match_id=fixture.id,
                method="v1",
                evidence={"participants": mapping},
                linked_at=T0,
            )
        )
        db.add(
            BookmakerMatchResolution(
                event_id=event_id,
                status="linked",
                last_match_id=fixture.id,
                checked_at=T0,
                sha256="b" * 64,
                evidence={},
            )
        )
        db.add(BookmakerPayload(sha256="c" * 64, parser_version="test", document={}))
        db.add(
            BookmakerSnapshot(
                id=snapshot_id,
                event_id=event_id,
                run_id=run_id,
                payload_sha256="c" * 64,
                started_at=T0,
                finished_at=T0,
                scheduled_start_at=None,
                phase="live",
                capture_times={},
            )
        )
        db.flush()
        for label, scope, period in markets:
            market_id = uuid4()
            db.add(
                BookmakerMarket(
                    id=market_id,
                    event_id=event_id,
                    identity_key=str(market_id),
                    identity_basis="test",
                    label=label,
                    family="Gagnant",
                    scope=scope,
                    period=period,
                    first_seen_at=T0,
                    last_seen_at=T0,
                )
            )
            db.flush()
            ids = []
            for team in ("Alpha", "Beta"):
                selection_id = uuid4()
                ids.append(selection_id)
                db.add(
                    BookmakerSelection(
                        id=selection_id,
                        market_id=market_id,
                        identity_key=str(selection_id),
                        identity_basis="test",
                        label=team,
                        first_seen_at=T0,
                        last_seen_at=T0,
                    )
                )
            db.flush()
            for selection_id in ids:
                db.add(
                    BookmakerQuote(
                        snapshot_id=snapshot_id,
                        selection_id=selection_id,
                        observed_at=T0,
                        tab="main",
                        odds=Decimal("2.0"),
                        odds_raw="2.0",
                        disabled=False,
                    )
                )
            selection_ids.append(ids)
        db.add(snapshot(fixture.id, "loltv", "live", {"home": 0, "away": 0}, [], T0))
    assert settle_selections(engine, now=T0 + timedelta(minutes=40))["pending"] == 6
    with Session(engine) as db, db.begin():
        db.add(
            snapshot(
                fixture_id,
                "oracles-elixir",
                "finished",
                {"home": 2, "away": 0},
                ["alpha", "alpha"],
                T0 + timedelta(minutes=41),
            )
        )
    assert settle_selections(engine, now=T0 + timedelta(minutes=70))["pending"] == 6
    assert settle_selections(engine, now=T0 + timedelta(minutes=71))["void"] == 2
    with Session(engine) as db:
        assert [db.get(BookmakerSelectionResult, sid).status for sid in selection_ids[0]] == [
            "won",
            "lost",
        ]
        assert [db.get(BookmakerSelectionResult, sid).source for sid in selection_ids[0]] == [
            "oracles-elixir"
        ] * 2
        before = db.scalar(select(func.count()).select_from(BookmakerSelectionResultDecision))
    settle_selections(engine, now=T0 + timedelta(minutes=72))
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(BookmakerSelectionResultDecision)) == before
        )
    with Session(engine) as db, db.begin():
        db.add(
            snapshot(
                fixture_id,
                "loltv",
                "live",
                {"home": 1, "away": 0},
                ["alpha"],
                T0 + timedelta(minutes=72, seconds=1),
            )
        )
    assert settle_selections(engine, now=T0 + timedelta(minutes=72, seconds=2))["pending"] == 6
    with Session(engine) as db, db.begin():
        db.add(
            snapshot(
                fixture_id,
                "loltv",
                "finished",
                {"home": 2, "away": 0},
                ["alpha", "alpha"],
                T0 + timedelta(minutes=73),
            )
        )
    assert settle_selections(engine, now=T0 + timedelta(minutes=102))["pending"] == 6
    assert settle_selections(engine, now=T0 + timedelta(minutes=103))["won"] == 2
    with Session(engine) as db:
        assert [db.get(BookmakerSelectionResult, sid).source for sid in selection_ids[0]] == [
            "loltv"
        ] * 2
    with Session(engine) as db, db.begin():
        db.add(
            snapshot(
                fixture_id,
                "loltv",
                "finished",
                {"home": 1, "away": 2},
                ["alpha", "beta", "beta"],
                T0 + timedelta(minutes=104),
            )
        )
    assert settle_selections(engine, now=T0 + timedelta(minutes=135))["pending"] == 6
    with Session(engine) as db:
        assert db.get(BookmakerSelectionResult, selection_ids[0][0]).evidence["reason"] == (
            "source-conflict"
        )
    with Session(engine) as db, db.begin():
        link = db.get(BookmakerMatchLink, event_id)
        db.delete(link)
        db.get(BookmakerMatchResolution, event_id).status = "conflict"
    assert settle_selections(engine, now=T0 + timedelta(minutes=136))["pending"] == 6
    with Session(engine) as db:
        assert all(
            db.get(BookmakerSelectionResult, sid).status == "pending"
            for pair in selection_ids
            for sid in pair
        )
