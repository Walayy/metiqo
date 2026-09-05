"""Créer les dimensions canoniques League of Legends traçables.

Revision ID: 20260906_0009
Revises: 20260906_0008
Create Date: 2026-09-06 03:20:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260906_0009"
down_revision: str | None = "20260906_0008"
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


def upgrade() -> None:
    """Créer cinq dimensions dont chaque ligne remonte au raw validé."""

    op.create_table(
        "game_titles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        *_provenance_columns("game_titles"),
        sa.PrimaryKeyConstraint("id", name="pk_game_titles"),
        sa.UniqueConstraint("slug", name="uq_game_titles_slug"),
        schema=CORE_SCHEMA,
    )
    for table_name, value_column, value_length in (
        ("competitions", "source_competition_id", 255),
        ("teams", "source_team_id", 255),
        ("players", "source_player_id", 255),
        ("patches", "version", 64),
    ):
        columns: list[SchemaItem] = [
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("game_title_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(value_column, sa.String(length=value_length), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
        ]
        if table_name in {"teams", "players"}:
            columns.append(sa.Column("source_identity_kind", sa.String(length=32), nullable=False))
            allowed_identities = (
                "('teamid', 'teamname')" if table_name == "teams" else "('playerid', 'playername')"
            )
            columns.append(
                sa.CheckConstraint(
                    f"source_identity_kind IN {allowed_identities}",
                    name=f"ck_{table_name}_source_identity_kind",
                )
            )
        columns.extend(_provenance_columns(table_name))
        columns.extend(
            (
                sa.ForeignKeyConstraint(
                    ["game_title_id"],
                    ["core.game_titles.id"],
                    name=f"fk_{table_name}_game_title_id_game_titles",
                    ondelete="RESTRICT",
                ),
                sa.PrimaryKeyConstraint("id", name=f"pk_{table_name}"),
                sa.UniqueConstraint(
                    "game_title_id",
                    value_column,
                    name=f"uq_{table_name}_game_title_source_identity",
                ),
            )
        )
        op.create_table(table_name, *columns, schema=CORE_SCHEMA)


def downgrade() -> None:
    """Supprimer les dimensions dans l'ordre inverse des dépendances."""

    for table_name in ("patches", "players", "teams", "competitions", "game_titles"):
        op.drop_table(table_name, schema=CORE_SCHEMA)
