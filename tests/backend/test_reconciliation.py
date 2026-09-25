from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerEventObservation,
    BookmakerMatchDecision,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    EsportMatch,
    League,
    MatchIdentityAlias,
    MatchSourceLink,
    Team,
)
from metiquo_worker.loltv_publication import _publish_events
from metiquo_worker.reconciliation import reconcile_matches, revoke_alias
from metiquo_worker.sources.loltv import LoltvEvent
from metiquo_worker.stake_storage import remember_event, remember_events
from metiquo_worker.stake_types import EventMetadata, Participant
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def metadata(**updates):
    at = datetime.now(UTC)
    return EventMetadata(
        game="league-of-legends",
        source_id="123",
        url="https://stake.bet/fr/sports/league-of-legends/world/cup/123-alpha-beta",
        competition_key="cup",
        competition_name="Cup 2026 Summer Playoffs",
        participants=[
            Participant(name="Alpha Academy", position=0),
            Participant(name="Beta", position=1),
        ],
        starts_at=at + timedelta(days=60),
        status="scheduled",
        observed_at=at,
    ).model_copy(update=updates)


def seed_match(engine, value, *, provider="loltv", source_id="loltv-123"):
    with Session(engine) as db, db.begin():
        if db.get(League, "cup") is None:
            db.add(League(id="cup", data={"name": "Cup 2026 Summer", "slug": "cup"}))
            db.flush()
            db.add_all(
                [
                    Team(
                        id="alpha",
                        league_id="cup",
                        data={"name": "Alpha Academy", "sourceIds": {"loltv": ["alpha"]}},
                    ),
                    Team(
                        id="beta",
                        league_id="cup",
                        data={"name": "Beta", "sourceIds": {"loltv": ["beta"]}},
                    ),
                ]
            )
            db.flush()
        match_id = uuid4()
        db.add(
            EsportMatch(
                id=match_id,
                source=provider,
                source_id=source_id,
                league_id="cup",
                home_id="alpha",
                away_id="beta",
                starts_at=value.starts_at,
                registered_at=value.observed_at,
                format="BO3",
            )
        )
        db.flush()
        db.add(
            MatchSourceLink(
                match_id=match_id,
                provider=provider,
                source_id=source_id,
                source_url="https://loltv.gg/matches/123",
                source_names={"competition": "Cup Summer 2026"},
                first_seen_at=value.observed_at,
                last_seen_at=value.observed_at,
            )
        )
    return match_id


def test_future_arrival_dry_run_idempotence_and_journal(database):
    engine, _ = database
    value = metadata()
    remember_event(engine, value)
    with Session(engine) as db:
        assert db.get(BookmakerMatchResolution, value.id).status == "pending"
        assert db.scalar(select(func.count()).select_from(EsportMatch)) == 0
    target = seed_match(engine, value)
    assert reconcile_matches(engine, dry_run=True)["counts"] == {"linked": 1}
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id) is None
    assert reconcile_matches(engine)["counts"] == {"linked": 1}
    reconcile_matches(engine)
    remember_event(engine, value)
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id).match_id == target
        assert db.scalar(select(func.count()).select_from(BookmakerMatchDecision)) == 2
        assert db.scalar(select(func.count()).select_from(BookmakerEventObservation)) == 1


def test_loLtv_publication_resolves_waiting_event_in_same_transaction(database):
    engine, _ = database
    value = metadata()
    remember_event(engine, value)
    event = LoltvEvent(
        source_id="late-event",
        url="https://loltv.gg/matches/late-event",
        home_name="Alpha Academy",
        away_name="Beta",
        competition="Cup Summer 2026",
        competition_source_id="cup",
        competition_slug="cup",
        home_source_id="alpha",
        away_source_id="beta",
        home_image="",
        away_image="",
        competition_image="",
        starts_at=value.starts_at,
        status="scheduled",
        best_of=3,
        home_score=None,
        away_score=None,
        payload={},
    )
    assert _publish_events(engine, [event]) == (1, 1)
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id) is not None
        assert db.get(BookmakerMatchResolution, value.id).status == "linked"


def test_ambiguity_invalidates_existing_link_and_retains_history(database):
    engine, _ = database
    value = metadata()
    first = seed_match(engine, value)
    remember_event(engine, value)
    second = seed_match(engine, value, source_id="rematch")
    assert first != second
    assert reconcile_matches(engine)["counts"] == {"conflict": 1}
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id) is None
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.last_match_id == first
        assert len(state.evidence["candidates"]) == 2
        assert db.scalar(select(func.count()).select_from(BookmakerMatchDecision)) == 2


