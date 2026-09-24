"""Collect public Stake markets during live events and preserve old stop decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _quote_guard(*, prematch_only: bool) -> None:
    cutoff = "OR NEW.observed_at >= scheduled" if prematch_only else ""
    message = "Invalid pre-match quote provenance" if prematch_only else "Invalid quote provenance"
    suspension_guard = (
        ""
        if prematch_only
        else """
        IF (NEW.disabled AND NEW.odds IS NOT NULL)
          OR (NOT NEW.disabled AND NEW.odds IS NULL) THEN
          RAISE EXCEPTION 'A suspended quote has no available odds';
        END IF;"""
    )
    op.execute(f"""CREATE OR REPLACE FUNCTION bookmaker_guard_quote() RETURNS trigger
      LANGUAGE plpgsql AS $$
      DECLARE e uuid; started timestamptz; ended timestamptz;
              scheduled timestamptz; selection_event uuid;
      BEGIN
        SELECT event_id, started_at, finished_at, scheduled_start_at
          INTO e, started, ended, scheduled FROM bookmaker_snapshots WHERE id=NEW.snapshot_id;
        SELECT m.event_id INTO selection_event FROM bookmaker_selections s
          JOIN bookmaker_markets m ON m.id=s.market_id WHERE s.id=NEW.selection_id;
        IF e IS DISTINCT FROM selection_event OR NEW.observed_at < started
          OR NEW.observed_at > ended {cutoff} THEN
          RAISE EXCEPTION '{message}';
        END IF;
        {suspension_guard}
        RETURN NEW;
      END $$""")


def _snapshot_guard(*, prematch_only: bool) -> None:
    if prematch_only:
        op.execute("""CREATE OR REPLACE FUNCTION bookmaker_guard_snapshot() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.scheduled_start_at <= clock_timestamp() OR EXISTS (
              SELECT 1 FROM bookmaker_events WHERE id=NEW.event_id AND stopped_at IS NOT NULL
            ) THEN RAISE EXCEPTION 'Event no longer eligible for pre-match collection'; END IF;
            RETURN NEW;
          END $$""")
    else:
        op.execute("""CREATE OR REPLACE FUNCTION bookmaker_guard_snapshot() RETURNS trigger
          LANGUAGE plpgsql AS $$
          DECLARE current_status text; stopped timestamptz;
          BEGIN
            SELECT status, stopped_at INTO current_status, stopped
              FROM bookmaker_events WHERE id=NEW.event_id;
            IF current_status IS NULL OR stopped IS NOT NULL THEN
              RAISE EXCEPTION 'Event no longer collectible';
            END IF;
            IF NEW.phase = 'prematch' AND
              (current_status <> 'scheduled' OR NEW.scheduled_start_at IS NULL
               OR NEW.scheduled_start_at <= clock_timestamp()) THEN
              RAISE EXCEPTION 'Pre-match status or time is no longer valid';
            END IF;
            IF NEW.phase = 'live' AND current_status <> 'live' THEN
              RAISE EXCEPTION 'Live event status is no longer valid';
            END IF;
            RETURN NEW;
          END $$""")


def _current_view(*, prematch_only: bool) -> None:
    op.execute("DROP VIEW bookmaker_current_quotes")
    phase_column = "" if prematch_only else ", phase"
    extra_columns = (
        ""
        if prematch_only
        else """,
        l.phase AS captured_phase, e.status AS event_status, s.row_label,
        (NOT q.disabled AND q.odds IS NOT NULL) AS quote_open"""
    )
    status_guard = "" if prematch_only else "e.status = 'scheduled' AND "
    op.execute(f"""CREATE VIEW bookmaker_current_quotes AS
      WITH latest AS (
        SELECT DISTINCT ON (event_id) id, event_id, finished_at{phase_column}
        FROM bookmaker_snapshots ORDER BY event_id, finished_at DESC, id
      )
      SELECT DISTINCT ON (q.selection_id)
        e.id AS event_id, e.bookmaker, e.game, e.source_id AS event_source_id,
        e.source_url, e.competition_key, e.competition_name, e.participants, e.starts_at,
        e.stopped_at, e.stop_reason, m.id AS market_id, m.label AS market_label,
        m.family, m.scope, m.period, s.id AS selection_id, s.label AS selection_label,
        s.accessible_label, s.column_label, s.line, s.line_raw, s.ordinal,
        q.odds, q.odds_raw, q.disabled, q.observed_at, q.snapshot_id,
        (e.stopped_at IS NULL AND {status_guard}e.starts_at > now()) AS collecting_prematch
        {extra_columns}
      FROM latest l JOIN bookmaker_events e ON e.id=l.event_id
      JOIN bookmaker_quotes q ON q.snapshot_id=l.id
      JOIN bookmaker_selections s ON s.id=q.selection_id
      JOIN bookmaker_markets m ON m.id=s.market_id
      ORDER BY q.selection_id, q.observed_at DESC""")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api') THEN
        GRANT SELECT ON bookmaker_current_quotes TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_worker') THEN
        GRANT SELECT ON bookmaker_current_quotes TO metiquo_worker;
      END IF;
    END $$""")


