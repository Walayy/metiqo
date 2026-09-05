"""Modèles de persistance des datasets et artefacts ML."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

ML_SCHEMA = "ml"


class TrainingDataset(Base):
    """Manifeste immuable d'un dataset d'entraînement reproductible."""

    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint("length(trim(provider)) > 0", name="provider"),
        CheckConstraint("length(trim(dataset)) > 0", name="dataset"),
        CheckConstraint("length(trim(dataset_version)) > 0", name="dataset_version"),
        CheckConstraint("length(trim(label_definition)) > 0", name="label_definition"),
        CheckConstraint("length(trim(feature_set_version)) > 0", name="feature_set_version"),
        CheckConstraint("period_end > period_start", name="period"),
        CheckConstraint("cutoff_max >= cutoff_min", name="cutoff_range"),
        CheckConstraint("example_count >= 1", name="example_count"),
        CheckConstraint("exclusion_count >= 0", name="exclusion_count"),
        CheckConstraint("jsonb_typeof(quality_filter) = 'object'", name="quality_filter_object"),
        CheckConstraint("jsonb_typeof(competition_ids) = 'array'", name="competitions_array"),
        CheckConstraint("jsonb_typeof(oe_snapshot_ids) = 'array'", name="snapshots_array"),
        CheckConstraint("jsonb_array_length(oe_snapshot_ids) >= 1", name="snapshots_nonempty"),
        CheckConstraint("jsonb_typeof(exclusions) = 'array'", name="exclusions_array"),
        CheckConstraint(
            "jsonb_array_length(exclusions) = exclusion_count",
            name="exclusions_count",
        ),
        CheckConstraint("feature_set_hash ~ '^[0-9a-f]{64}$'", name="feature_set_hash"),
        CheckConstraint("examples_fingerprint ~ '^[0-9a-f]{64}$'", name="examples_fingerprint"),
        CheckConstraint("dataset_hash ~ '^[0-9a-f]{64}$'", name="dataset_hash"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("dataset_hash", name="uq_ml_datasets_hash"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label_definition: Mapped[str] = mapped_column(String(128), nullable=False)
    quality_filter: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    period_start: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    period_end: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    cutoff_min: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    cutoff_max: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    competition_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    oe_snapshot_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    exclusions: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    example_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exclusion_count: Mapped[int] = mapped_column(Integer, nullable=False)
    examples_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class TrainingDatasetExample(Base):
    """Label OE et feature snapshot exact d'un exemple d'entraînement."""

    __tablename__ = "dataset_examples"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("team_a_id <> team_b_id", name="distinct_teams"),
        UniqueConstraint("dataset_id", "event_id", name="uq_dataset_examples_event"),
        UniqueConstraint(
            "dataset_id",
            "feature_snapshot_id",
            name="uq_dataset_examples_feature_snapshot",
        ),
        {"schema": ML_SCHEMA},
    )

    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    feature_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_a_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_b_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    competition_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
    )
    cutoff_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    label_team_a_win: Mapped[bool] = mapped_column(Boolean, nullable=False)
    label_source_revision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.canonical_entity_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    label_source_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )


class BaselineRun(Base):
    """Évaluation OOF immuable d'une baseline comparable."""

    __tablename__ = "baseline_runs"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint(
            "baseline_name IN ('competition_prior', 'recent_form')",
            name="supported_baseline",
        ),
        CheckConstraint("length(trim(baseline_version)) > 0", name="baseline_version"),
        CheckConstraint("evaluation_split = 'oof_validation'", name="evaluation_split"),
        CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        CheckConstraint("prediction_count >= 1", name="prediction_count"),
        CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'",
            name="predictions_fingerprint",
        ),
        CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("run_fingerprint", name="uq_ml_baseline_runs_fingerprint"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_name: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_split: Mapped[str] = mapped_column(String(32), nullable=False)
    walk_forward_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    prediction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predictions_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class BaselinePrediction(Base):
    """Probabilité OOF exacte publiée avec un run de baseline."""

    __tablename__ = "baseline_predictions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("fold_index >= 0", name="fold_index"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        UniqueConstraint("run_id", "example_id", name="uq_baseline_predictions_example"),
        {"schema": ML_SCHEMA},
    )

    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.baseline_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    example_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fold_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
