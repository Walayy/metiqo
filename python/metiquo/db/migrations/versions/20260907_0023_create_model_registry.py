"""Créer le registre des versions de modèles.

Revision ID: 20260907_0023
Revises: 20260906_0022
Create Date: 2026-09-07 01:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0023"
down_revision: str | None = "20260906_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persister les métadonnées et références d'artefacts vérifiables."""

    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("segment", sa.String(length=128), nullable=False),
        sa.Column("algorithm", sa.String(length=128), nullable=False),
        sa.Column("hyperparameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("training_cutoff_min", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_cutoff_max", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation_report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("calibrator_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uncertainty_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uncertainty_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_object_year", sa.Integer(), nullable=False),
        sa.Column("artifact_object_key", sa.String(length=256), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=False),
        sa.Column("artifact_format", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("registered_by", sa.String(length=128), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_reason", sa.String(length=512), nullable=False),
        sa.Column("status_changed_by", sa.String(length=128), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_reason", sa.String(length=512), nullable=False),
        sa.Column("registration_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint("game = 'lol'", name="supported_game"),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("length(trim(segment)) > 0", name="segment"),
        sa.CheckConstraint("length(trim(algorithm)) > 0", name="algorithm"),
        sa.CheckConstraint(
            "jsonb_typeof(hyperparameters) = 'object'", name="hyperparameters_object"
        ),
        sa.CheckConstraint("length(trim(feature_set_version)) > 0", name="feature_set_version"),
        sa.CheckConstraint("dataset_hash ~ '^[0-9a-f]{64}$'", name="dataset_hash"),
        sa.CheckConstraint("training_cutoff_max >= training_cutoff_min", name="cutoff_range"),
        sa.CheckConstraint("jsonb_typeof(evaluation_report) = 'object'", name="report_object"),
        sa.CheckConstraint(
            "evaluation_report_fingerprint ~ '^[0-9a-f]{64}$'", name="report_fingerprint"
        ),
        sa.CheckConstraint("uncertainty_fingerprint ~ '^[0-9a-f]{64}$'", name="uncertainty_hash"),
        sa.CheckConstraint("artifact_object_year >= 2014", name="artifact_year"),
        sa.CheckConstraint("length(trim(artifact_object_key)) > 0", name="artifact_key"),
        sa.CheckConstraint("artifact_hash ~ '^[0-9a-f]{64}$'", name="artifact_hash"),
        sa.CheckConstraint("artifact_size_bytes >= 1", name="artifact_size"),
        sa.CheckConstraint("length(trim(artifact_format)) > 0", name="artifact_format"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.CheckConstraint(
            "status IN ('candidate', 'champion', 'retired', 'blocked')", name="status"
        ),
        sa.CheckConstraint("length(trim(registered_by)) > 0", name="registered_by"),
        sa.CheckConstraint("length(trim(registration_reason)) > 0", name="registration_reason"),
        sa.CheckConstraint("length(trim(status_changed_by)) > 0", name="status_changed_by"),
        sa.CheckConstraint("length(trim(status_reason)) > 0", name="status_reason"),
        sa.CheckConstraint(
            "registration_fingerprint ~ '^[0-9a-f]{64}$'",
            name="registration_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_model_versions_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["calibrator_artifact_id"],
            ["ml.calibrator_artifacts.id"],
            name="fk_ml_model_versions_calibrator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_model_versions"),
        sa.UniqueConstraint("registration_fingerprint", name="uq_ml_model_versions_fingerprint"),
        schema="ml",
    )
    op.create_index(
        "uq_ml_model_versions_champion_scope",
        "model_versions",
        ["game", "market", "segment"],
        unique=True,
        schema="ml",
        postgresql_where=sa.text("status = 'champion'"),
    )
    op.execute(
        """
        CREATE FUNCTION ml.protect_model_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'model version cannot be deleted';
          END IF;
          IF (to_jsonb(NEW) - ARRAY['status', 'status_changed_by', 'status_changed_at',
                                    'status_reason'])
             IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['status', 'status_changed_by', 'status_changed_at',
                                    'status_reason']) THEN
            RAISE EXCEPTION 'model version immutable metadata cannot be updated';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_model_versions_protect
        BEFORE UPDATE OR DELETE ON ml.model_versions
        FOR EACH ROW EXECUTE FUNCTION ml.protect_model_version()
        """
    )


def downgrade() -> None:
    """Retirer le registre des versions de modèles."""

    op.execute("DROP TRIGGER trg_model_versions_protect ON ml.model_versions")
    op.execute("DROP FUNCTION ml.protect_model_version()")
    op.drop_index(
        "uq_ml_model_versions_champion_scope",
        table_name="model_versions",
        schema="ml",
    )
    op.drop_table("model_versions", schema="ml")
