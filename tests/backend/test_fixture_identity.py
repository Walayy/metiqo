import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from metiquo_core.models import BookmakerEvent, BookmakerSnapshot
from metiquo_worker.fixture_identity import (
    Alias,
    Candidate,
    FixtureIdentity,
    ParticipantIdentity,
    TeamIdentity,
    competitions_agree,
    resolve_fixture,
)
from metiquo_worker.oracle_match_sync import oracle_time_agrees
from metiquo_worker.reconciliation import AliasDocument, fixture_from_event

AT = datetime(2026, 9, 24, 9, tzinfo=UTC)
HOME = TeamIdentity("a", ("Alpha Academy",), {"loltv": ("alpha",)})
AWAY = TeamIdentity("b", ("Beta",), {"loltv": ("beta",)})


def fixture(**kwargs):
    return replace(
        FixtureIdentity(
            uuid4(),
            "stake",
            "123",
            "league-of-legends",
            "cup",
            "Cup 2026 Summer Playoffs",
            AT,
            (ParticipantIdentity(0, "Alpha Academy"), ParticipantIdentity(1, "Beta")),
        ),
        **kwargs,
    )


def candidate(**kwargs):
    return replace(
        Candidate(
            uuid4(),
            AT,
            "Cup Summer 2026",
            HOME,
            AWAY,
            ({"provider": "loltv", "sourceId": "event"},),
        ),
        **kwargs,
    )


def alias(**kwargs):
    return replace(
        Alias(
            "reviewed",
            "stake",
            "league-of-legends",
            "A Acad",
            "cup",
            "loltv",
            "alpha",
            AT - timedelta(days=1),
            AT + timedelta(days=1),
        ),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (
            "2026 World Star Challengers Invitational",
            "World Star Challengers Invitational 2026",
            True,
        ),
        ("LCS 2026 Summer Playoffs", "LCS Summer 2026", True),
        ("CBLOL 2026 Split 2 Playoffs", "CBLOL Split 2 2026", True),
        ("EMEA Masters 2026 Summer LCQ", "EMEA Masters Summer 2026", True),
        ("LCS 2027 Promotion", "LCS Summer 2026", False),
        ("LCS 2027 Promotion", "LCS 2026 Promotion", False),
        ("LCS 2026 Summer Playoffs", "LCS 2026 Summer Regular Season", False),
        ("LCS 2026 Summer", "LCS 2026 Spring", False),
        ("LCK CL", "LCK", False),
        ("CBLOL Split 2", "CBLOL Split 1", False),
        ("Cup Group A", "Cup Group B", False),
        ("Tyler1 All Stars Season 2026 Week 14", "Tyler1 All Stars Season 2026 Week 15", False),
    ],
)
def test_competition_identity_keeps_editions_and_known_phases(left, right, expected):
    assert competitions_agree(left, right) is expected


def test_reversed_source_order_is_preserved_as_explicit_team_mapping():
    value = fixture(
        participants=(ParticipantIdentity(0, "Beta"), ParticipantIdentity(1, "Alpha Academy"))
    )
    target = candidate()
    decision = resolve_fixture(value, [target])
    assert decision.match_id == target.id
    assert [p["teamId"] for p in decision.evidence["participants"]] == ["b", "a"]


@pytest.mark.parametrize(
    "name",
    [
        "Alpha",
        "Alpha Junior",
        "Alpha B",
        "Alpha II",
        "Alpha Challengers",
        "Alfa Academy",
        "TBD",
        "Winner Alpha Academy",
    ],
)
def test_parent_qualifier_typo_and_placeholder_never_force_identity(name):
    value = fixture(participants=(ParticipantIdentity(0, name), ParticipantIdentity(1, "Beta")))
    assert resolve_fixture(value, [candidate()]).status == "pending"


def test_generic_words_case_and_accents_do_not_require_team_specific_rules():
    value = fixture(
        participants=(
            ParticipantIdentity(0, "ALPHÁ Academy esports"),
            ParticipantIdentity(1, "Team Beta"),
        )
    )
    assert resolve_fixture(value, [candidate()]).status == "linked"


def test_all_plausible_rematches_block_even_if_one_is_exactly_on_time():
    first, second = candidate(), candidate(starts_at=AT + timedelta(minutes=25))
    a = resolve_fixture(fixture(), [first, second])
    b = resolve_fixture(fixture(), [second, first])
    assert a.status == b.status == "ambiguous" and a.match_id is None
    assert a.evidence["candidates"] == b.evidence["candidates"]


def test_two_orientations_of_homonymous_teams_are_ambiguous():
    target = candidate(away=replace(AWAY, names=HOME.names))
    value = fixture(
        participants=(
            ParticipantIdentity(0, "Alpha Academy"),
            ParticipantIdentity(1, "Alpha Academy"),
        )
    )
    assert resolve_fixture(value, [target]).status == "ambiguous"


def test_future_arrival_and_new_bookmaker_ids_do_not_create_fake_matches():
    value = fixture(starts_at=AT + timedelta(days=60))
    assert resolve_fixture(value, [candidate()]).status == "pending"
    target = candidate(starts_at=value.starts_at)
    assert resolve_fixture(value, [target]).match_id == target.id
    assert (
        resolve_fixture(replace(value, id=uuid4(), source_id="different"), [target]).match_id
        == target.id
    )


@pytest.mark.parametrize("at", [None, AT.replace(tzinfo=None)])
def test_unknown_timezone_or_missing_time_cannot_link(at):
    assert (
        resolve_fixture(fixture(starts_at=at), [candidate()]).evidence["reason"]
        == "missing-verified-time"
    )


