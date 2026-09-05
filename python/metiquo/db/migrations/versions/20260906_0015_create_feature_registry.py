"""Créer le registre immuable des définitions de features.

Revision ID: 20260906_0015
Revises: 20260906_0014
Create Date: 2026-09-06 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0015"
down_revision: str | None = "20260906_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEATURES_SCHEMA = "features"


def upgrade() -> None:
    """Créer les définitions, feature sets et membres append-only."""

    op.create_table(
        "feature_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("definition_version", sa.String(length=64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("availability", sa.String(length=24), nullable=False),
        sa.Column("required_capability", sa.String(length=128), nullable=True),
        sa.Column("code_version", sa.String(length=128), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name"),
        sa.CheckConstraint("length(trim(domain)) > 0", name="domain"),
        sa.CheckConstraint(
            "length(trim(definition_version)) > 0",
            name="definition_version",
        ),
        sa.CheckConstraint("length(trim(code_version)) > 0", name="code_version"),
        sa.CheckConstraint(
            "availability IN ('required', 'optional', 'capability_gated')",
            name="availability",
        ),
        sa.CheckConstraint(
            "(availability = 'capability_gated' AND required_capability IS NOT NULL) OR "
            "(availability <> 'capability_gated' AND required_capability IS NULL)",
            name="required_capability",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(parameters) = 'object'",
            name="parameters_object",
        ),
        sa.CheckConstraint(
            "definition_hash ~ '^[0-9a-f]{64}$'",
            name="definition_hash",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feature_definitions"),
        sa.UniqueConstraint(
            "name",
            "definition_version",
            name="uq_feature_definition_version",
        ),
        schema=FEATURES_SCHEMA,
    )
    op.create_table(
        "feature_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("set_version", sa.String(length=64), nullable=False),
        sa.Column("code_version", sa.String(length=128), nullable=False),
        sa.Column("set_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name"),
        sa.CheckConstraint("length(trim(set_version)) > 0", name="set_version"),
        sa.CheckConstraint("length(trim(code_version)) > 0", name="code_version"),
        sa.CheckConstraint("set_hash ~ '^[0-9a-f]{64}$'", name="set_hash"),
        sa.PrimaryKeyConstraint("id", name="pk_feature_sets"),
        sa.UniqueConstraint("name", "set_version", name="uq_feature_set_version"),
        schema=FEATURES_SCHEMA,
    )
    op.create_table(
        "feature_set_members",
        sa.Column("feature_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.ForeignKeyConstraint(
            ["feature_definition_id"],
            ["features.feature_definitions.id"],
            name="fk_feature_set_members_definition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feature_set_id"],
            ["features.feature_sets.id"],
            name="fk_feature_set_members_set",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "feature_set_id",
            "feature_definition_id",
            name="pk_feature_set_members",
        ),
        sa.UniqueConstraint(
            "feature_set_id",
            "position",
            name="uq_feature_set_member_position",
        ),
        sa.UniqueConstraint(
            "feature_set_id",
            "feature_definition_id",
            name="uq_feature_set_member_definition",
        ),
        schema=FEATURES_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION features.prevent_feature_registry_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'feature registry table % is append-only', TG_TABLE_NAME;
        END;
        $$
        """
    )
    for table in ("feature_definitions", "feature_sets", "feature_set_members"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON features.{table}
            FOR EACH ROW EXECUTE FUNCTION features.prevent_feature_registry_mutation()
            """
        )


def downgrade() -> None:
    """Retirer le registre après ses protections append-only."""

    for table in ("feature_set_members", "feature_sets", "feature_definitions"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON features.{table}")
    op.execute("DROP FUNCTION features.prevent_feature_registry_mutation()")
    op.drop_table("feature_set_members", schema=FEATURES_SCHEMA)
    op.drop_table("feature_sets", schema=FEATURES_SCHEMA)
    op.drop_table("feature_definitions", schema=FEATURES_SCHEMA)
