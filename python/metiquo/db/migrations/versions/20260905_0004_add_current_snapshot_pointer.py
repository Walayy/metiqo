"""Ajouter le pointeur atomique vers le snapshot courant.

Revision ID: 20260905_0004
Revises: 20260905_0003
Create Date: 2026-09-05 22:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0004"
down_revision: str | None = "20260905_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_SCHEMA = "raw"


def upgrade() -> None:
    """Relier chaque entrée du catalogue à son snapshot publié courant."""

    op.create_unique_constraint(
        "uq_snapshots_id_source_catalog_id",
        "snapshots",
        ["id", "source_catalog_id"],
        schema=RAW_SCHEMA,
    )
    op.add_column(
        "source_catalog",
        sa.Column("current_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=RAW_SCHEMA,
    )
    op.create_foreign_key(
        "fk_source_catalog_current_snapshot_id_snapshots",
        "source_catalog",
        "snapshots",
        ["current_snapshot_id", "id"],
        ["id", "source_catalog_id"],
        source_schema=RAW_SCHEMA,
        referent_schema=RAW_SCHEMA,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Supprimer le pointeur sans toucher aux snapshots immuables."""

    op.drop_constraint(
        "fk_source_catalog_current_snapshot_id_snapshots",
        "source_catalog",
        schema=RAW_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("source_catalog", "current_snapshot_id", schema=RAW_SCHEMA)
    op.drop_constraint(
        "uq_snapshots_id_source_catalog_id",
        "snapshots",
        schema=RAW_SCHEMA,
        type_="unique",
    )
