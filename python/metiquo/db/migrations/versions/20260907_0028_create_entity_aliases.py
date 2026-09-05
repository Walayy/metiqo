"""Créer les aliases canoniques datés.

Revision ID: 20260907_0028
Revises: 20260907_0027
Create Date: 2026-09-07 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0028"
down_revision: str | None = "20260907_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer la liaison temporelle et vérifier la cible canonique selon son type."""

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("raw_alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('team', 'competition', 'player')",
            name="ck_entity_aliases_entity_type",
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0",
            name="ck_entity_aliases_provider",
        ),
        sa.CheckConstraint(
            "length(trim(raw_alias)) > 0",
            name="ck_entity_aliases_raw_alias",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_alias)) > 0",
            name="ck_entity_aliases_normalized_alias",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_entity_aliases_validity",
        ),
        sa.CheckConstraint(
            "source IN ('auto', 'seeded', 'manual')",
            name="ck_entity_aliases_source",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_entity_aliases_confidence",
        ),
        sa.CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)",
            name="ck_entity_aliases_approval_pair",
        ),
        sa.CheckConstraint(
            "source <> 'manual' OR approved_by IS NOT NULL",
            name="ck_entity_aliases_manual_approval",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_entity_aliases"),
        schema="core",
    )
    op.execute(
        """
        ALTER TABLE core.entity_aliases
        ADD CONSTRAINT ex_core_entity_aliases_temporal_identity
        EXCLUDE USING gist (
          entity_type WITH =,
          provider WITH =,
          normalized_alias WITH =,
          tstzrange(valid_from, valid_to, '[)') WITH &&
        )
        """
    )
    op.create_index(
        "ix_core_entity_aliases_canonical_validity",
        "entity_aliases",
        ["entity_type", "canonical_id", "valid_from", "valid_to"],
        schema="core",
    )
    op.execute(
        """
        CREATE FUNCTION core.validate_entity_alias_canonical()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          canonical_exists boolean;
        BEGIN
          IF NEW.entity_type = 'team' THEN
            SELECT EXISTS(SELECT 1 FROM core.teams WHERE id = NEW.canonical_id)
              INTO canonical_exists;
          ELSIF NEW.entity_type = 'competition' THEN
            SELECT EXISTS(SELECT 1 FROM core.competitions WHERE id = NEW.canonical_id)
              INTO canonical_exists;
          ELSIF NEW.entity_type = 'player' THEN
            SELECT EXISTS(SELECT 1 FROM core.players WHERE id = NEW.canonical_id)
              INTO canonical_exists;
          ELSE
            canonical_exists := false;
          END IF;

          IF NOT canonical_exists THEN
            RAISE EXCEPTION 'canonical % id % does not exist',
              NEW.entity_type, NEW.canonical_id;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_entity_aliases_validate_canonical
        BEFORE INSERT OR UPDATE OF entity_type, canonical_id ON core.entity_aliases
        FOR EACH ROW EXECUTE FUNCTION core.validate_entity_alias_canonical()
        """
    )


def downgrade() -> None:
    """Retirer les aliases et leur support d'exclusion temporelle."""

    op.execute("DROP TRIGGER trg_entity_aliases_validate_canonical ON core.entity_aliases")
    op.execute("DROP FUNCTION core.validate_entity_alias_canonical()")
    op.drop_index(
        "ix_core_entity_aliases_canonical_validity",
        table_name="entity_aliases",
        schema="core",
    )
    op.drop_table("entity_aliases", schema="core")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
