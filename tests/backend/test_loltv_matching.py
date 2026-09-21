from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from metiquo_core.models import EsportMatch, League, OracleRow, Team
from metiquo_worker.loltv_publication import (
    _competition_base_name,
    _competition_brand,
    _rendered_maps,
    _save_event,
)
from metiquo_worker.matching import MatchIdentity, normalize_name, resolve_match, resolve_team
from metiquo_worker.oracle_match_sync import _map_for_game
from metiquo_worker.sources.loltv import (
    LoltvEvent,
)
from sqlalchemy.orm import Session


def test_normalize_name_handles_accents_and_punctuation() -> None:
    assert normalize_name("Movistar KOI — LEC") == "movistar koi lec"


def test_rendered_bans_are_projected_to_metiquo_team_ids() -> None:
    home = Team(id="team:home", league_id="league:test", data={"name": "Home"})
    away = Team(id="team:away", league_id="league:test", data={"name": "Away"})
    event = LoltvEvent(
        source_id="event-bans",
        url="https://loltv.gg/match/test-event-bans",
        home_name="Home",
        away_name="Away",
        competition="Test",
        competition_source_id="1",
        competition_slug="test",
        home_source_id="10",
        away_source_id="20",
        home_image="",
        away_image="",
        competition_image="",
        starts_at=datetime(2026, 9, 21, 12, tzinfo=UTC),
        status="live",
        best_of=3,
        home_score=1,
        away_score=0,
        payload={
            "rendered": {
                "maps": [
                    {
                        "number": 1,
                        "status": "live",
                        "winner": None,
                        "bans": [
                            {
                                "teamId": "home",
                                "champion": "Shyvana",
                                "championImage": "",
                            }
                        ],
                        "sides": [
                            {"position": "home", "players": []},
                            {"position": "away", "players": []},
                        ],
                    }
                ]
            }
        },
    )

    maps = _rendered_maps(event, home, away)

    assert maps[0]["bans"] == [{"teamId": home.id, "champion": "Shyvana", "championImage": ""}]


def test_loltv_match_reuses_another_provider_match() -> None:
    league = League(id="league:lec", data={"name": "LEC", "slug": "lec"})
    home = Team(
        id="team:navi",
        league_id=league.id,
        data={"name": "Natus Vincere", "code": "NAVI", "slug": "natus-vincere"},
    )
    away = Team(
        id="team:koi",
        league_id=league.id,
        data={"name": "Movistar KOI", "code": "MKOI", "slug": "movistar-koi"},
    )
    existing = EsportMatch(
        id=uuid4(),
        source="oracles-elixir",
        source_id="oracle:17083991",
        league_id=league.id,
        home_id=home.id,
        away_id=away.id,
        starts_at=datetime(2026, 9, 18, 15, 10, tzinfo=UTC),
        registered_at=datetime(2026, 9, 18, 15, 0, tzinfo=UTC),
        format="BO5",
    )
    result = resolve_match(
        MatchIdentity(
            home_name="Natus-Vincere",
            away_name="Movistar Koi",
            starts_at=datetime(2026, 9, 18, 15, 11, tzinfo=UTC),
            competition="LEC",
            provider="loltv",
            provider_id="17083991",
        ),
        [home, away],
        [league],
        [existing],
    )
    assert result is not None
    assert result.existing_match is existing
    assert result.reason == "team-pair-and-time"


def test_qualified_team_does_not_resolve_to_parent_team() -> None:
    parent = Team(
        id="team:blg",
        league_id="league:lpl",
        data={"name": "BILIBILI GAMING", "code": "BLG", "slug": "bilibili-gaming"},
    )

    assert resolve_team("Bilibili Gaming Junior", [parent]) is None


def test_explicit_sourced_alias_resolves_without_merging_parent_identity() -> None:
    parent = Team(
        id="team:mkoi",
        league_id="league:lec",
        data={"name": "Movistar KOI", "code": "MKOI", "slug": "movistar-koi"},
    )
    academy = Team(
        id="team:mkoi-fenix",
        league_id="league:superliga",
        data={
            "name": "Movistar KOI Fénix",
            "code": "MKOI.F",
            "slug": "movistar-koi-fenix",
            "aliases": ["MKOI Fenix"],
        },
    )

    result = resolve_team("MKOI Fénix", [parent, academy])

    assert result is not None
    assert result.team_id == academy.id
    assert result.score == 1.0


def test_unknown_competition_is_not_forced_into_closest_league() -> None:
    league = League(id="league:lck-cl", data={"name": "LCK CL", "slug": "lck-cl"})
    home = Team(
        id="team:kt-c",
        league_id=league.id,
        data={"name": "KT Rolster Challengers", "code": "KT.C", "slug": "kt-rolster-challengers"},
    )
    away = Team(
        id="team:blg-j",
        league_id=league.id,
        data={"name": "Bilibili Gaming Junior", "code": "BLG.J", "slug": "bilibili-gaming-junior"},
    )

    assert (
        resolve_match(
            MatchIdentity(
                home_name="KT Rolster Challengers",
                away_name="Bilibili Gaming Junior",
                starts_at=datetime(2026, 9, 20, 8, 15, tzinfo=UTC),
                competition="World Star Challengers Invitational Group B",
                provider="loltv",
                provider_id="37525",
            ),
            [home, away],
            [league],
            [],
        )
        is None
    )


