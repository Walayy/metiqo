"""Auditable bookmaker identities and deterministic reconciliation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_matches_starts_at", "matches", ["starts_at"])
    op.create_table(
        "match_identity_aliases",
        sa.Column("id", sa.String(64), primary_key=True),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "provider",
                "game",
                "name",
                "competition_key",
                "target_provider",
                "target_id",
            )
        ],
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("valid_until > valid_from"),
    )
    op.create_table(
        "bookmaker_match_resolutions",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("bookmaker_events.id"), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_match_id", sa.Uuid(), sa.ForeignKey("matches.id")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'linked', 'ambiguous', 'conflict')"),
    )
    for table, timestamp in (
        ("bookmaker_event_observations", "observed_at"),
        ("bookmaker_match_decisions", "decided_at"),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.Uuid(), sa.ForeignKey("bookmaker_events.id"), nullable=False),
            sa.Column(timestamp, sa.DateTime(timezone=True), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column(
                "payload" if timestamp == "observed_at" else "evidence", JSONB(), nullable=False
            ),
        )
        op.create_index(f"ix_{table}_event_id", table, ["event_id"])
    op.execute("""CREATE FUNCTION keep_match_evidence() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Match identity evidence is append-only';
      END $$""")
    for table in ("bookmaker_event_observations", "bookmaker_match_decisions"):
        op.execute(f"""CREATE TRIGGER keep_evidence BEFORE UPDATE OR DELETE ON {table}
          FOR EACH ROW EXECUTE FUNCTION keep_match_evidence()""")
    op.execute("""CREATE VIEW bookmaker_matching_status AS
      SELECT e.id event_id, e.bookmaker, e.game, e.source_id, e.participants,
        e.starts_at, e.competition_name, e.stopped_at,
        coalesce(r.status, 'pending') status, r.evidence, r.checked_at,
        l.match_id, l.evidence->'participants' participant_mapping
      FROM bookmaker_events e LEFT JOIN bookmaker_match_resolutions r ON r.event_id=e.id
      LEFT JOIN bookmaker_match_links l ON l.event_id=e.id AND r.status='linked'""")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api') THEN
        GRANT SELECT ON match_identity_aliases, bookmaker_event_observations,
          bookmaker_match_resolutions, bookmaker_match_decisions, bookmaker_matching_status
          TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON match_identity_aliases, bookmaker_match_resolutions
          TO metiquo_worker;
        GRANT SELECT, INSERT ON bookmaker_event_observations, bookmaker_match_decisions
          TO metiquo_worker;
        GRANT SELECT ON bookmaker_matching_status TO metiquo_worker;
        GRANT DELETE ON bookmaker_match_links TO metiquo_worker;
        REVOKE UPDATE, DELETE ON bookmaker_event_observations, bookmaker_match_decisions
          FROM metiquo_worker;
        REVOKE DELETE ON match_identity_aliases, bookmaker_match_resolutions FROM metiquo_worker;
        GRANT USAGE, SELECT ON SEQUENCE bookmaker_event_observations_id_seq,
          bookmaker_match_decisions_id_seq TO metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    op.drop_index("ix_matches_starts_at", table_name="matches")
    op.execute("DROP VIEW bookmaker_matching_status")
    for table in ("bookmaker_match_decisions", "bookmaker_event_observations"):
        op.drop_table(table)
    op.execute("DROP FUNCTION keep_match_evidence()")
    op.drop_table("bookmaker_match_resolutions")
    op.drop_table("match_identity_aliases")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_worker') THEN
        REVOKE DELETE ON bookmaker_match_links FROM metiquo_worker;
      END IF;
    END $$""")
