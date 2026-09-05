"""Modèles de persistance du domaine features."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

FEATURES_SCHEMA = "features"


class FeatureDefinition(Base):
    """Définition versionnée et immuable d'une colonne de feature."""

    __tablename__ = "feature_definitions"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name"),
        CheckConstraint("length(trim(domain)) > 0", name="domain"),
        CheckConstraint("length(trim(definition_version)) > 0", name="definition_version"),
        CheckConstraint("length(trim(code_version)) > 0", name="code_version"),
        CheckConstraint(
            "availability IN ('required', 'optional', 'capability_gated')",
            name="availability",
        ),
        CheckConstraint(
            "(availability = 'capability_gated' AND required_capability IS NOT NULL) OR "
            "(availability <> 'capability_gated' AND required_capability IS NULL)",
            name="required_capability",
        ),
        CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        CheckConstraint("definition_hash ~ '^[0-9a-f]{64}$'", name="definition_hash"),
        UniqueConstraint("name", "definition_version", name="uq_feature_definition_version"),
        {"schema": FEATURES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    availability: Mapped[str] = mapped_column(String(24), nullable=False)
    required_capability: Mapped[str | None] = mapped_column(String(128))
    code_version: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class FeatureSet(Base):
    """Ensemble ordonné et versionné de définitions exactes."""

    __tablename__ = "feature_sets"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name"),
        CheckConstraint("length(trim(set_version)) > 0", name="set_version"),
        CheckConstraint("length(trim(code_version)) > 0", name="code_version"),
        CheckConstraint("set_hash ~ '^[0-9a-f]{64}$'", name="set_hash"),
        UniqueConstraint("name", "set_version", name="uq_feature_set_version"),
        {"schema": FEATURES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[str] = mapped_column(String(128), nullable=False)
    set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class FeatureSetMember(Base):
    """Appartenance immuable d'une définition à un feature set."""

    __tablename__ = "feature_set_members"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        UniqueConstraint("feature_set_id", "position", name="uq_feature_set_member_position"),
        UniqueConstraint(
            "feature_set_id",
            "feature_definition_id",
            name="uq_feature_set_member_definition",
        ),
        {"schema": FEATURES_SCHEMA},
    )

    feature_set_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_sets.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    feature_definition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_definitions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class FeatureSnapshot(Base):
    """Vecteur et lignage immuables pour une candidate de prédiction."""

    __tablename__ = "feature_snapshots"
    __table_args__ = (
        CheckConstraint("team_a_id <> team_b_id", name="distinct_teams"),
        CheckConstraint(
            "max_input_time IS NULL OR max_input_time < cutoff_at", name="input_cutoff"
        ),
        CheckConstraint(
            "max_knowledge_time IS NULL OR max_knowledge_time <= cutoff_at",
            name="knowledge_cutoff",
        ),
        CheckConstraint("jsonb_typeof(definition_versions) = 'object'", name="definitions_object"),
        CheckConstraint("jsonb_typeof(values) = 'object'", name="values_object"),
        CheckConstraint("jsonb_typeof(missingness) = 'object'", name="missingness_object"),
        CheckConstraint("jsonb_typeof(source_game_ids) = 'array'", name="games_array"),
        CheckConstraint("jsonb_typeof(source_revision_ids) = 'array'", name="revisions_array"),
        CheckConstraint("jsonb_typeof(source_snapshot_ids) = 'array'", name="snapshots_array"),
        CheckConstraint("jsonb_typeof(leakage_checks) = 'object'", name="leakage_object"),
        CheckConstraint("source_games_fingerprint ~ '^[0-9a-f]{64}$'", name="games_fingerprint"),
        CheckConstraint("vector_hash ~ '^[0-9a-f]{64}$'", name="vector_hash"),
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash"),
        CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        CheckConstraint("generation >= 1", name="generation"),
        UniqueConstraint("snapshot_hash", name="uq_feature_snapshots_hash"),
        Index("ix_features_feature_snapshots_event_cutoff", "event_id", "cutoff_at"),
        Index("ix_features_feature_snapshots_teams_cutoff", "team_a_id", "team_b_id", "cutoff_at"),
        {"schema": FEATURES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_set_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
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
    target_oe_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cutoff_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    max_input_time: Mapped[datetime | None] = mapped_column(UtcDateTime())
    max_knowledge_time: Mapped[datetime | None] = mapped_column(UtcDateTime())
    definition_versions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    values: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    missingness: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    source_game_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_revision_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_snapshot_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_games_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    leakage_checks: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    vector_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_snapshot_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("features.feature_snapshots.id", ondelete="RESTRICT"),
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class FeatureInvalidation(Base):
    """Plage de features à reconstruire après des révisions source."""

    __tablename__ = "invalidations"
    __table_args__ = (
        CheckConstraint("changed_through >= affected_from", name="date_range"),
        CheckConstraint("revision_count >= 1", name="revision_count"),
        UniqueConstraint("source_run_id", name="uq_invalidations_source_run_id"),
        Index("ix_invalidations_affected_from", "affected_from"),
        {"schema": FEATURES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    affected_from: Mapped[date] = mapped_column(nullable=False)
    changed_through: Mapped[date] = mapped_column(nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )
