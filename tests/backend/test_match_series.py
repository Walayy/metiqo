from datetime import UTC, datetime
from uuid import uuid4

from metiquo_api.main import _is_complete_oracle_snapshot, _snapshot_format
from metiquo_core.matches import completed_series_summary
from metiquo_core.models import EsportMatch, MatchSnapshot


def _maps(*winners: str) -> list[dict[str, object]]:
    return [
        {"number": index, "status": "finished", "winnerId": winner}
        for index, winner in enumerate(winners, start=1)
    ]


def _match() -> EsportMatch:
    return EsportMatch(
        id=uuid4(),
        source="sofascore",
        source_id="source-match",
        league_id="league",
        home_id="home",
        away_id="away",
        starts_at=datetime(2026, 9, 18, tzinfo=UTC),
        registered_at=datetime(2026, 9, 18, tzinfo=UTC),
        format="BO5",
    )


def _snapshot(match: EsportMatch, format_name: str, maps: list[dict[str, object]]) -> MatchSnapshot:
    return MatchSnapshot(
        id=uuid4(),
        match_id=match.id,
        source="oracles-elixir",
        source_id="oracle-match",
        source_url="https://oracleselixir.com/tools/downloads",
        status="finished",
        observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        sha256="a" * 64,
        payload={"format": format_name, "maps": maps, "completionBasis": "sourced-format"},
    )


def test_completed_series_requires_the_sourced_format() -> None:
    assert completed_series_summary(_maps("home", "home"), "home", "away", "BO3") == ("BO3", 2, 0)
    assert completed_series_summary(_maps("home", "home"), "home", "away", "BO5") is None
    assert completed_series_summary(_maps("home"), "home", "away", "BO5") is None
    assert completed_series_summary(_maps("home", "home", "away"), "home", "away", "BO3") is None


def test_incomplete_series_is_not_published_as_finished() -> None:
    assert completed_series_summary(_maps("home", "away"), "home", "away", "BO3") is None
    assert (
        completed_series_summary(
            [
                {"number": 1, "status": "finished", "winnerId": "home"},
                {"number": 3, "status": "finished", "winnerId": "home"},
            ],
            "home",
            "away",
            "BO3",
        )
        is None
    )


def test_stale_oracle_format_is_not_selected_as_complete_history() -> None:
    match = _match()
    snapshot = _snapshot(match, "BO5", _maps("home", "home"))
    assert _snapshot_format(snapshot, match) is None
    assert not _is_complete_oracle_snapshot(snapshot, match)
    complete = _snapshot(match, "BO3", _maps("home", "home"))
    assert not _is_complete_oracle_snapshot(complete, match)
    match.format = "BO3"
    assert _snapshot_format(complete, match) == "BO3"
    assert _is_complete_oracle_snapshot(complete, match)
    complete.payload.pop("completionBasis")
    assert not _is_complete_oracle_snapshot(complete, match)


def test_live_snapshot_accepts_finished_and_in_progress_map_details() -> None:
    match = _match()
    snapshot = MatchSnapshot(
        id=uuid4(),
        match_id=match.id,
        source="sofascore",
        source_id="source-match",
        source_url="https://www.sofascore.com/fr/esports/match/example#id:1",
        status="live",
        observed_at=datetime(2026, 9, 20, tzinfo=UTC),
        sha256="b" * 64,
        payload={
            "format": "BO5",
            "maps": [
                {"number": 1, "status": "finished", "winnerId": "home"},
                {"number": 2, "status": "live", "winnerId": None},
            ],
        },
    )

    assert _snapshot_format(snapshot, match) == "BO5"
