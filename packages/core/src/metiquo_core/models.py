from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str]
    status: Mapped[str] = mapped_column(default="running")
    scope: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'interrupted')"),
        Index("ix_runs_source_started", "source", "started_at"),
    )


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str]
    source_file_id: Mapped[str]
    filename: Mapped[str]
    file_year: Mapped[int]
    active_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", use_alter=True, name="fk_dataset_active_version")
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str]
    byte_count: Mapped[int] = mapped_column(BigInteger)
    row_count: Mapped[int] = mapped_column(BigInteger)
    columns: Mapped[list[str]] = mapped_column(JSONB)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("dataset_id", "sha256"),)


class OracleRow(Base):
    __tablename__ = "oracle_rows"
    version_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_versions.id"), primary_key=True)
    row_number: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str]
    participant_id: Mapped[str]
    payload: Mapped[dict[str, str]] = mapped_column(JSONB)
    __table_args__ = (Index("ix_oracle_rows_version_game", "version_id", "game_id"),)


class CatalogMetadata(Base):
    __tablename__ = "catalog_metadata"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    retrieved_at: Mapped[date]
    source: Mapped[str]
    active_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("catalog_versions.id", name="fk_catalog_active_version")
    )
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    image_cache: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, server_default="{}")
    __table_args__ = (CheckConstraint("id = 1"),)


class CatalogVersion(Base):
    __tablename__ = "catalog_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str]
    run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    document: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("source", "sha256"),)


class League(Base):
    __tablename__ = "leagues"
    id: Mapped[str] = mapped_column(primary_key=True)
    data: Mapped[dict[str, str]] = mapped_column(JSONB)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(primary_key=True)
    league_id: Mapped[str] = mapped_column(ForeignKey("leagues.id"))
    data: Mapped[dict[str, str]] = mapped_column(JSONB)


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    auth_issuer: Mapped[str]
    auth_subject: Mapped[str]
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    role: Mapped[str] = mapped_column(server_default="user")
    disabled: Mapped[bool] = mapped_column(server_default="false")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("auth_issuer", "auth_subject"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_user_role"),
        CheckConstraint("email = lower(email)", name="ck_user_email_normalized"),
    )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    binding_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ScriptSchedule(Base):
    __tablename__ = "script_schedules"
    id: Mapped[str] = mapped_column(primary_key=True)
    cron: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=1)


class ScriptRun(Base):
    __tablename__ = "script_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    script_id: Mapped[str] = mapped_column(ForeignKey("script_schedules.id"))
    trigger: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingestion_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    error: Mapped[str | None]
    __table_args__ = (
        CheckConstraint("trigger IN ('manual', 'schedule')"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')"),
        Index("ix_script_runs_requested", "script_id", "requested_at"),
        Index(
            "uq_script_runs_active",
            "script_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )


class WorkerStatus(Base):
    __tablename__ = "worker_status"
    id: Mapped[int] = mapped_column(primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scripts: Mapped[list[str]] = mapped_column(JSONB)


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("app_users.id"))
    action: Mapped[str]
    target: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class EsportMatch(Base):
    __tablename__ = "matches"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str]
    source_id: Mapped[str]
    league_id: Mapped[str] = mapped_column(ForeignKey("leagues.id"))
    home_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    away_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    format: Mapped[str]
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        CheckConstraint("home_id <> away_id"),
        CheckConstraint("format IN ('BO1', 'BO3', 'BO5')"),
    )


class MatchSourceLink(Base):
    __tablename__ = "match_source_links"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"))
    provider: Mapped[str]
    source_id: Mapped[str]
    source_url: Mapped[str]
    source_names: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("provider", "source_id"),
        Index("ix_match_source_links_match", "match_id"),
    )


class MatchSnapshot(Base):
    __tablename__ = "match_snapshots"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"))
    source: Mapped[str]
    source_id: Mapped[str]
    source_url: Mapped[str]
    status: Mapped[str]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("match_id", "sha256"),
        Index("ix_match_snapshots_latest", "match_id", "observed_at"),
    )


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"))
    bookmaker: Mapped[str] = mapped_column(default="stake")
    source_id: Mapped[str]
    kind: Mapped[str]
    pick_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (
        UniqueConstraint("bookmaker", "source_id", "pick_id"),
        CheckConstraint("bookmaker = 'stake'"),
        CheckConstraint("kind IN ('winner', 'map1')"),
    )


class OddsObservation(Base):
    __tablename__ = "odds_observations"
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    odds: Mapped[Decimal] = mapped_column(Numeric(16, 6))
    __table_args__ = (CheckConstraint("odds > 1 AND odds < 1000000000"),)


class ProbabilityEstimate(Base):
    __tablename__ = "probability_estimates"
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), primary_key=True)
    estimated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    probability: Mapped[Decimal] = mapped_column(Numeric(12, 10))
    model_version: Mapped[str]
    __table_args__ = (
        CheckConstraint("probability > 0 AND probability < 1"),
        CheckConstraint("valid_until > estimated_at"),
    )
