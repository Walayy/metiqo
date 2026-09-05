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
            "baseline_name IN ('competition_prior', 'recent_form', 'rating')",
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
    artifact_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.rating_artifacts.id", ondelete="RESTRICT"),
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


class RatingArtifact(Base):
    """Transformation rating-vers-probabilité sélectionnée uniquement sur OOF."""

    __tablename__ = "rating_artifacts"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint("length(trim(artifact_version)) > 0", name="artifact_version"),
        CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        CheckConstraint("rating_feature = 'rating.difference'", name="rating_feature"),
        CheckConstraint("selected_scale > 0", name="selected_scale"),
        CheckConstraint("jsonb_typeof(candidate_scales) = 'array'", name="scales_array"),
        CheckConstraint("jsonb_array_length(candidate_scales) >= 1", name="scales_nonempty"),
        CheckConstraint("selection_metric = 'log_loss'", name="selection_metric"),
        CheckConstraint("selection_scope = 'oof_validation'", name="selection_scope"),
        CheckConstraint(
            "jsonb_typeof(candidate_metrics) = 'object'",
            name="candidate_metrics_object",
        ),
        CheckConstraint("artifact_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("artifact_fingerprint", name="uq_ml_rating_artifacts_fingerprint"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_version: Mapped[str] = mapped_column(String(64), nullable=False)
    walk_forward_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rating_feature: Mapped[str] = mapped_column(String(128), nullable=False)
    selected_scale: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    candidate_scales: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    selection_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class TabularBenchmarkRun(Base):
    """Benchmark CPU publié avec décision de promotion multi-métrique."""

    __tablename__ = "tabular_benchmark_runs"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint("length(trim(benchmark_version)) > 0", name="benchmark_version"),
        CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        CheckConstraint("jsonb_typeof(feature_spec) = 'object'", name="feature_spec_object"),
        CheckConstraint(
            "jsonb_typeof(candidate_evaluations) = 'object'",
            name="candidates_object",
        ),
        CheckConstraint("candidate_count >= 2", name="candidate_count"),
        CheckConstraint(
            "selected_candidate IN ('gradient_boosting', 'hist_gradient_boosting')",
            name="selected_candidate",
        ),
        CheckConstraint("jsonb_typeof(baseline_run_ids) = 'array'", name="baselines_array"),
        CheckConstraint("jsonb_array_length(baseline_run_ids) = 3", name="baselines_count"),
        CheckConstraint("jsonb_typeof(promotion_gate) = 'object'", name="gate_object"),
        CheckConstraint("seed >= 0", name="seed"),
        CheckConstraint("predictions_per_candidate >= 1", name="prediction_count"),
        CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'",
            name="predictions_fingerprint",
        ),
        CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("run_fingerprint", name="uq_ml_tabular_benchmark_runs_fingerprint"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    benchmark_version: Mapped[str] = mapped_column(String(64), nullable=False)
    walk_forward_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_spec: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    candidate_evaluations: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_candidate: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    promotion_gate: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    promotable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    predictions_per_candidate: Mapped[int] = mapped_column(Integer, nullable=False)
    predictions_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class TabularBenchmarkPrediction(Base):
    """Probabilité OOF exacte de chaque candidat du benchmark."""

    __tablename__ = "tabular_benchmark_predictions"
    __table_args__ = (
        CheckConstraint(
            "candidate_name IN ('gradient_boosting', 'hist_gradient_boosting')",
            name="candidate_name",
        ),
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("fold_index >= 0", name="fold_index"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        UniqueConstraint(
            "run_id",
            "candidate_name",
            "example_id",
            name="uq_tabular_benchmark_predictions_example",
        ),
        {"schema": ML_SCHEMA},
    )

    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.tabular_benchmark_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(64), primary_key=True)
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


class EnsembleCandidateRun(Base):
    """Décision immuable d'activer ou non un mélange rating/tabulaire."""

    __tablename__ = "ensemble_candidate_runs"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint("length(trim(ensemble_version)) > 0", name="ensemble_version"),
        CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        CheckConstraint("jsonb_typeof(candidate_weights) = 'array'", name="weights_array"),
        CheckConstraint("jsonb_array_length(candidate_weights) >= 1", name="weights_nonempty"),
        CheckConstraint("jsonb_typeof(candidate_evaluations) = 'object'", name="candidates_object"),
        CheckConstraint("selected_rating_weight > 0", name="selected_weight_lower"),
        CheckConstraint("selected_rating_weight < 1", name="selected_weight_upper"),
        CheckConstraint("jsonb_typeof(baseline_run_ids) = 'array'", name="baselines_array"),
        CheckConstraint("jsonb_array_length(baseline_run_ids) = 3", name="baselines_count"),
        CheckConstraint("jsonb_typeof(decision) = 'object'", name="decision_object"),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        CheckConstraint("worst_fold_log_loss >= 0", name="worst_fold_log_loss"),
        CheckConstraint("prediction_count >= 1", name="prediction_count"),
        CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'", name="predictions_fingerprint"
        ),
        CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("run_fingerprint", name="uq_ml_ensemble_candidate_runs_fingerprint"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    benchmark_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.tabular_benchmark_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rating_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.baseline_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    ensemble_version: Mapped[str] = mapped_column(String(64), nullable=False)
    walk_forward_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_weights: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    candidate_evaluations: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    selected_rating_weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    baseline_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    worst_fold_log_loss: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    prediction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predictions_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class EnsembleCandidatePrediction(Base):
    """Probabilité OOF du poids d'ensemble sélectionné."""

    __tablename__ = "ensemble_candidate_predictions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("fold_index >= 0", name="fold_index"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        UniqueConstraint("run_id", "example_id", name="uq_ensemble_predictions_example"),
        {"schema": ML_SCHEMA},
    )

    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.ensemble_candidate_runs.id", ondelete="RESTRICT"),
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


