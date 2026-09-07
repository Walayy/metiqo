"""Créer le compte Owner unique et ses sessions opaques auditables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0044"
down_revision = "20260908_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("singleton", name="singleton"),
        sa.CheckConstraint("revision >= 1", name="revision"),
        sa.UniqueConstraint("singleton", name="uq_owner_singleton"),
        schema="ops",
    )
    op.create_table(
        "owner_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ops.owner_accounts.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotate_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("reason_code", sa.String(64)),
        sa.Column(
            "replacement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops.owner_sessions.id")
        ),
        sa.Column("grace_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash"),
        sa.CheckConstraint("status IN ('active','revoked')", name="status"),
        sa.CheckConstraint("(status = 'revoked') = (revoked_at IS NOT NULL)", name="revocation"),
        sa.CheckConstraint("expires_at > created_at AND last_seen_at >= created_at", name="times"),
        sa.UniqueConstraint("token_hash", name="uq_owner_session_token_hash"),
        schema="ops",
    )
    op.execute("""
        CREATE FUNCTION ops.guard_owner_account() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'owner history cannot be deleted'; END IF;
            IF (NEW.id, NEW.singleton, NEW.username, NEW.created_at)
                IS DISTINCT FROM (OLD.id, OLD.singleton, OLD.username, OLD.created_at)
                THEN RAISE EXCEPTION 'owner identity is immutable'; END IF;
            IF NEW.revision <> OLD.revision +
                (CASE WHEN NEW.password_hash <> OLD.password_hash THEN 1 ELSE 0 END)
                THEN RAISE EXCEPTION 'credential revision must follow password changes'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER guard_owner_account BEFORE UPDATE OR DELETE ON ops.owner_accounts
            FOR EACH ROW EXECUTE FUNCTION ops.guard_owner_account();
        CREATE TRIGGER guard_owner_account_truncate BEFORE TRUNCATE ON ops.owner_accounts
            FOR EACH STATEMENT EXECUTE FUNCTION ops.guard_owner_account();
        CREATE FUNCTION ops.guard_owner_session() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'session history cannot be deleted'; END IF;
            IF (NEW.id, NEW.owner_id, NEW.token_hash, NEW.created_at, NEW.expires_at, NEW.rotate_at)
                IS DISTINCT FROM (OLD.id, OLD.owner_id, OLD.token_hash,
                                  OLD.created_at, OLD.expires_at, OLD.rotate_at)
                THEN RAISE EXCEPTION 'session identity is immutable'; END IF;
            IF OLD.status = 'revoked' AND to_jsonb(NEW) <> to_jsonb(OLD)
                THEN RAISE EXCEPTION 'revoked session is immutable'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER guard_owner_session BEFORE UPDATE OR DELETE ON ops.owner_sessions
            FOR EACH ROW EXECUTE FUNCTION ops.guard_owner_session();
        CREATE TRIGGER guard_owner_session_truncate BEFORE TRUNCATE ON ops.owner_sessions
            FOR EACH STATEMENT EXECUTE FUNCTION ops.guard_owner_session();
        CREATE TRIGGER trg_central_audit AFTER INSERT OR UPDATE ON ops.owner_accounts
            FOR EACH ROW EXECUTE FUNCTION ops.audit_critical_mutation();
        CREATE TRIGGER trg_central_audit AFTER INSERT OR UPDATE ON ops.owner_sessions
            FOR EACH ROW EXECUTE FUNCTION ops.audit_critical_mutation();
    """)


def downgrade() -> None:
    op.drop_table("owner_sessions", schema="ops")
    op.drop_table("owner_accounts", schema="ops")
    op.execute("DROP FUNCTION ops.guard_owner_session()")
    op.execute("DROP FUNCTION ops.guard_owner_account()")
