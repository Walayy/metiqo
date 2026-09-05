"""Historiser les corrections de lignes de façon append-only.

Revision ID: 20260906_0006
Revises: 20260905_0005
Create Date: 2026-09-06 00:05:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0006"
down_revision: str | None = "20260905_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_SCHEMA = "raw"


def upgrade() -> None:
    """Créer une baseline puis protéger toutes les futures révisions."""

    op.add_column(
        "row_revisions",
        sa.Column("event_date", sa.Date(), nullable=True),
        schema=RAW_SCHEMA,
    )
    op.drop_constraint(
        "uq_row_revisions_hash",
        "row_revisions",
        schema=RAW_SCHEMA,
        type_="unique",
    )
    op.create_index(
        "ix_row_revisions_natural_key_hash",
        "row_revisions",
        ["provider", "dataset", "natural_key", "row_hash"],
        schema=RAW_SCHEMA,
    )
    op.execute("UPDATE raw.canonical_rows SET revision = 1 WHERE revision <> 1")
    op.execute(
        """
        INSERT INTO raw.row_revisions (
          id, snapshot_id, run_id, provider, dataset, natural_key, row_hash,
          revision, operation, previous_revision_id, payload, event_date,
          valid_from, created_at
        )
        SELECT gen_random_uuid(), source_snapshot_id, source_run_id, provider, dataset,
               natural_key, row_hash, 1, 'inserted', NULL, payload, event_date,
               created_at, created_at
        FROM raw.canonical_rows
        ON CONFLICT (provider, dataset, natural_key, revision) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE FUNCTION raw.prevent_row_revision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'row revision % is append-only', OLD.id
            USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_row_revisions_prevent_mutation
        BEFORE UPDATE OR DELETE ON raw.row_revisions
        FOR EACH ROW EXECUTE FUNCTION raw.prevent_row_revision_mutation()
        """
    )


def downgrade() -> None:
    """Retirer la protection et revenir au contrat de hash initial."""

    op.execute("DROP TRIGGER trg_row_revisions_prevent_mutation ON raw.row_revisions")
    op.execute("DROP FUNCTION raw.prevent_row_revision_mutation()")
    op.drop_index(
        "ix_row_revisions_natural_key_hash",
        table_name="row_revisions",
        schema=RAW_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_row_revisions_hash",
        "row_revisions",
        ["provider", "dataset", "natural_key", "row_hash"],
        schema=RAW_SCHEMA,
    )
    op.drop_column("row_revisions", "event_date", schema=RAW_SCHEMA)
