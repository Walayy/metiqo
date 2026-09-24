"""The two quote phases must never borrow a missing or suspended outcome."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from metiquo_api.match_odds import match_odds
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerMarket,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    BookmakerPayload,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSelectionResult,
    BookmakerSnapshot,
    EsportMatch,
    IngestionRun,
    League,
    Team,
)
from sqlalchemy.orm import Session

NOW = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)


@pytest.mark.integration
@pytest.mark.parametrize("map_number", [None, 2])
def test_phases_suspension_missing_quote_and_retracted_link(database, map_number):
    engine, _ = database
    with Session(engine) as db, db.begin():
        db.add(League(id="cup", data={"name": "Cup"}))
        db.flush()
        db.add_all([Team(id=name, league_id="cup", data={"name": name}) for name in ("a", "b")])
        db.flush()
        fixture = EsportMatch(
            id=uuid4(),
            source="loltv",
            source_id="test",
            league_id="cup",
            home_id="a",
            away_id="b",
            starts_at=NOW,
            registered_at=NOW,
        )
        event = BookmakerEvent(
            id=uuid4(),
            bookmaker="stake",
            game="league-of-legends",
            source_id="test",
            source_url="https://example.com",
            competition_key="cup",
            participants=[],
            participant_keys=[],
            status="live",
            first_seen_at=NOW,
            last_seen_at=NOW,
            metadata_raw={},
        )
        db.add_all(
            [fixture, event, BookmakerPayload(sha256="a" * 64, parser_version="test", document={})]
        )
        db.flush()
        link = BookmakerMatchLink(
            event_id=event.id, match_id=fixture.id, method="test", evidence={}, linked_at=NOW
        )
        db.add_all(
            [
                link,
                BookmakerMatchResolution(
                    event_id=event.id,
                    status="linked",
                    last_match_id=fixture.id,
                    checked_at=NOW,
                    sha256="b" * 64,
                    evidence={},
                ),
            ]
        )
        market = BookmakerMarket(
            id=uuid4(),
            event_id=event.id,
            identity_key="winner",
            identity_basis="test",
            label=f"Vainqueur de la carte {map_number}" if map_number else "Vainqueur du match",
            scope="period" if map_number else "match",
            period=map_number,
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        db.add(market)
        db.flush()
        selections = []
        for team_id in ("b", "a"):
            selection = BookmakerSelection(
                id=uuid4(),
                market_id=market.id,
                identity_key=team_id,
                identity_basis="test",
                label=team_id,
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
            db.add(selection)
            db.flush()
            db.add(
                BookmakerSelectionResult(
                    selection_id=selection.id,
                    event_id=event.id,
                    status="pending",
                    market_kind="map_winner" if map_number else "match_winner",
                    map_number=map_number,
                    picked_team_id=team_id,
                    evidence_sha256="c" * 64,
                    evidence={},
                    decided_at=NOW,
                )
            )
            selections.append(selection)

        def capture(phase, minutes, prices):
            at = NOW + timedelta(minutes=minutes)
            event.status = "scheduled" if phase == "prematch" else "live"
            event.starts_at = NOW
            run = IngestionRun(
                id=uuid4(), source="stake", scope="test", status="succeeded", details={}
            )
            db.add(run)
            db.flush()
            snapshot = BookmakerSnapshot(
                id=uuid4(),
                event_id=event.id,
                run_id=run.id,
                payload_sha256="a" * 64,
                started_at=at,
                finished_at=at,
                phase=phase,
                scheduled_start_at=NOW,
                capture_times={},
            )
            db.add(snapshot)
            db.flush()
            for selection, price in zip(selections, prices, strict=False):
                db.add(
                    BookmakerQuote(
                        snapshot_id=snapshot.id,
                        selection_id=selection.id,
                        observed_at=at,
                        tab="main",
                        odds=Decimal(price) if price else None,
                        odds_raw=price,
                        disabled=price is None,
                    )
                )
            db.flush()

        def read(status="live"):
            return match_odds(
                db, [fixture], statuses={fixture.id: status}, now=NOW, max_age_seconds=1200
            ).get(fixture.id, [])

        capture("prematch", -60, ["1.5", "2.5"])
        capture("live", -20, ["1.3", "3.4"])
        capture("live", -10, [None, "4.2"])
        capture("live", 10, ["1.1", "8.0"])
        rows = read()
        assert [(row["phase"], row["historical"]) for row in rows] == [
            ("prematch", True),
            ("live", False),
        ]
        assert [pick["teamId"] for pick in rows[0]["selections"]] == ["a", "b"]
        assert [pick["odds"] for pick in rows[0]["selections"]] == [2.5, 1.5]
        assert [pick["odds"] for pick in rows[1]["selections"]] == [4.2, None]
        assert rows[1]["selections"][1]["suspended"] is True
        assert [pick["result"] for pick in rows[1]["selections"]] == ["pending", "pending"]
        assert rows[0]["observedAt"] == NOW - timedelta(hours=1)
        for selection in selections:
            outcome = db.get(BookmakerSelectionResult, selection.id)
            assert outcome is not None
            outcome.status = "won" if outcome.picked_team_id == "a" else "lost"
        db.flush()
        finished_rows = read("finished")
        assert all(row["historical"] for row in finished_rows)
        assert all(
            [pick["result"] for pick in row["selections"]] == ["won", "lost"]
            for row in finished_rows
        )
        event.status = "unknown"
        db.flush()
        assert all(row["historical"] for row in read())
        capture("live", -5, ["1.2"])
        assert [row["phase"] for row in read()] == ["prematch"]
        db.delete(link)
        db.flush()
        assert read() == []
