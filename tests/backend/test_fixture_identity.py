import json
import runpy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from metiquo_core.models import BookmakerEvent, BookmakerEventObservation, BookmakerSnapshot
from metiquo_worker.fixture_identity import (
    Alias,
    Candidate,
    CompetitionAlias,
    FixtureIdentity,
    ParticipantIdentity,
    TeamIdentity,
    competitions_agree,
    resolve_fixture,
)
from metiquo_worker.oracle_match_sync import oracle_time_agrees
from metiquo_worker.reconciliation import (
    AliasDocument,
    fixture_from_event,
    with_schedule_observations,
)

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


def competition_alias(**kwargs):
    return replace(
        CompetitionAlias(
            "tournament-reviewed",
            "stake",
            "league-of-legends",
            "EM 2026 Summer Swiss",
            "emea-swiss",
            "loltv",
            "emea-masters-summer-2026",
            AT - timedelta(days=1),
            AT + timedelta(days=1),
        ),
        **kwargs,
    )


def test_reviewed_competition_identity_is_reusable_but_source_scoped():
    value = fixture(competition="EM 2026 Summer Swiss", competition_key="emea-swiss")
    target = candidate(
        competition="EMEA Masters Summer 2026",
        sources=(
            {"provider": "loltv", "names": {"competitionSourceId": "emea-masters-summer-2026"}},
        ),
    )
    assert resolve_fixture(value, [target]).status == "pending"
    linked = resolve_fixture(value, [target], competition_aliases=(competition_alias(),))
    assert linked.match_id == target.id
    assert linked.evidence["candidates"][0]["competitionProof"]["basis"] == "reviewed-alias"
    assert (
        resolve_fixture(
            replace(value, competition_key="another-tournament"),
            [target],
            competition_aliases=(competition_alias(),),
        ).status
        == "pending"
    )
    assert (
        resolve_fixture(
            value,
            [target],
            competition_aliases=(competition_alias(valid_until=AT),),
        ).status
        == "pending"
    )
    assert (
        resolve_fixture(
            value,
            [
                replace(
                    target,
                    sources=({"provider": "loltv", "names": {"competitionSourceId": "different"}},),
                )
            ],
            competition_aliases=(competition_alias(),),
        ).status
        == "pending"
    )


def test_conflicting_competition_aliases_withdraw_link():
    value = fixture(competition="EM 2026 Summer Swiss", competition_key="emea-swiss")
    target = candidate(
        competition="EMEA Masters Summer 2026",
        sources=(
            {"provider": "loltv", "names": {"competitionSourceId": "emea-masters-summer-2026"}},
        ),
    )
    decision = resolve_fixture(
        value,
        [target],
        competition_aliases=(competition_alias(), competition_alias(id="other", target_id="rival")),
    )
    assert decision.status == "conflict"
    assert decision.evidence["reason"] == "contradictory-competition-aliases"


