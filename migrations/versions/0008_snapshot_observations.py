"""Allow a source to return to a previously observed match state.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("match_snapshots_match_id_sha256_key", "match_snapshots", type_="unique")
    # Previous Oracle projections inferred a smaller format from partial maps.
    # Repair only from explicit provider evidence, never from win counts.
    op.execute("""
        UPDATE matches AS match
        SET format = 'BO' || source.best_of
        FROM (
            SELECT DISTINCT ON (match_id) match_id,
                   payload->'event'->>'bestOf' AS best_of
            FROM match_snapshots
            WHERE source = 'sofascore'
              AND payload->'event'->>'bestOf' IN ('1', '3', '5')
            ORDER BY match_id, observed_at DESC, id DESC
        ) AS source
        WHERE match.id = source.match_id
    """)


def downgrade() -> None:
    # Refuse to discard immutable observations when repeated states exist.
    op.create_unique_constraint(
        "match_snapshots_match_id_sha256_key", "match_snapshots", ["match_id", "sha256"]
    )
