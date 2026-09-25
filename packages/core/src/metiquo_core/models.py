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


class CollectorState(Base):
    __tablename__ = "collector_state"
    source: Mapped[str] = mapped_column(primary_key=True)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


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
    __table_args__ = (
        Index("ix_oracle_rows_version_game", "version_id", "game_id"),
        Index("ix_oracle_rows_version_date", "version_id", text("left(payload ->> 'date', 10)")),
    )


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
    data: Mapped[dict[str, object]] = mapped_column(JSONB)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(primary_key=True)
    league_id: Mapped[str] = mapped_column(ForeignKey("leagues.id"))
    data: Mapped[dict[str, object]] = mapped_column(JSONB)


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
    format: Mapped[str | None]
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        Index("ix_matches_starts_at", "starts_at"),
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
    __table_args__ = (Index("ix_match_snapshots_latest", "match_id", "observed_at"),)


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


class BookmakerEvent(Base):
    """Provider identity, independent of canonical esports matches and their fixtures."""

    __tablename__ = "bookmaker_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    bookmaker: Mapped[str]
    game: Mapped[str]
    source_id: Mapped[str]
    source_url: Mapped[str]
    competition_key: Mapped[str]
    competition_name: Mapped[str | None]
    category_name: Mapped[str | None]
    participants: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    participant_keys: Mapped[list[str]] = mapped_column(JSONB)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None]
    metadata_raw: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("bookmaker", "game", "source_id"),
        CheckConstraint("bookmaker = 'stake'"),
        CheckConstraint("status IN ('scheduled', 'live', 'closed', 'unknown')"),
        CheckConstraint("(stopped_at IS NULL) = (stop_reason IS NULL)"),
        Index("ix_bookmaker_events_matching", "game", "starts_at", "competition_key"),
        Index("ix_bookmaker_events_participants", "participant_keys", postgresql_using="gin"),
    )


class BookmakerCollectionResumption(Base):
    """Historical pre-match exclusions lifted when live collection was enabled."""

    __tablename__ = "bookmaker_collection_resumptions"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), primary_key=True)
    previous_stopped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_reason: Mapped[str]
    resumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BookmakerPayload(Base):
    """Deduplicated public evidence. No cookies, headers or private browser state."""

    __tablename__ = "bookmaker_payloads"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    parser_version: Mapped[str]
    document: Mapped[dict[str, object]] = mapped_column(JSONB)


class BookmakerSnapshot(Base):
    """An atomically published traversal with a sourced pre-match or live phase."""

    __tablename__ = "bookmaker_snapshots"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id"))
    payload_sha256: Mapped[str] = mapped_column(ForeignKey("bookmaker_payloads.sha256"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phase: Mapped[str]
    capture_times: Mapped[dict[str, str]] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("run_id", "event_id"),
        CheckConstraint("started_at <= finished_at"),
        CheckConstraint("phase IN ('prematch', 'live')"),
        Index("ix_bookmaker_snapshots_event_time", "event_id", "finished_at"),
    )


class BookmakerMarket(Base):
    __tablename__ = "bookmaker_markets"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"))
    identity_key: Mapped[str] = mapped_column(String(64))
    identity_basis: Mapped[str]
    source_id: Mapped[str | None]
    label: Mapped[str]
    family: Mapped[str | None]
    scope: Mapped[str]
    period: Mapped[int | None]
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("event_id", "identity_key"),)


class BookmakerSelection(Base):
    __tablename__ = "bookmaker_selections"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_markets.id"))
    identity_key: Mapped[str] = mapped_column(String(64))
    identity_basis: Mapped[str]
    source_id: Mapped[str | None]
    label: Mapped[str]
    accessible_label: Mapped[str | None]
    column_label: Mapped[str | None]
    row_label: Mapped[str | None]
    line: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    line_raw: Mapped[str | None]
    ordinal: Mapped[int | None]
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("market_id", "identity_key"),
        CheckConstraint("ordinal IS NULL OR ordinal > 0"),
    )


class BookmakerQuote(Base):
    """Append-only readings, including unchanged odds and suspension transitions."""

    __tablename__ = "bookmaker_quotes"
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookmaker_snapshots.id"), primary_key=True
    )
    selection_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookmaker_selections.id"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tab: Mapped[str]
    odds: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    odds_raw: Mapped[str | None]
    disabled: Mapped[bool]
    __table_args__ = (
        CheckConstraint("odds IS NULL OR (odds > 1 AND odds < 1000000000)"),
        Index("ix_bookmaker_quotes_selection_time", "selection_id", "observed_at"),
        Index("ix_bookmaker_quotes_time", "observed_at", postgresql_using="brin"),
    )


class BookmakerMatchLink(Base):
    """Only currently demonstrated links; past decisions remain in the journal."""

    __tablename__ = "bookmaker_match_links"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), primary_key=True)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    method: Mapped[str]
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BookmakerEventObservation(Base):
    __tablename__ = "bookmaker_event_observations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class MatchIdentityAlias(Base):
    """Reviewed, scoped provider aliases, never global fuzzy-name substitutions."""

    __tablename__ = "match_identity_aliases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str]
    game: Mapped[str]
    name: Mapped[str]
    competition_key: Mapped[str]
    target_provider: Mapped[str]
    target_id: Mapped[str]
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("valid_until > valid_from"),)


class MatchCompetitionAlias(Base):
    """Reviewed bookmaker tournament identity scoped to one edition and source period."""

    __tablename__ = "match_competition_aliases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str]
    game: Mapped[str]
    name: Mapped[str]
    competition_key: Mapped[str]
    target_provider: Mapped[str]
    target_id: Mapped[str]
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("valid_until > valid_from"),)


class BookmakerMatchResolution(Base):
    __tablename__ = "bookmaker_match_resolutions"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), primary_key=True)
    status: Mapped[str]
    last_match_id: Mapped[UUID | None] = mapped_column(ForeignKey("matches.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint("status IN ('pending', 'linked', 'ambiguous', 'conflict')"),)


class BookmakerMatchDecision(Base):
    __tablename__ = "bookmaker_match_decisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)


class BookmakerSelectionResult(Base):
    """Current, revisable outcome of a public Stake selection, not a placed bet."""

    __tablename__ = "bookmaker_selection_results"
    selection_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookmaker_selections.id"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_events.id"), index=True)
    status: Mapped[str]
    market_kind: Mapped[str]
    map_number: Mapped[int | None]
    picked_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    source: Mapped[str | None]
    source_snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("match_snapshots.id"))
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'won', 'lost', 'void')"),
        CheckConstraint("market_kind IN ('match_winner', 'map_winner')"),
        CheckConstraint(
            "(market_kind = 'match_winner' AND map_number IS NULL) OR "
            "(market_kind = 'map_winner' AND map_number BETWEEN 1 AND 5)"
        ),
    )


class BookmakerSelectionResultDecision(Base):
    """Append-only evidence of outcome changes and corrections."""

    __tablename__ = "bookmaker_selection_result_decisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    selection_id: Mapped[UUID] = mapped_column(ForeignKey("bookmaker_selections.id"), index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
