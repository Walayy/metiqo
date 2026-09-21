from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from metiquo_core.config import Settings
from metiquo_core.models import EsportMatch, League, OracleRow, Team
from metiquo_worker.matching import MatchIdentity, normalize_name, resolve_match, resolve_team
from metiquo_worker.oracle_match_sync import _map_for_game
from metiquo_worker.sofascore_sync import (
    _competition_base_name,
    _competition_brand,
    _known_stable_event_ids,
    _rendered_maps,
    _save_event,
)
from metiquo_worker.sources.sofascore import (
    SofaEvent,
    SofaLink,
    _event_from_next,
    _refresh_sort_key,
    _rendered_map,
)
from sqlalchemy.orm import Session


def test_normalize_name_handles_accents_and_punctuation() -> None:
    assert normalize_name("Movistar KOI — LEC") == "movistar koi lec"


def test_live_events_are_first_in_the_refresh_queue() -> None:
    current = datetime(2026, 9, 20, tzinfo=UTC).date()
    scheduled = SofaLink("scheduled", "scheduled", current, "scheduled")
    live = SofaLink("live", "live", current, "live")

    ordered = sorted(
        [scheduled, live],
        key=lambda link: _refresh_sort_key(link, current, frozenset({"live"})),
    )

    assert [link.source_id for link in ordered] == ["live", "scheduled"]


def test_rendered_bans_are_projected_to_metiquo_team_ids() -> None:
    home = Team(id="team:home", league_id="league:test", data={"name": "Home"})
    away = Team(id="team:away", league_id="league:test", data={"name": "Away"})
    event = SofaEvent(
        source_id="event-bans",
        url="https://www.sofascore.com/esports/match/example#id:event-bans",
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


def test_sofascore_match_reuses_another_provider_match() -> None:
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
            provider="sofascore",
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
                provider="sofascore",
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
        id="sofascore:tournament:90739",
        data={"name": "VCS Regular Season", "slug": "vcs-regular-season", "image": ""},
    )
    event = SofaEvent(
        source_id="17032527",
        url="https://www.sofascore.com/fr/esports/match/example#id:17032527",
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


def test_distinct_sofascore_event_is_created_without_cross_provider_match() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def scalar(self, _statement):
            return None

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
        source="sofascore",
        source_id="previous-event",
        league_id=league.id,
        home_id=home.id,
        away_id=away.id,
        starts_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        registered_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        format="BO1",
    )
    event = SofaEvent(
        source_id="next-event",
        url="https://www.sofascore.com/fr/esports/match/example#id:next-event",
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


def test_finished_and_distant_scheduled_events_honor_freshness_after_restart() -> None:
    class FakeResult:
        def all(self):
            return [
                (
                    "finished",
                    datetime(2026, 9, 20, 8, tzinfo=UTC),
                    "finished",
                    datetime(2026, 9, 20, 8, tzinfo=UTC),
                    {"maps": [{"number": 1}]},
                ),
                (
                    "empty-finished",
                    datetime(2026, 9, 20, 8, tzinfo=UTC),
                    "finished",
                    4,
                    {"maps": []},
                ),
                (
                    "future",
                    datetime(2026, 9, 21, 8, tzinfo=UTC),
                    "scheduled",
                    datetime(2026, 9, 20, 9, 50, tzinfo=UTC),
                    {"maps": []},
                ),
                ("soon", datetime(2026, 9, 20, 10, 20, tzinfo=UTC), "scheduled", 2, {"maps": []}),
                ("live", datetime(2026, 9, 20, 9, tzinfo=UTC), "live", 1, {"maps": []}),
            ]

    class FakeSession:
        def execute(self, _statement):
            return FakeResult()

    stable = _known_stable_event_ids(
        cast(Session, FakeSession()),
        datetime(2026, 9, 20, 10, tzinfo=UTC),
        Settings(database_url="postgresql://unused"),
    )

    # The two-hour-old result is due again; the distant fixture is still cached.
    assert stable == {"future"}


def test_event_parser_keeps_explicit_score_and_teams() -> None:
    html = """
    <html><head><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"event":{
      "id":17083991,"startTimestamp":1789744200,"bestOf":5,
      "homeTeam":{"name":"Natus Vincere"},"awayTeam":{"name":"Movistar KOI"},
      "tournament":{"name":"LEC Playoffs"},"status":{"type":"inprogress"},
      "homeScore":{"current":1},"awayScore":{"current":0}
    }}}}
    </script></head><body><span>Game 2</span></body></html>
    """
    event = _event_from_next(html)
    assert event["id"] == 17083991
    assert event["homeScore"] == {"current": 1}


def test_rendered_game_panel_keeps_progressive_map_data_and_unknown_fields() -> None:
    rows = [
        ("BrokenBlade", "Myrwn", "16", "0/2/6", "3/4/0", "189", "214", "-", "-", "15"),
        ("SkewMond", "Elyoya", "16", "9/1/4", "0/4/3", "229", "182", "-", "-", "13"),
        ("Caps", "Jojopyun", "16", "2/2/11", "2/4/2", "254", "288", "-", "-", "16"),
        ("Hans sama", "Supa", "15", "2/0/8", "0/2/2", "328", "275", "-", "-", "12"),
        ("Labrov", "Alvaro", "12", "2/0/12", "0/1/2", "36", "14", "-", "-", "12"),
    ]
    capture = {
        "direct": [
            "1ST",
            "2ND",
            "15",
            "-",
            "5",
            "Objectifs",
            "0",
            "0",
            "2",
            "9",
            "0",
            "0",
            "0",
            "2",
            "Compositions",
            *(value for row in rows for value in row),
            "Phase de ban",
        ],
        "scoreClasses": ["text c_onColor.primary", "text c_onColor.secondary"],
        "championImages": [
            f"https://img.sofascore.com/api/v1/character/{index}/image" for index in range(10)
        ],
    }

    game = _rendered_map(capture, number=1, status="finished", source_id="17139011")

    assert game is not None
    assert game["winner"] == "home"
    assert game["durationSeconds"] is None
    assert game["bans"] == []
    sides = cast(list[dict[str, object]], game["sides"])
    assert sides[0]["towers"] == 9 and sides[0]["inhibitors"] == 2
    assert sides[0]["heralds"] is None and sides[0]["grubs"] is None
    players = cast(list[dict[str, object]], sides[0]["players"])
    assert players[0]["name"] == "BrokenBlade"
    assert players[0]["gold"] is None
    assert players[0]["champion"] is None
    assert players[0]["championImage"] == capture["championImages"][0]
    assert players[1]["kills"] == 9
    assert sides[0]["side"] is None and sides[1]["side"] is None
    capture["scoreClasses"] = ["score", "score"]
    assert _rendered_map(capture, number=1, status="finished", source_id="17139011") is None


def test_oracle_game_is_projected_as_a_complete_map() -> None:
    league = League(id="league:lpl", data={"name": "LPL", "slug": "lpl"})
    home = Team(id="team:we", league_id=league.id, data={"name": "Xi'an Team WE"})
    away = Team(id="team:jdg", league_id=league.id, data={"name": "Beijing JDG Esports"})
    match = EsportMatch(
        id=uuid4(),
        source="sofascore",
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