def test_replay_all_eleven_captured_emea_swiss_pairs():
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "migrations/versions/0018_scoped_competition_aliases.py"
        )
    )
    seeded = dict(migration["TEAM_ALIASES"])
    reviewed_teams = tuple(
        Alias(
            name,
            "stake",
            "league-of-legends",
            name,
            migration["STAKE_KEY"],
            "loltv",
            target_id,
            datetime(2026, 9, 25, tzinfo=UTC),
            datetime(2026, 11, 1, tzinfo=UTC),
        )
        for name, target_id in seeded.items()
    )
    tournament = CompetitionAlias(
        "emea-reviewed",
        "stake",
        "league-of-legends",
        "EM 2026 Summer Swiss",
        migration["STAKE_KEY"],
        "loltv",
        "emea-masters-summer-2026",
        datetime(2026, 9, 25, tzinfo=UTC),
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    # Stake event IDs and source labels were read from the retained 25 Sep captures;
    # the LoLTV pairs and starts were independently read from match_source_links.
    observations = (
        (
            851558,
            "BIG",
            "Frites Esports Club",
            "Berlin International Gaming",
            "Frites Esports Club",
            16,
        ),
        (851559, "JSK Esports", "FC Barcelona", "JSK Esports", "Barça eSports", 16),
        (851560, "Colossal Gaming", "Skillcamp", "Skillcamp", "Colossal Gaming", 16),
        (851561, "Valerion", "LODIS", "Valerion", "LODIS", 16),
        (
            851562,
            "Bushido Wildcats",
            "Senshi eSports (Benelux Team)",
            "Senshi eSports",
            "Bushido Wildcats",
            17,
        ),
        (851563, "Hmble", "UCAM Esports", "UCAM Esports Club", "HMBLE", 17),
        (851564, "G2 NORD", "Forsaken", "Forsaken", "G2 NORD", 18),
        (851565, "Team Heretics Academy", "eSuba", "Team Heretics Academy", "eSuba", 18),
        (851566, "Karmine Corp Blue", "White Dragons", "Karmine Corp Blue", "White Dragons", 18),
        (851569, "Team Phantasma", "SU Esports", "Team Phantasma", "SU Esports", 18),
        (851570, "Anubis Gaming", "Team Secret Club", "Anubis Gaming", "The Secret Club", 19),
    )
    target_ids = {
        "Berlin International Gaming": seeded["BIG"],
        "Barça eSports": seeded["FC Barcelona"],
        "Senshi eSports": seeded["Senshi eSports (Benelux Team)"],
        "The Secret Club": seeded["Team Secret Club"],
    }
    candidates = []
    for event_id, _, _, lol_a, lol_b, hour in observations:
        starts = datetime(2026, 9, 26, hour, tzinfo=UTC)

        def team(name):
            source_id = target_ids.get(name, name)
            return TeamIdentity(name, (name,), {"loltv": (source_id,)})

        candidates.append(
            Candidate(
                uuid5(NAMESPACE_URL, f"loltv:2026-09-26:{event_id}"),
                starts,
                "EMEA Masters Summer 2026",
                team(lol_a),
                team(lol_b),
                (
                    {
                        "provider": "loltv",
                        "names": {"competitionSourceId": "emea-masters-summer-2026"},
                    },
                ),
            )
        )
    for index, (event_id, stake_a, stake_b, _, _, hour) in enumerate(observations):
        fixture_identity = FixtureIdentity(
            uuid5(NAMESPACE_URL, f"stake:{event_id}"),
            "stake",
            str(event_id),
            "league-of-legends",
            migration["STAKE_KEY"],
            "EM 2026 Summer Swiss",
            datetime(2026, 9, 26, hour, tzinfo=UTC),
            (ParticipantIdentity(0, stake_a), ParticipantIdentity(1, stake_b)),
        )
        decision = resolve_fixture(
            fixture_identity, candidates, reviewed_teams, competition_aliases=(tournament,)
        )
        assert decision.match_id == candidates[index].id, (event_id, decision.evidence)


@pytest.mark.parametrize(
    (
        "provider_name",
        "target_name",
        "opponent",
        "competition_key",
        "competition",
        "target_id",
        "at",
    ),
    [
        (
            "Keyd Academy",
            "Vivo Keyd Stars Academy",
            "FENNEL",
            "/fr/sports/league-of-legends/international-1/2026-world-star-challengers-invitational-t8",
            "2026 World Star Challengers Invitational",
            "clpz8g6bv01fbakxlifhqtdwk",
            datetime(2026, 9, 25, 7, tzinfo=UTC),
        ),
        (
            "LOS",
            "LØS",
            "LOUD",
            "/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5",
            "CBLOL 2026 Split 2 Playoffs",
            "clpz8g6da01kxakxl4k32fiwd",
            datetime(2026, 9, 27, 16, tzinfo=UTC),
        ),
    ],
)
def test_current_other_tournaments_use_only_their_reviewed_team_alias(
    provider_name, target_name, opponent, competition_key, competition, target_id, at
):
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "migrations/versions/0018_scoped_competition_aliases.py"
        )
    )
    record = next(
        record for record in migration["_team_records"]() if record["name"] == provider_name
    )
    reviewed = Alias(
        record["id"],
        record["provider"],
        record["game"],
        record["name"],
        record["competition_key"],
        record["target_provider"],
        record["target_id"],
        record["valid_from"],
        record["valid_until"],
    )
    assert reviewed.target_id == target_id
    fixture_identity = fixture(
        competition_key=competition_key,
        competition=competition,
        starts_at=at,
        participants=(ParticipantIdentity(0, opponent), ParticipantIdentity(1, provider_name)),
    )
    target = candidate(
        starts_at=at,
        competition=competition,
        home=TeamIdentity("opponent", (opponent,)),
        away=TeamIdentity("aliased", (target_name,), {"loltv": (target_id,)}),
    )
    assert resolve_fixture(fixture_identity, [target]).status == "pending"
    assert resolve_fixture(fixture_identity, [target], (reviewed,)).match_id == target.id
    assert (
        resolve_fixture(
            replace(fixture_identity, competition_key="another-tournament"), [target], (reviewed,)
        ).status
        == "pending"
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


def test_a_proven_link_survives_a_day_shift_without_weakening_first_links():
    target = candidate()
    shifted = fixture(starts_at=AT + timedelta(days=1))
    assert resolve_fixture(shifted, [target]).status == "pending"
    decision = resolve_fixture(shifted, [target], previous_match_id=target.id)
    assert decision.status == "linked" and decision.match_id == target.id
    assert decision.evidence["scheduleBasis"] == "retained-identity"
    assert decision.evidence["candidates"][0]["deltaSeconds"] == 86400


def test_an_old_verified_schedule_can_establish_a_link_after_a_shift():
    target = candidate()
    shifted = fixture(starts_at=AT + timedelta(days=1), verified_starts=(AT,))
    decision = resolve_fixture(shifted, [target])
    assert decision.status == "linked" and decision.match_id == target.id
    assert decision.evidence["scheduleBasis"] == "observed-schedule"


def test_only_prior_observations_of_the_same_fixture_can_anchor_a_shift():
    shifted = fixture(
        starts_at=AT + timedelta(days=1),
        participants=(
            ParticipantIdentity(0, "Alpha Academy", "stake-alpha"),
            ParticipantIdentity(1, "Beta", "stake-beta"),
        ),
    )
    base_payload = {
        "starts_at": AT.isoformat(),
        "competition_key": "cup",
        "competition_name": "Cup 2026 Summer Playoffs",
        "participants": [
            {"position": 0, "name": "Alpha Academy", "source_id": "stake-alpha"},
            {"position": 1, "name": "Beta", "source_id": "stake-beta"},
        ],
    }

    def observation(index, payload):
        return BookmakerEventObservation(
            id=index,
            event_id=shifted.id,
            observed_at=AT + timedelta(minutes=index),
            sha256=str(index) * 64,
            payload=payload,
        )

    unrelated = [
        observation(1, {**base_payload, "competition_name": "Other 2026 Summer"}),
        observation(
            2,
            {
                **base_payload,
                "participants": [base_payload["participants"][0], {"position": 1, "name": "Gamma"}],
            },
        ),
        observation(
            3,
            {
                **base_payload,
                "participants": [
                    {"position": 0, "name": "Alpha Academy", "source_id": "different"},
                    base_payload["participants"][1],
                ],
            },
        ),
        observation(4, {**base_payload, "starts_at": "2026-09-24T09:00:00"}),
    ]
    assert not with_schedule_observations(shifted, unrelated).verified_starts
    verified = with_schedule_observations(shifted, [*unrelated, observation(5, base_payload)])
    assert verified.verified_starts == (AT,)
    assert [item["id"] for item in verified.evidence["scheduleObservations"]] == [5]
    assert resolve_fixture(verified, [candidate()]).status == "linked"


def test_schedule_basis_belongs_to_the_selected_candidate():
    target = candidate(id=UUID(int=1))
    irrelevant = candidate(
        id=UUID(int=2),
        starts_at=AT + timedelta(days=1),
        away=replace(AWAY, names=("Other",)),
    )
    decision = resolve_fixture(fixture(), [irrelevant, target], previous_match_id=target.id)
    assert decision.match_id == target.id
    assert decision.evidence["scheduleBasis"] == "current-schedule"


def test_reviewed_alias_remains_scoped_to_the_observed_schedule_after_a_shift():
    shifted = fixture(
        starts_at=AT + timedelta(days=1),
        verified_starts=(AT,),
        participants=(ParticipantIdentity(0, "A Acad"), ParticipantIdentity(1, "Beta")),
    )
    decision = resolve_fixture(shifted, [candidate()], (alias(),))
    assert decision.status == "linked"
    assert decision.evidence["scheduleBasis"] == "observed-schedule"


def test_a_rematch_at_the_new_time_blocks_an_old_link_without_reassignment():
    original = candidate()
    rematch = candidate(starts_at=AT + timedelta(days=1))
    shifted = fixture(starts_at=rematch.starts_at, verified_starts=(AT,))
    decision = resolve_fixture(shifted, [original, rematch], previous_match_id=original.id)
    assert decision.status == "conflict" and decision.match_id is None
    assert decision.evidence["reason"] == "multiple-plausible-identities"
    assert len(decision.evidence["candidates"]) == 2


def test_an_old_transient_schedule_does_not_poison_a_corrected_link():
    original = candidate()
    rematch = candidate(starts_at=AT + timedelta(days=1))
    corrected = fixture(starts_at=AT, verified_starts=(rematch.starts_at,))
    decision = resolve_fixture(corrected, [original, rematch], previous_match_id=original.id)
    assert decision.status == "linked" and decision.match_id == original.id
    assert len(decision.evidence["candidates"]) == 1


def test_a_changed_opponent_still_blocks_the_retained_link_after_a_day_shift():
    original = candidate()
    changed = fixture(
        starts_at=AT + timedelta(days=1),
        participants=(ParticipantIdentity(0, "Alpha Academy"), ParticipantIdentity(1, "Gamma")),
    )
    decision = resolve_fixture(changed, [original], previous_match_id=original.id)
    assert decision.status == "conflict" and decision.match_id is None


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