class CalibratorArtifact(Base):
    """Calibrateur séparé choisi sur des prédictions OOS temporelles."""

    __tablename__ = "calibrator_artifacts"
    __table_args__ = (
        CheckConstraint("market = 'game_winner'", name="supported_market"),
        CheckConstraint("source_kind IN ('tabular', 'ensemble')", name="source_kind"),
        CheckConstraint(
            "(source_kind = 'tabular' AND benchmark_run_id IS NOT NULL "
            "AND ensemble_run_id IS NULL) OR "
            "(source_kind = 'ensemble' AND ensemble_run_id IS NOT NULL)",
            name="source_reference",
        ),
        CheckConstraint("method IN ('platt', 'isotonic')", name="method"),
        CheckConstraint("length(trim(calibrator_version)) > 0", name="calibrator_version"),
        CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        CheckConstraint("jsonb_typeof(candidate_evaluations) = 'object'", name="candidates_object"),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        CheckConstraint("jsonb_typeof(segment_reports) = 'array'", name="segments_array"),
        CheckConstraint("oos_prediction_count >= 1", name="prediction_count"),
        CheckConstraint(
            "oos_predictions_fingerprint ~ '^[0-9a-f]{64}$'",
            name="predictions_fingerprint",
        ),
        CheckConstraint("artifact_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        UniqueConstraint("artifact_fingerprint", name="uq_ml_calibrator_artifacts_fingerprint"),
        {"schema": ML_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    benchmark_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.tabular_benchmark_runs.id", ondelete="RESTRICT"),
    )
    ensemble_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.ensemble_candidate_runs.id", ondelete="RESTRICT"),
    )
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    calibrator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    walk_forward_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    candidate_evaluations: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    calibration_slope: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    calibration_intercept: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    segment_reports: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    oos_prediction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    oos_predictions_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class CalibratorOosPrediction(Base):
    """Prédiction calibrée sur un bloc strictement futur au fit."""

    __tablename__ = "calibrator_oos_predictions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("fold_index >= 0", name="fold_index"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        UniqueConstraint("artifact_id", "example_id", name="uq_calibrator_oos_example"),
        {"schema": ML_SCHEMA},
    )

    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.calibrator_artifacts.id", ondelete="RESTRICT"),
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
