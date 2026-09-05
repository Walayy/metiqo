"""Créer les séries canoniques et leur résolution explicite.

Revision ID: 20260906_0011
Revises: 20260906_0010
Create Date: 2026-09-06 07:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260906_0011"
down_revision: str | None = "20260906_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA = "core"


def _provenance_columns() -> tuple[SchemaItem, ...]:
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
            name="fk_series_source_raw_row_id_canonical_rows",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_series_source_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_series_source_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="ck_series_source_row_hash"),
        sa.CheckConstraint("source_row_revision >= 1", name="ck_series_source_row_revision"),
        sa.CheckConstraint(
            "length(trim(transformation_version)) > 0",
            name="ck_series_transformation_version",
        ),
    )


def upgrade() -> None:
    """Créer les séries avant d'ajouter leur lien facultatif aux games."""

    op.create_table(
        "series",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_title_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("team_one_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_two_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("winner_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("series_key", sa.String(length=512), nullable=False),
        sa.Column("source_series_id", sa.String(length=255), nullable=True),
        sa.Column("identity_strategy", sa.String(length=16), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("best_of", sa.Integer(), nullable=True),
        sa.Column("allows_draw", sa.Boolean(), nullable=True),
        sa.Column("score_one", sa.Integer(), nullable=True),
        sa.Column("score_two", sa.Integer(), nullable=True),
        sa.Column("result_status", sa.String(length=16), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_provenance_columns(),
        sa.CheckConstraint("length(trim(series_key)) > 0", name="ck_series_series_key"),
        sa.CheckConstraint(
            "identity_strategy IN ('oe', 'fallback')", name="ck_series_identity_strategy"
        ),
        sa.CheckConstraint("team_one_id <> team_two_id", name="ck_series_distinct_teams"),
        sa.CheckConstraint("best_of IS NULL OR best_of >= 1", name="ck_series_best_of"),
        sa.CheckConstraint(
            "(best_of IS NULL AND allows_draw IS NULL) OR "
            "(best_of IS NOT NULL AND allows_draw = (mod(best_of, 2) = 0))",
            name="ck_series_draw_format",
        ),
        sa.CheckConstraint("score_one IS NULL OR score_one >= 0", name="ck_series_score_one"),
        sa.CheckConstraint("score_two IS NULL OR score_two >= 0", name="ck_series_score_two"),
        sa.CheckConstraint(
            "result_status IN ('team_one', 'team_two', 'draw', 'unresolved')",
            name="ck_series_result_status",
        ),
        sa.CheckConstraint(
            "(result_status IN ('team_one', 'team_two') AND winner_team_id IS NOT NULL) OR "
            "(result_status IN ('draw', 'unresolved') AND winner_team_id IS NULL)",
            name="ck_series_winner_state",
        ),
        sa.CheckConstraint(
            "quality_status IN ('complete', 'incomplete')",
            name="ck_series_quality_status",
        ),
        sa.ForeignKeyConstraint(
            ["game_title_id"],
            ["core.game_titles.id"],
            name="fk_series_game_title_id_game_titles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_series_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_one_id"],
            ["core.teams.id"],
            name="fk_series_team_one_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_two_id"],
            ["core.teams.id"],
            name="fk_series_team_two_id_teams",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["winner_team_id"],
            ["core.teams.id"],
            name="fk_series_winner_team_id_teams",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_series"),
        sa.UniqueConstraint("game_title_id", "series_key", name="uq_series_game_title_series_key"),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_core_series_scheduled_date", "series", ["scheduled_date"], schema=CORE_SCHEMA
    )
    op.add_column(
        "games",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=CORE_SCHEMA,
    )
    op.add_column(
        "games",
        sa.Column(
            "series_resolution_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'missing_context'"),
        ),
        schema=CORE_SCHEMA,
    )
    op.create_foreign_key(
        "fk_games_series_id_series",
        "games",
        "series",
        ["series_id"],
        ["id"],
        source_schema=CORE_SCHEMA,
        referent_schema=CORE_SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_games_series_resolution_status",
        "games",
        "series_resolution_status IN ('resolved', 'ambiguous', 'missing_context')",
        schema=CORE_SCHEMA,
    )


def downgrade() -> None:
    """Délier les games puis supprimer les séries."""

    op.drop_constraint(
        "ck_games_series_resolution_status", "games", schema=CORE_SCHEMA, type_="check"
    )
    op.drop_constraint("fk_games_series_id_series", "games", schema=CORE_SCHEMA, type_="foreignkey")
    op.drop_column("games", "series_resolution_status", schema=CORE_SCHEMA)
    op.drop_column("games", "series_id", schema=CORE_SCHEMA)
    op.drop_index("ix_core_series_scheduled_date", table_name="series", schema=CORE_SCHEMA)
    op.drop_table("series", schema=CORE_SCHEMA)
