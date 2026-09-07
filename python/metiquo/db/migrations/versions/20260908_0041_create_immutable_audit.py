"""Journal central append-only des mutations critiques.

Revision ID: 20260908_0041
Revises: 20260908_0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0041"
down_revision: str | None = "20260908_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGETS = (
    ("raw", "source_catalog"),
    ("raw", "ingestion_runs"),
    ("raw", "snapshots"),
    ("raw", "quarantine_items"),
    ("raw", "backfill_jobs"),
    ("raw", "backfill_years"),
    ("core", "entity_aliases"),
    ("ml", "model_versions"),
    ("ml", "model_status_events"),
    ("ml", "model_action_jobs"),
    ("ml", "model_action_audits"),
    ("odds", "providers"),
    ("odds", "mapping_reviews"),
    ("odds", "mapping_audits"),
    ("odds", "market_rules"),
    ("signals", "value_policies"),
    ("signals", "value_policy_audits"),
    ("signals", "paper_bets"),
    ("signals", "settlements"),
    ("ops", "jobs"),
)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(128), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("before_refs", postgresql.JSONB(), nullable=False),
        sa.Column("after_refs", postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(before_refs) = 'object' AND jsonb_typeof(after_refs) = 'object'",
            name="references",
        ),
        sa.CheckConstraint("length(trim(actor)) > 0 AND length(trim(action)) > 0", name="identity"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_audit_target",
        "audit_events",
        ["target_type", "target_id", "occurred_at"],
        schema="ops",
    )
    op.create_index("ix_ops_audit_trace", "audit_events", ["trace_id", "occurred_at"], schema="ops")
    op.execute("""
      CREATE FUNCTION ops.prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'audit events are append-only'; END $$;
      CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON ops.audit_events
      FOR EACH ROW EXECUTE FUNCTION ops.prevent_audit_mutation();
      CREATE TRIGGER trg_audit_no_truncate BEFORE TRUNCATE ON ops.audit_events
      FOR EACH STATEMENT EXECUTE FUNCTION ops.prevent_audit_mutation();

      CREATE FUNCTION ops.safe_audit_refs(row_value jsonb) RETURNS jsonb
      LANGUAGE sql IMMUTABLE AS $$
        SELECT coalesce(jsonb_object_agg(key, value), '{}'::jsonb) FROM jsonb_each(row_value)
        WHERE key IN (
          'id','job_id','run_id','source_catalog_id','snapshot_id','current_snapshot_id',
          'model_version_id','related_model_version_id','policy_id','previous_policy_id',
          'paper_bet_id','signal_id','prediction_id','odds_snapshot_id','canonical_id',
          'review_id','event_id','market_id','rules_id','provider_id','rerun_of',
          'status','from_status','to_status','action','attempt','max_attempts','cancel_requested',
          'error_code','reason_code','revision','enabled','source','approved_at','valid_from','valid_to',
          'resolved_at','payload_sha256','attempts','year','from_year','to_year',
          'sha256','request_fingerprint','idempotency_fingerprint','transition_fingerprint',
          'input_fingerprint','evidence_fingerprint','decision_fingerprint','request_key_hash',
          'scheduled_at','started_at','finished_at','registered_at','status_changed_at'
        )
      $$;

      CREATE FUNCTION ops.audit_critical_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE old_row jsonb; new_row jsonb; before_value jsonb; after_value jsonb;
              row_value jsonb; actor_value text; trace_value uuid;
      BEGIN
        old_row := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
        new_row := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
        before_value := ops.safe_audit_refs(old_row);
        after_value := ops.safe_audit_refs(new_row);
        IF TG_OP = 'UPDATE' AND before_value = after_value THEN RETURN NEW; END IF;
        row_value := CASE WHEN TG_OP = 'DELETE' THEN old_row ELSE new_row END;
        actor_value := coalesce(nullif(current_setting('metiquo.audit_actor', true), ''),
            row_value->>'actor', row_value->>'status_changed_by', row_value->>'registered_by',
            row_value->>'approved_by', row_value->>'resolved_by', 'database:' || session_user);
        trace_value := coalesce(nullif(current_setting('metiquo.audit_trace', true), '')::uuid,
            (row_value->>'trace_id')::uuid, gen_random_uuid());
        INSERT INTO ops.audit_events(id, actor, action, target_type, target_id,
            before_refs, after_refs, trace_id, occurred_at)
        VALUES(gen_random_uuid(), actor_value,
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME || '.' || lower(TG_OP),
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, row_value->>'id',
            before_value, after_value, trace_value, clock_timestamp());
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
      END $$;
    """)
    for schema, table in _TARGETS:
        op.execute(
            "CREATE TRIGGER trg_central_audit AFTER INSERT OR UPDATE OR DELETE "
            f'ON "{schema}"."{table}" '
            "FOR EACH ROW EXECUTE FUNCTION ops.audit_critical_mutation()"
        )


def downgrade() -> None:
    for schema, table in reversed(_TARGETS):
        op.execute(f'DROP TRIGGER IF EXISTS trg_central_audit ON "{schema}"."{table}"')
    op.execute("DROP FUNCTION ops.audit_critical_mutation()")
    op.execute("DROP FUNCTION ops.safe_audit_refs(jsonb)")
    op.drop_table("audit_events", schema="ops")
    op.execute("DROP FUNCTION ops.prevent_audit_mutation()")
