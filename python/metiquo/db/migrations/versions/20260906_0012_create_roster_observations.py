"""Créer les observations historiques de roster issues des games.

Revision ID: 20260906_0012
Revises: 20260906_0011
Create Date: 2026-09-06 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0012"
down_revision: str | None = "20260906_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA = "core"


def upgrade() -> None:
    """Créer une preuve datée par joueur réellement observé en game."""

    op.create_table(
        "roster_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("continuity_status", sa.String(length=32), nullable=False),
        sa.Column("observation_confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("source_raw_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_natural_key", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("source_row_revision", sa.Integer(), nullable=False),
        sa.Column("transformation_version", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('top', 'jng', 'mid', 'bot', 'sup')",
            name="ck_roster_observations_role",
        ),
        sa.CheckConstraint(
            "continuity_status IN ('first_seen', 'confirmed', 'substitution_observed')",
            name="ck_roster_observations_continuity_status",
        ),
        sa.CheckConstraint(
            "observation_confidence >= 0 AND observation_confidence <= 1",
            name="ck_roster_observations_observation_confidence",
        ),
        sa.CheckConstraint(
            "source_row_hash ~ '^[0-9a-f]{64}$'",
            name="ck_roster_observations_source_row_hash",
        ),
        sa.CheckConstraint(
            "source_row_revision >= 1",
            name="ck_roster_observations_source_row_revision",
        ),
        sa.CheckConstraint(
            "length(trim(transformation_version)) > 0",
            name="ck_roster_observations_transformation_version",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["core.games.id"],
            name="fk_roster_observations_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["core.teams.id"],
            name="fk_roster_observations_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["core.players.id"],
            name="fk_roster_observations_player_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_raw_row_id"],
            ["raw.canonical_rows.id"],
            name="fk_roster_observations_source_raw_row_id_canonical_rows",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_roster_observations_source_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_roster_observations_source_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roster_observations"),
        sa.UniqueConstraint(
            "game_id",
            "team_id",
            "role",
            name="uq_roster_observations_game_team_role",
        ),
        sa.UniqueConstraint("game_id", "player_id", name="uq_roster_observations_game_player"),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_core_roster_observations_team_observed",
        "roster_observations",
        ["team_id", "observed_at"],
        schema=CORE_SCHEMA,
    )


def downgrade() -> None:
    """Supprimer les observations sans modifier les games sources."""

    op.drop_index(
        "ix_core_roster_observations_team_observed",
        table_name="roster_observations",
        schema=CORE_SCHEMA,
    )
    op.drop_table("roster_observations", schema=CORE_SCHEMA)
