"""Conserver les preuves et échecs des sauvegardes sans supprimer leur historique."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0043"
down_revision = "20260908_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("repository_fingerprint", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("retained", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="status"),
        sa.CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finished_state"),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="times"),
        sa.CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        sa.CheckConstraint("status <> 'succeeded' OR sha256 IS NOT NULL", name="success_proof"),
        schema="ops",
    )
    op.create_index(
        "ix_backup_runs_repository",
        "backup_runs",
        ["repository_fingerprint", "started_at"],
        schema="ops",
    )
    op.execute("""
      CREATE FUNCTION ops.guard_backup_proof() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'backup history is append-only'; END IF;
        IF OLD.status <> 'running' AND (to_jsonb(NEW) - 'retained') <> (to_jsonb(OLD) - 'retained')
          THEN RAISE EXCEPTION 'completed backup proof is immutable'; END IF;
        IF NOT OLD.retained AND NEW.retained
          THEN RAISE EXCEPTION 'retention cannot be reversed'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER guard_backup_proof BEFORE UPDATE OR DELETE ON ops.backup_runs
        FOR EACH ROW EXECUTE FUNCTION ops.guard_backup_proof();
      CREATE TRIGGER guard_backup_truncate BEFORE TRUNCATE ON ops.backup_runs
        FOR EACH STATEMENT EXECUTE FUNCTION ops.guard_backup_proof();
      CREATE TRIGGER trg_central_audit AFTER INSERT OR UPDATE ON ops.backup_runs
        FOR EACH ROW EXECUTE FUNCTION ops.audit_critical_mutation();
    """)


def downgrade() -> None:
    op.drop_table("backup_runs", schema="ops")
    op.execute("DROP FUNCTION ops.guard_backup_proof()")
