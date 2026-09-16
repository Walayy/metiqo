"""Versioned LoL catalog and immutable logo publication.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("source", "sha256"),
    )
    op.add_column("catalog_metadata", sa.Column("active_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "catalog_metadata", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "catalog_metadata",
        sa.Column("image_cache", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_foreign_key(
        "fk_catalog_active_version",
        "catalog_metadata",
        "catalog_versions",
        ["active_version_id"],
        ["id"],
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        GRANT SELECT ON catalog_versions TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON catalog_versions TO metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    op.drop_constraint("fk_catalog_active_version", "catalog_metadata", type_="foreignkey")
    for column in ("active_version_id", "checked_at", "image_cache"):
        op.drop_column("catalog_metadata", column)
    op.drop_table("catalog_versions")
