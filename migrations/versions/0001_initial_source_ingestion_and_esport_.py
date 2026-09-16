"""Initial source ingestion and esport domain

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_issuer", sa.String(), nullable=False),
        sa.Column("auth_subject", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_issuer", "auth_subject"),
    )
    op.create_table(
        "catalog_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retrieved_at", sa.Date(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.CheckConstraint("id = 1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_file_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_year", sa.Integer(), nullable=False),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'interrupted')"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runs_source_started", "ingestion_runs", ["source", "started_at"], unique=False
    )
    op.create_table(
        "leagues",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_path", sa.String(), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "sha256"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("league_id", sa.String(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("league_id", sa.String(), nullable=False),
        sa.Column("home_id", sa.String(), nullable=False),
        sa.Column("away_id", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.CheckConstraint("format IN ('BO1', 'BO3', 'BO5')"),
        sa.CheckConstraint("home_id <> away_id"),
        sa.ForeignKeyConstraint(
            ["away_id"],
            ["teams.id"],
        ),
        sa.ForeignKeyConstraint(
            ["home_id"],
            ["teams.id"],
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id"),
    )
    op.create_table(
        "oracle_rows",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
        ),
        sa.PrimaryKeyConstraint("version_id", "row_number"),
    )
    op.create_index(
        "ix_oracle_rows_version_game", "oracle_rows", ["version_id", "game_id"], unique=False
    )
    op.create_table(
        "markets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("bookmaker", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("pick_id", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("bookmaker = 'stake'"),
        sa.CheckConstraint("kind IN ('winner', 'map1')"),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pick_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bookmaker", "source_id", "pick_id"),
    )
    op.create_table(
        "odds_observations",
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("odds", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.CheckConstraint("odds > 1 AND odds < 1000000000"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
        ),
        sa.PrimaryKeyConstraint("market_id", "recorded_at"),
    )
    op.create_table(
        "probability_estimates",
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("estimated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Numeric(precision=12, scale=10), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.CheckConstraint("probability > 0 AND probability < 1"),
        sa.CheckConstraint("valid_until > estimated_at"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
        ),
        sa.PrimaryKeyConstraint("market_id", "estimated_at"),
    )
    op.create_foreign_key(
        "fk_dataset_active_version", "datasets", "dataset_versions", ["active_version_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_dataset_active_version", "datasets", type_="foreignkey")
    op.drop_table("probability_estimates")
    op.drop_table("odds_observations")
    op.drop_table("markets")
    op.drop_index("ix_oracle_rows_version_game", table_name="oracle_rows")
    op.drop_table("oracle_rows")
    op.drop_table("matches")
    op.drop_table("teams")
    op.drop_table("dataset_versions")
    op.drop_table("leagues")
    op.drop_index("ix_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("datasets")
    op.drop_table("catalog_metadata")
    op.drop_table("app_users")
