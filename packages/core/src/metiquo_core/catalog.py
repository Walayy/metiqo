from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metiquo_core.contracts import Catalog
from metiquo_core.models import CatalogMetadata, EsportMatch, League, MatchSnapshot, Team

CATALOG_LOCK_ID = 7_346_810_206
CATALOG_WRITE_LOCK_ID = 7_346_810_209


def other_game_identities(session: Session) -> tuple[set[str], set[str]]:
    """Quarantine legacy recommendations while keeping their original evidence."""
    rows = session.execute(
        select(EsportMatch.league_id, EsportMatch.home_id, EsportMatch.away_id)
        .join(MatchSnapshot, MatchSnapshot.match_id == EsportMatch.id)
        .where(
            MatchSnapshot.source == "sofascore",
            MatchSnapshot.payload["event"]["tournament"]["category"]["slug"].astext != "lol",
        )
        .distinct()
    ).all()
    leagues = {league for league, _, _ in rows if league.startswith("sofascore:")}
    teams = {
        team for _, home, away in rows for team in (home, away) if team.startswith("sofascore:")
    }
    return leagues, teams


def import_catalog(session: Session, catalog: Catalog) -> None:
    """Explicit import of sourced identities; never loads frontend fixtures at runtime."""
    session.execute(select(func.pg_advisory_xact_lock(CATALOG_WRITE_LOCK_ID)))
    for league in catalog.leagues:
        incoming = league.model_dump(by_alias=True)
        existing_league = session.get(League, league.id)
        if existing_league is None:
            session.add(League(id=league.id, data=incoming))
        else:
            private = {
                key: existing_league.data[key]
                for key in ("aliases", "sourceIds", "sourceImages", "sourceId", "parentLeagueId")
                if key in existing_league.data
            }
            existing_league.data = {**incoming, **private}
    session.flush()
    for team in catalog.teams:
        incoming = team.model_dump(by_alias=True)
        existing_team = session.get(Team, team.id)
        if existing_team is None:
            session.add(Team(id=team.id, league_id=team.league_id, data=incoming))
        else:
            private = {
                key: existing_team.data[key]
                for key in ("aliases", "sourceIds", "sourceImages")
                if key in existing_team.data
            }
            existing_team.league_id = team.league_id
            existing_team.data = {**incoming, **private}
    session.merge(
        CatalogMetadata(
            id=1,
            retrieved_at=catalog.retrieved_at,
            source=str(catalog.source),
            active_version_id=None,
        )
    )
