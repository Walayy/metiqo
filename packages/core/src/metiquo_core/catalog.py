from sqlalchemy.orm import Session

from metiquo_core.contracts import Catalog
from metiquo_core.models import CatalogMetadata, League, Team

CATALOG_LOCK_ID = 7_346_810_206


def import_catalog(session: Session, catalog: Catalog) -> None:
    """Explicit import of sourced identities; never loads frontend fixtures at runtime."""
    for league in catalog.leagues:
        session.merge(League(id=league.id, data=league.model_dump(by_alias=True)))
    session.flush()
    for team in catalog.teams:
        session.merge(
            Team(id=team.id, league_id=team.league_id, data=team.model_dump(by_alias=True))
        )
    session.merge(
        CatalogMetadata(
            id=1,
            retrieved_at=catalog.retrieved_at,
            source=str(catalog.source),
            active_version_id=None,
        )
    )