def test_observation_A_B_A_is_preserved_and_old_observations_cannot_rewind_state(database):
    engine, _ = database
    value = metadata()
    for i, competition in enumerate(["Cup", "Other", "Cup"]):
        remember_event(
            engine,
            value.model_copy(
                update={
                    "competition_name": competition,
                    "observed_at": value.observed_at + timedelta(seconds=i),
                }
            ),
        )
    remember_event(
        engine,
        value.model_copy(
            update={"competition_name": "Old", "observed_at": value.observed_at - timedelta(days=1)}
        ),
    )
    with Session(engine) as db:
        observations = list(
            db.scalars(select(BookmakerEventObservation).order_by(BookmakerEventObservation.id))
        )
        assert [o.payload["competition_name"] for o in observations] == [
            "Cup",
            "Other",
            "Cup",
            "Old",
        ]
        assert observations[0].sha256 == observations[2].sha256
        assert db.get(BookmakerEvent, value.id).competition_name == "Cup"


def test_partial_listing_keeps_verified_identity_and_stops_collection(database):
    engine, _ = database
    value = metadata()
    match_id = seed_match(engine, value)
    remember_event(engine, value)
    partial = value.model_copy(
        update={
            "starts_at": None,
            "status": "live",
            "participants": [],
            "competition_name": None,
            "observed_at": value.observed_at + timedelta(seconds=1),
        }
    )
    remember_event(engine, partial, stop_reason="live_listing")
    with Session(engine) as db:
        event = db.get(BookmakerEvent, value.id)
        assert event.starts_at == value.starts_at and len(event.participants) == 2
        assert event.stopped_at is not None
        assert db.get(BookmakerMatchLink, value.id).match_id == match_id
        assert db.scalar(select(func.count()).select_from(BookmakerEventObservation)) == 2


def test_changed_schedule_keeps_a_proven_link_and_journals_the_correction(database):
    engine, _ = database
    value = metadata()
    first = seed_match(engine, value)
    remember_event(engine, value)
    changed = value.model_copy(
        update={
            "starts_at": value.starts_at + timedelta(days=1),
            "observed_at": value.observed_at + timedelta(seconds=1),
        }
    )
    remember_event(engine, changed)
    with Session(engine) as db:
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.status == "linked"
        assert state.evidence["scheduleBasis"] == "observed-schedule"
        assert db.get(BookmakerMatchLink, value.id).match_id == first
    remember_event(
        engine, value.model_copy(update={"observed_at": value.observed_at + timedelta(seconds=2)})
    )
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id).match_id == first
        decisions = list(
            db.scalars(select(BookmakerMatchDecision).order_by(BookmakerMatchDecision.id))
        )
        assert [d.evidence["status"] for d in decisions] == ["linked", "linked", "linked"]


def test_historical_schedule_links_after_late_sport_publication(database):
    engine, _ = database
    value = metadata()
    remember_event(engine, value)
    changed = value.model_copy(
        update={
            "starts_at": value.starts_at + timedelta(days=1),
            "observed_at": value.observed_at + timedelta(seconds=1),
        }
    )
    remember_event(engine, changed)
    first = seed_match(engine, value)
    assert reconcile_matches(engine)["counts"] == {"linked": 1}
    with Session(engine) as db:
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.evidence["scheduleBasis"] == "observed-schedule"
        assert state.evidence["fixture"]["scheduleObservations"]
        assert db.get(BookmakerMatchLink, value.id).match_id == first


def test_a_sporting_schedule_shift_keeps_the_same_match_id(database):
    engine, _ = database
    value = metadata()
    first = seed_match(engine, value)
    remember_event(engine, value)
    with Session(engine) as db, db.begin():
        db.get(EsportMatch, first).starts_at = value.starts_at + timedelta(days=1)
    assert reconcile_matches(engine)["counts"] == {"linked": 1}
    with Session(engine) as db:
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.evidence["scheduleBasis"] == "retained-identity"
        assert db.get(BookmakerMatchLink, value.id).match_id == first


def test_a_new_rematch_at_the_shifted_time_suspends_the_retained_link(database):
    engine, _ = database
    value = metadata()
    first = seed_match(engine, value)
    remember_event(engine, value)
    changed = value.model_copy(
        update={
            "starts_at": value.starts_at + timedelta(days=1),
            "observed_at": value.observed_at + timedelta(seconds=1),
        }
    )
    remember_event(engine, changed)
    second = seed_match(engine, changed, source_id="rematch")
    assert first != second
    assert reconcile_matches(engine)["counts"] == {"conflict": 1}
    with Session(engine) as db:
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.last_match_id == first
        assert state.evidence["reason"] == "multiple-plausible-identities"
        assert db.get(BookmakerMatchLink, value.id) is None


