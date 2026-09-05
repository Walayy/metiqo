"""Créer le cycle champion/challenger audité.

Revision ID: 20260907_0024
Revises: 20260907_0023
Create Date: 2026-09-07 03:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0024"
down_revision: str | None = "20260907_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persister transitions manuelles et prédictions shadow immuables."""

    statuses = "('candidate', 'champion', 'retired', 'blocked')"
    op.create_table(
        "model_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("related_model_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transition_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "action IN ('promote', 'retire_for_promotion', 'rollback', "
            "'retire_for_rollback', 'block')",
            name="action",
        ),
        sa.CheckConstraint(f"from_status IN {statuses}", name="from_status"),
        sa.CheckConstraint(f"to_status IN {statuses}", name="to_status"),
        sa.CheckConstraint("from_status <> to_status", name="status_changed"),
        sa.CheckConstraint("length(trim(actor)) > 0", name="actor"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="reason"),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_object"),
        sa.CheckConstraint("transition_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_model_status_events_model",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_model_status_events_related_model",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_model_status_events"),
        sa.UniqueConstraint("transition_fingerprint", name="uq_ml_model_status_events_fingerprint"),
        schema="ml",
    )
    op.create_table(
        "shadow_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("champion_model_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("p_low", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("p_high", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prediction_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint("model_version_id <> champion_model_version_id", name="distinct_models"),
        sa.CheckConstraint("predicted_at >= cutoff_at", name="prediction_after_cutoff"),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        sa.CheckConstraint("p_low >= 0 AND p_low <= probability", name="lower_interval"),
        sa.CheckConstraint("p_high >= probability AND p_high <= 1", name="upper_interval"),
        sa.CheckConstraint("context_fingerprint ~ '^[0-9a-f]{64}$'", name="context_fingerprint"),
        sa.CheckConstraint("prediction_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_shadow_predictions_model",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["champion_model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_shadow_predictions_champion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["core.games.id"],
            name="fk_ml_shadow_predictions_event",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_shadow_predictions"),
        sa.UniqueConstraint("prediction_fingerprint", name="uq_ml_shadow_predictions_fingerprint"),
        schema="ml",
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_model_lifecycle_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'model lifecycle evidence is append-only';
        END;
        $$
        """
    )
    for table in ("model_status_events", "shadow_predictions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_model_lifecycle_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les preuves du cycle de vie."""

    for table in ("shadow_predictions", "model_status_events"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_model_lifecycle_mutation()")
    op.drop_table("shadow_predictions", schema="ml")
    op.drop_table("model_status_events", schema="ml")