def upgrade() -> None:
    op.add_column("bookmaker_selections", sa.Column("row_label", sa.String(), nullable=True))
    op.create_table(
        "bookmaker_collection_resumptions",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("bookmaker_events.id"), primary_key=True),
        sa.Column("previous_stopped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_reason", sa.String(), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("""INSERT INTO bookmaker_collection_resumptions
      (event_id, previous_stopped_at, previous_reason, resumed_at)
      SELECT id, stopped_at, stop_reason, clock_timestamp()
      FROM bookmaker_events
      WHERE stop_reason IN ('live', 'live_listing', 'start_time_reached')""")
    op.execute("DROP TRIGGER bookmaker_event_stop ON bookmaker_events")
    op.execute("""UPDATE bookmaker_events SET stopped_at=NULL, stop_reason=NULL
      WHERE id IN (SELECT event_id FROM bookmaker_collection_resumptions)""")
    op.execute("""CREATE TRIGGER bookmaker_event_stop BEFORE UPDATE ON bookmaker_events
      FOR EACH ROW EXECUTE FUNCTION bookmaker_keep_stop()""")

    op.add_column(
        "bookmaker_snapshots",
        sa.Column("phase", sa.String(), nullable=False, server_default="prematch"),
    )
    op.alter_column("bookmaker_snapshots", "scheduled_start_at", nullable=True)
    op.drop_constraint("bookmaker_snapshots_check", "bookmaker_snapshots", type_="check")
    op.create_check_constraint(
        "ck_bookmaker_snapshots_capture_order", "bookmaker_snapshots", "started_at <= finished_at"
    )
    op.create_check_constraint(
        "ck_bookmaker_snapshots_phase",
        "bookmaker_snapshots",
        "phase IN ('prematch', 'live')",
    )
    _quote_guard(prematch_only=False)
    _snapshot_guard(prematch_only=False)
    _current_view(prematch_only=False)
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api') THEN
        GRANT SELECT ON bookmaker_collection_resumptions TO metiquo_api;
      END IF;
    END $$""")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM bookmaker_snapshots WHERE phase='live'")):
        raise RuntimeError("Cannot revert Stake live support while live snapshots are preserved")
    if connection.scalar(
        sa.text("""SELECT count(*) FROM bookmaker_collection_resumptions r
      JOIN bookmaker_snapshots s ON s.event_id=r.event_id AND s.finished_at > r.resumed_at""")
    ):
        raise RuntimeError("Cannot revert Stake live support after resumed events were collected")
    _current_view(prematch_only=True)
    _quote_guard(prematch_only=True)
    _snapshot_guard(prematch_only=True)
    op.drop_constraint("ck_bookmaker_snapshots_phase", "bookmaker_snapshots", type_="check")
    op.drop_constraint("ck_bookmaker_snapshots_capture_order", "bookmaker_snapshots", type_="check")
    op.create_check_constraint(
        "bookmaker_snapshots_check",
        "bookmaker_snapshots",
        "started_at <= finished_at AND finished_at < scheduled_start_at",
    )
    op.alter_column("bookmaker_snapshots", "scheduled_start_at", nullable=False)
    op.drop_column("bookmaker_snapshots", "phase")
    op.execute("DROP TRIGGER bookmaker_event_stop ON bookmaker_events")
    op.execute("""UPDATE bookmaker_events e SET stopped_at=r.previous_stopped_at,
      stop_reason=r.previous_reason FROM bookmaker_collection_resumptions r
      WHERE e.id=r.event_id AND e.stopped_at IS NULL""")
    op.execute("""CREATE TRIGGER bookmaker_event_stop BEFORE UPDATE ON bookmaker_events
      FOR EACH ROW EXECUTE FUNCTION bookmaker_keep_stop()""")
    op.drop_table("bookmaker_collection_resumptions")
    op.drop_column("bookmaker_selections", "row_label")