def test_competition_stage_reuses_exact_base_league_brand() -> None:
    canonical = League(
        id="league:vcs",
        data={
            "name": "VCS",
            "slug": "vcs",
            "image": "/api/v1/catalog/logos/vcs.webp",
        },
    )
    source_stage = League(
        id="loltv:tournament:90739",
        data={"name": "VCS Regular Season", "slug": "vcs-regular-season", "image": ""},
    )
    event = LoltvEvent(
        source_id="17032527",
        url="https://loltv.gg/match/test-17032527",
        home_name="MVK Esports",
        away_name="Saigon Warriors",
        competition="VCS Regular Season",
        competition_source_id="90739",
        competition_slug="vcs-regular-season",
        home_source_id="1",
        away_source_id="2",
        home_image="",
        away_image="",
        competition_image="",
        starts_at=datetime(2026, 9, 20, 9, tzinfo=UTC),
        status="scheduled",
        best_of=3,
        home_score=None,
        away_score=None,
        payload={},
    )

    assert _competition_base_name(event.competition) == "vcs"
    assert _competition_brand(event, [source_stage, canonical]) is canonical


def test_distinct_loltv_event_is_created_without_cross_provider_match() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def scalar(self, _statement):
            return None

        def scalars(self, _statement):
            return []

        def get(self, _model, _identity):
            return None

        def add(self, value: object) -> None:
            self.added.append(value)

        def flush(self) -> None:
            return None

    league = League(id="league:wsci", data={"name": "WSCI", "slug": "wsci"})
    home = Team(id="team:koi-fenix", league_id=league.id, data={"name": "Movistar KOI Fénix"})
    away = Team(
        id="team:cfo-academy",
        league_id=league.id,
        data={"name": "CTBC Flying Oyster Academy"},
    )
    previous = EsportMatch(
        id=uuid4(),
        source="loltv",
        source_id="previous-event",
        league_id=league.id,
        home_id=home.id,
        away_id=away.id,
        starts_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        registered_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        format="BO1",
    )
    event = LoltvEvent(
        source_id="next-event",
        url="https://loltv.gg/match/test-next-event",
        home_name="Movistar KOI Fénix",
        away_name="CTBC Flying Oyster Academy",
        competition="World Star Challengers Invitational Group B",
        competition_source_id="37525",
        competition_slug="world-star-challengers-invitational-group-b",
        home_source_id="1",
        away_source_id="2",
        home_image="",
        away_image="",
        competition_image="",
        starts_at=datetime(2026, 9, 20, 10, tzinfo=UTC),
        status="scheduled",
        best_of=1,
        home_score=None,
        away_score=None,
        payload={},
    )
    fake = FakeSession()

    matched, created = _save_event(
        cast(Session, fake),
        event,
        league,
        home,
        away,
        [home, away],
        [league],
        [previous],
        datetime(2026, 9, 20, 9, tzinfo=UTC),
    )

    saved = [item for item in fake.added if isinstance(item, EsportMatch)]
    assert matched and created
    assert len(saved) == 1
    assert saved[0].source_id == "next-event"
    assert saved[0].id != previous.id


def test_oracle_game_is_projected_as_a_complete_map() -> None:
    league = League(id="league:lpl", data={"name": "LPL", "slug": "lpl"})
    home = Team(id="team:we", league_id=league.id, data={"name": "Xi'an Team WE"})
    away = Team(id="team:jdg", league_id=league.id, data={"name": "Beijing JDG Esports"})
    match = EsportMatch(
        id=uuid4(),
        source="loltv",
        source_id="17027083",
        league_id=league.id,
        home_id=home.id,
        away_id=away.id,
        starts_at=datetime(2026, 9, 18, 9, tzinfo=UTC),
        registered_at=datetime(2026, 9, 18, 9, tzinfo=UTC),
        format="BO5",
    )
    common = {
        "date": "2026-09-18 09:12:00",
        "game": "1",
        "patch": "16.17",
        "gamelength": "2170",
    }
    rows: list[OracleRow] = []
    positions = ("top", "jng", "mid", "bot", "sup")
    for team_number, team_name, participant_base, side, result in (
        ("100", home.data["name"], 1, "Blue", "1"),
        ("200", away.data["name"], 6, "Red", "0"),
    ):
        team_payload = {
            **common,
            "teamname": team_name,
            "position": "team",
            "side": side,
            "result": result,
            "towers": "9",
            "dragons": "3",
            "barons": "1",
            "heralds": "1",
            "void_grubs": "0",
            "inhibitors": "2",
            **{f"ban{index}": f"Champion {index}" for index in range(1, 6)},
        }
        rows.append(
            OracleRow(
                version_id=uuid4(),
                row_number=len(rows),
                game_id="13507-13507_game_1",
                participant_id=team_number,
                payload=team_payload,
            )
        )
        for index, position in enumerate(positions):
            rows.append(
                OracleRow(
                    version_id=uuid4(),
                    row_number=len(rows),
                    game_id="13507-13507_game_1",
                    participant_id=str(participant_base + index),
                    payload={
                        **common,
                        "teamname": team_name,
                        "position": position,
                        "side": side,
                        "playername": f"Player {participant_base + index}",
                        "playerid": f"player-{participant_base + index}",
                        "champion": f"Champion {index + 1}",
                        "kills": "2",
                        "deaths": "1",
                        "assists": "7",
                        "total cs": "210",
                        "totalgold": "12000",
                    },
                )
            )

    result = _map_for_game("13507-13507_game_1", rows, match, {home.id: home, away.id: away})

    assert result is not None
    game_map, patch = result
    assert patch == "16.17"
    assert game_map["status"] == "finished"
    assert len(game_map["bans"]) == 10
    assert len(game_map["sides"]) == 2
    assert all(len(side["players"]) == 5 for side in game_map["sides"])
