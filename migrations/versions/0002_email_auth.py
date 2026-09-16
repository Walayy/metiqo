"""Email codes, revocable sessions and provisioned administrator.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("email", sa.String(254), nullable=True))
    op.add_column(
        "app_users", sa.Column("role", sa.String(), server_default="user", nullable=False)
    )
    op.add_column("app_users", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_app_users_email", "app_users", ["email"])
    op.create_check_constraint("ck_user_role", "app_users", "role IN ('user', 'admin')")
    op.create_check_constraint("ck_user_email_normalized", "app_users", "email = lower(email)")
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("binding_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("auth_challenges", "auth_sessions", "auth_rate_limits"):
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    users = sa.table(
        "app_users",
        sa.column("id", sa.Uuid()),
        sa.column("auth_issuer"),
        sa.column("auth_subject"),
        sa.column("email"),
        sa.column("role"),
    )
    op.execute(
        insert(users)
        .values(
            **{
                "id": UUID("4e3b4d5c-7030-4617-90ce-b24c2726437f"),
                "auth_issuer": "metiquo:email",
                "auth_subject": "admin@metiquo.fr",
                "email": "admin@metiquo.fr",
                "role": "admin",
            }
        )
        .on_conflict_do_update(
            index_elements=["auth_issuer", "auth_subject"],
            set_={"email": "admin@metiquo.fr", "role": "admin"},
        )
    )
    # Also upgrade privileges on existing volumes (init scripts only run once).
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        GRANT SELECT ON app_users, auth_challenges, auth_sessions, auth_rate_limits TO metiquo_api;
        GRANT INSERT (id, auth_issuer, auth_subject, email, verified_at),
          UPDATE (verified_at) ON app_users TO metiquo_api;
        GRANT INSERT, UPDATE, DELETE ON auth_challenges, auth_sessions, auth_rate_limits
          TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        REVOKE ALL ON app_users, auth_challenges, auth_sessions, auth_rate_limits
          FROM metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    for table in ("auth_rate_limits", "auth_sessions", "auth_challenges"):
        op.drop_table(table)
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        REVOKE INSERT (id, auth_issuer, auth_subject, email, verified_at),
          UPDATE (verified_at) ON app_users FROM metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON app_users TO metiquo_worker;
      END IF;
    END $$""")
    op.drop_constraint("ck_user_email_normalized", "app_users")
    op.drop_constraint("ck_user_role", "app_users")
    op.drop_constraint("uq_app_users_email", "app_users")
    for column in ("verified_at", "role", "email"):
        op.drop_column("app_users", column)