def test_partial_listing_with_a_changed_opponent_suspends_the_retained_identity(database):
    engine, _ = database
    value = metadata()
    seed_match(engine, value)
    remember_event(engine, value)
    partial = value.model_copy(
        update={
            "starts_at": None,
            "observed_at": value.observed_at + timedelta(seconds=1),
            "participants": [
                Participant(name="Alpha Academy", position=0),
                Participant(name="Different opponent", position=1),
            ],
        }
    )
    remember_event(engine, partial)
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id) is None
        state = db.get(BookmakerMatchResolution, value.id)
        assert state.status == "conflict"
        assert state.evidence["reason"] == "contradictory-latest-reading"
        assert db.get(BookmakerEvent, value.id).participants[1]["name"] == "Beta"


def test_revoke_alias_is_atomic_and_does_not_fall_back_to_the_old_link(database):
    engine, _ = database
    value = metadata(
        participants=[Participant(name="A Acad", position=0), Participant(name="Beta", position=1)]
    )
    seed_match(engine, value)
    with Session(engine) as db, db.begin():
        db.add(
            MatchIdentityAlias(
                id="reviewed",
                provider="stake",
                game=value.game,
                name="A Acad",
                competition_key="cup",
                target_provider="loltv",
                target_id="alpha",
                valid_from=value.starts_at - timedelta(days=1),
                valid_until=value.starts_at + timedelta(days=1),
                evidence={"sources": ["audit"], "reason": "reviewed"},
                active=True,
            )
        )
    remember_event(engine, value)
    assert revoke_alias(engine, "reviewed")["counts"] == {"conflict": 1}
    with Session(engine) as db:
        assert db.get(BookmakerMatchLink, value.id) is None


def test_restored_links_are_journaled_before_revalidation(database):
    engine, _ = database
    value = metadata()
    target = seed_match(engine, value)
    with Session(engine) as db, db.begin():
        db.add(
            BookmakerEvent(
                id=value.id,
                bookmaker="stake",
                game=value.game,
                source_id=value.source_id,
                source_url=value.url,
                competition_key=value.competition_key,
                competition_name=value.competition_name,
                participants=[p.model_dump() for p in value.participants],
                participant_keys=[],
                starts_at=value.starts_at,
                status=value.status,
                first_seen_at=value.observed_at,
                last_seen_at=value.observed_at,
                metadata_raw={},
            )
        )
        db.flush()
        db.add(
            BookmakerMatchLink(
                event_id=value.id,
                match_id=target,
                method="retired",
                evidence={"old": True},
                linked_at=value.observed_at,
            )
        )
    reconcile_matches(engine)
    with Session(engine) as db:
        rows = list(db.scalars(select(BookmakerMatchDecision).order_by(BookmakerMatchDecision.id)))
        assert rows[0].evidence["status"] == "legacy" and rows[0].evidence["evidence"] == {
            "old": True
        }
        assert rows[1].evidence["status"] == "linked"


def test_concurrent_source_writes_are_serialized_without_duplicate_decisions(database):
    engine, _ = database
    value = metadata()
    seed_match(engine, value)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: remember_event(engine, value), range(4)))
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BookmakerMatchLink)) == 1
        assert db.scalar(select(func.count()).select_from(BookmakerMatchDecision)) == 1
        assert db.scalar(select(func.count()).select_from(BookmakerEventObservation)) == 1


def test_discovery_records_every_event_without_market_captures(database):
    engine, _ = database
    values = [metadata(source_id=str(i), starts_at=None) for i in range(5)]
    remember_events(engine, values)
    assert reconcile_matches(engine)["counts"] == {"pending": 5}
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BookmakerEvent)) == 5


@pytest.mark.parametrize("table", ["bookmaker_event_observations", "bookmaker_match_decisions"])
def test_history_is_immutable_in_postgresql(database, table):
    engine, _ = database
    remember_event(engine, metadata())
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as db:
        db.execute(text(f"DELETE FROM {table}"))


def test_worker_rights_and_api_read_only_matching_status(database):
    engine, _ = database
    value = metadata()
    seed_match(engine, value)
    with engine.connect() as connection:
        if not connection.scalar(
            text("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname='metiquo_worker')")
        ):
            pytest.skip("Stack SQL roles unavailable")
        # Fresh isolated databases don't run postgres-init.sh. Supply only the
        # pre-existing sporting reads; new reconciliation grants come from 0015.
        connection.execute(text("GRANT SELECT ON teams, leagues, matches TO metiquo_worker"))
        connection.commit()
        connection.execute(text("SET ROLE metiquo_worker"))
        with Session(connection) as db, db.begin():
            from metiquo_worker.reconciliation import reconcile_in_session

            reconcile_in_session(db)
        connection.rollback()
    remember_event(engine, value)
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE metiquo_api"))
        assert connection.scalar(text("SELECT status FROM bookmaker_matching_status")) == "linked"
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE metiquo_api"))
        connection.execute(text("DELETE FROM bookmaker_match_links"))
