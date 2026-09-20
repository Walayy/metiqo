"""Repair the persisted SofaScore WSCI match classification.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The first rendered SofaScore import retained the source competition name
    # but linked the event to the closest Riot league. Reconcile that durable
    # row from its already stored provenance; no new network request is made.
    op.execute(
        """
        UPDATE matches AS match
        SET league_id = league.id
        FROM match_source_links AS source_link, leagues AS league
        WHERE source_link.match_id = match.id
          AND source_link.provider = 'sofascore'
          AND source_link.source_names->>'competition'
              ILIKE 'World Star Challengers Invitational%'
          AND league.data->>'slug' = 'wsci'
        """
    )
    op.execute(
        """
        UPDATE matches AS match
        SET home_id = team.id
        FROM match_source_links AS source_link, leagues AS league, teams AS team
        WHERE source_link.match_id = match.id
          AND source_link.provider = 'sofascore'
          AND source_link.source_names->>'competition'
              ILIKE 'World Star Challengers Invitational%'
          AND source_link.source_names->>'home' ILIKE 'KT Rolster Challengers'
          AND league.data->>'slug' = 'wsci'
          AND team.league_id = league.id
          AND lower(team.data->>'name') = 'kt challengers'
        """
    )


def downgrade() -> None:
    pass