def test_utc_offsets_are_compared_as_instants():
    value = fixture(starts_at=AT.astimezone(timezone(timedelta(hours=9))))
    assert resolve_fixture(value, [candidate()]).status == "linked"


def test_reviewed_alias_is_scoped_and_does_not_generalize_academies():
    value = fixture(participants=(ParticipantIdentity(0, "A Acad"), ParticipantIdentity(1, "Beta")))
    assert resolve_fixture(value, [candidate()], (alias(),)).status == "linked"
    assert (
        resolve_fixture(replace(value, competition_key="other"), [candidate()], (alias(),)).status
        == "pending"
    )
    assert resolve_fixture(value, [candidate()], (alias(valid_until=AT),)).status == "pending"
    assert (
        resolve_fixture(value, [candidate()], (alias(target_id="another-team"),)).status
        == "pending"
    )
    assert (
        resolve_fixture(value, [candidate()], (alias(), alias(target_id="other"))).status
        == "conflict"
    )


def test_source_ids_are_namespaced_and_contradictions_block_name_fallback():
    value = fixture(
        participants=(
            ParticipantIdentity(0, "Alpha Academy", "wrong"),
            ParticipantIdentity(1, "Beta"),
        )
    )
    target = candidate(home=replace(HOME, source_ids={"stake": ("right",)}))
    assert resolve_fixture(value, [target]).status == "pending"
    assert resolve_fixture(value, [candidate()]).status == "linked"  # LoLTV IDs are unrelated.


def test_changed_link_is_suspended_instead_of_silently_moved():
    first, other = candidate(), candidate()
    assert resolve_fixture(fixture(), [other], previous_match_id=first.id).status == "conflict"
    assert resolve_fixture(fixture(), [first], previous_match_id=first.id).status == "linked"
    assert resolve_fixture(fixture(), [], previous_match_id=first.id).status == "conflict"


def test_raw_oracle_map_time_does_not_match_a_series_the_following_day():
    assert oracle_time_agrees(AT + timedelta(hours=4), AT)
    assert not oracle_time_agrees(AT, AT + timedelta(hours=4))
    assert not oracle_time_agrees(AT + timedelta(hours=20), AT)


def test_replay_all_twenty_audited_stake_events():
    folder = Path(__file__).resolve().parents[2] / "docs/audits/matching/2026-09-23"
    corpus = json.loads((folder / "before.json").read_text(encoding="utf-8"))
    captures = {
        s["event_id"]: s
        for s in json.loads((folder / "last-prematch-evidence.json").read_text(encoding="utf-8"))
    }
    reviewed = AliasDocument.model_validate_json(
        (folder / "reviewed-aliases.json").read_text(encoding="utf-8")
    )
    aliases = tuple(
        Alias(str(i), **r.model_dump(exclude={"evidence"})) for i, r in enumerate(reviewed.aliases)
    )
    teams = {
        t["id"]: TeamIdentity(
            t["id"],
            tuple([t["data"]["name"], *t["data"].get("aliases", [])]),
            {k: tuple(v) for k, v in t["data"].get("sourceIds", {}).items()},
        )
        for t in corpus["teams"]
    }
    links = {s["match_id"]: s for s in corpus["links"] if s["provider"] == "loltv"}
    candidates = [
        Candidate(
            UUID(m["id"]),
            datetime.fromisoformat(m["starts_at"]),
            links[m["id"]]["source_names"]["competition"],
            teams[m["home_id"]],
            teams[m["away_id"]],
            ({"provider": "loltv", "sourceId": m["source_id"]},),
        )
        for m in corpus["matches"]
    ]
    expected = {
        "847754": "6138fb06a3c08bafd70f0210",
        "847755": "83efeaaa73bcff2394cf521d",
        "847756": "91b1075f1b483efeaaa73bcf",
        "847757": "1b1075f1b483efeaaa73bcff",
        "849089": "b1075f1b483efeaaa73bcff2",
        "849090": "75f1b483efeaaa73bcff2394",
        "849091": "b483efeaaa73bcff2394cf52",
        "849092": "5f1b483efeaaa73bcff2394c",
        "845833": "13bf4b7b04c9ebf76e000aad",
        "845961": "7202e0e8a4a6fd3a0f689018",
        "836114": "07202e0e8a4a6fd3a0f68901",
        "848607": "b3b4d5fd86e1c3c88ecd1f77",
    }
    assert len(corpus["events"]) == 20
    for raw in corpus["events"]:
        values = {
            **raw,
            "id": UUID(raw["id"]),
            "starts_at": datetime.fromisoformat(raw["starts_at"]) if raw["starts_at"] else None,
        }
        event = BookmakerEvent(**values)
        capture = captures.get(raw["id"])
        snapshot = (
            BookmakerSnapshot(
                id=UUID(capture["snapshot_id"]),
                payload_sha256=capture["payload_sha256"],
                finished_at=datetime.fromisoformat(capture["finished_at"]),
            )
            if capture
            else None
        )
        identity = fixture_from_event(event, snapshot, capture["metadata"] if capture else None)
        decision = resolve_fixture(identity, candidates, aliases)
        if raw["source_id"] in expected:
            assert decision.status == "linked", (raw["source_id"], decision.evidence)
            assert (
                next(c for c in candidates if c.id == decision.match_id).sources[0]["sourceId"]
                == expected[raw["source_id"]]
            )
        else:
            assert decision.status == "pending", raw["source_id"]
