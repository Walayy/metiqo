from datetime import UTC, datetime
from uuid import uuid4

from metiquo_core.models import EsportMatch, League, OracleRow, Team
from metiquo_worker.matching import MatchIdentity, normalize_name, resolve_match, resolve_team
from metiquo_worker.oracle_match_sync import _map_for_game
from metiquo_worker.sources.sofascore import _event_from_next


def test_normalize_name_handles_accents_and_punctuation() -> None:
    assert normalize_name("Movistar KOI — LEC") == "movistar koi lec"


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
