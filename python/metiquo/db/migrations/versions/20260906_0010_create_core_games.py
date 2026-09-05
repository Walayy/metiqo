"""Créer les parties et statistiques canoniques traçables.

Revision ID: 20260906_0010
Revises: 20260906_0009
Create Date: 2026-09-06 05:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260906_0010"
down_revision: str | None = "20260906_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA = "core"


def _provenance_columns(table_name: str) -> tuple[SchemaItem, ...]:
    return (
        sa.Column("source_raw_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_natural_key", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("source_row_revision", sa.Integer(), nullable=False),
        sa.Column("transformation_version", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_raw_row_id"],
            ["raw.canonical_rows.id"],
            name=f"fk_{table_name}_source_raw_row_id_canonical_rows",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name=f"fk_{table_name}_source_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name=f"fk_{table_name}_source_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "source_row_hash ~ '^[0-9a-f]{64}$'",
            name=f"ck_{table_name}_source_row_hash",
        ),
        sa.CheckConstraint(
            "source_row_revision >= 1",
            name=f"ck_{table_name}_source_row_revision",
        ),
        sa.CheckConstraint(
            "length(trim(transformation_version)) > 0",
            name=f"ck_{table_name}_transformation_version",
        ),
    )


def _non_negative(columns: Sequence[str], table_name: str) -> tuple[SchemaItem, ...]:
    return tuple(
        sa.CheckConstraint(
            f"{column} IS NULL OR {column} >= 0",
            name=f"ck_{table_name}_{column}_non_negative",
        )
        for column in columns
    )


def upgrade() -> None:
    """Créer les faits game et conserver chaque absence dans availability."""

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_title_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("patch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_game_id", sa.String(length=255), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("game_length_seconds", sa.Integer(), nullable=True),
        sa.Column("best_of", sa.Integer(), nullable=True),
        sa.Column("game_number", sa.Integer(), nullable=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("remake", sa.Boolean(), nullable=False),
        sa.Column("forfeit", sa.Boolean(), nullable=False),
        sa.Column("usable_for_training", sa.Boolean(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_provenance_columns("games"),
        sa.CheckConstraint("length(trim(source_game_id)) > 0", name="ck_games_source_game_id"),
        sa.CheckConstraint(
            "quality_status IN ('complete', 'incomplete', 'remake', 'forfeit')",
            name="ck_games_quality_status",
        ),
        sa.CheckConstraint(
            "game_length_seconds IS NULL OR game_length_seconds > 0",
            name="ck_games_length",
        ),
        sa.CheckConstraint("best_of IS NULL OR best_of >= 1", name="ck_games_best_of"),
        sa.CheckConstraint("game_number IS NULL OR game_number >= 1", name="ck_games_game_number"),
        sa.CheckConstraint(
            "NOT usable_for_training OR (complete AND NOT remake AND NOT forfeit)",
            name="ck_games_training_eligibility",
        ),
        sa.ForeignKeyConstraint(
            ["game_title_id"],
            ["core.game_titles.id"],
            name="fk_games_game_title_id_game_titles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_games_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["patch_id"],
            ["core.patches.id"],
            name="fk_games_patch_id_patches",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_games"),
        sa.UniqueConstraint(
            "game_title_id", "source_game_id", name="uq_games_game_title_source_identity"
        ),
        schema=CORE_SCHEMA,
    )
    op.create_index("ix_core_games_event_date", "games", ["event_date"], schema=CORE_SCHEMA)

    op.create_table(
        "game_team_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("result", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.Column("gold", sa.BigInteger(), nullable=True),
        sa.Column("towers", sa.Integer(), nullable=True),
        sa.Column("dragons", sa.Integer(), nullable=True),
        sa.Column("barons", sa.Integer(), nullable=True),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_provenance_columns("game_team_stats"),
        *_non_negative(
            ("kills", "deaths", "gold", "towers", "dragons", "barons"),
            "game_team_stats",
        ),
        sa.CheckConstraint("side IN ('Blue', 'Red')", name="ck_game_team_stats_side"),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["core.games.id"],
            name="fk_game_team_stats_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["core.teams.id"],
            name="fk_game_team_stats_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_game_team_stats"),
        sa.UniqueConstraint("game_id", "team_id", name="uq_game_team_stats_game_team"),
        sa.UniqueConstraint("game_id", "side", name="uq_game_team_stats_game_side"),
        schema=CORE_SCHEMA,
    )

    op.create_table(
        "game_player_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=False),
        sa.Column("champion", sa.String(length=128), nullable=True),
        sa.Column("result", sa.Boolean(), nullable=True),
        sa.Column("kills", sa.Integer(), nullable=True),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("creep_score", sa.Integer(), nullable=True),
        sa.Column("gold", sa.BigInteger(), nullable=True),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_provenance_columns("game_player_stats"),
        *_non_negative(
            ("kills", "deaths", "assists", "creep_score", "gold"),
            "game_player_stats",
        ),
        sa.CheckConstraint("side IN ('Blue', 'Red')", name="ck_game_player_stats_side"),
        sa.CheckConstraint(
            "position IN ('top', 'jng', 'mid', 'bot', 'sup')",
            name="ck_game_player_stats_position",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["core.games.id"],
            name="fk_game_player_stats_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["core.players.id"],
            name="fk_game_player_stats_player_id_players",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["core.teams.id"],
            name="fk_game_player_stats_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_game_player_stats"),
        sa.UniqueConstraint("game_id", "player_id", name="uq_game_player_stats_game_player"),
        sa.UniqueConstraint(
            "game_id",
            "side",
            "position",
            name="uq_game_player_stats_game_side_position",
        ),
        schema=CORE_SCHEMA,
    )


def downgrade() -> None:
    """Supprimer les faits avant leurs dimensions."""

    op.drop_table("game_player_stats", schema=CORE_SCHEMA)
    op.drop_table("game_team_stats", schema=CORE_SCHEMA)
    op.drop_index("ix_core_games_event_date", table_name="games", schema=CORE_SCHEMA)
    op.drop_table("games", schema=CORE_SCHEMA)
