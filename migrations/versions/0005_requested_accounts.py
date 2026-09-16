"""Provision the two explicitly requested application accounts.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve identities, email verification and suspension. Revoke sessions only
    # when the requested role changes, in the same migration transaction.
    op.execute("""
      WITH changed AS (
        UPDATE app_users SET role = requested.role
        FROM (VALUES ('metiquo@admin.fr', 'admin'), ('metiquo@user.fr', 'user'))
          AS requested(email, role)
        WHERE app_users.email = requested.email AND app_users.role <> requested.role
        RETURNING app_users.id
      )
      DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM changed)
    """)
    op.execute("""
      INSERT INTO app_users (id, auth_issuer, auth_subject, email, role)
      SELECT gen_random_uuid(), 'metiquo:email', email, email, role
      FROM (VALUES ('metiquo@admin.fr', 'admin'), ('metiquo@user.fr', 'user'))
        AS requested(email, role)
      WHERE NOT EXISTS (SELECT 1 FROM app_users WHERE app_users.email = requested.email)
      ON CONFLICT (auth_issuer, auth_subject) DO UPDATE
        SET email = EXCLUDED.email, role = EXCLUDED.role
        WHERE app_users.email IS NULL
    """)


def downgrade() -> None:
    # Account roles are operational data. Never delete a real account or undo
    # later administrator decisions when rolling back application code.
    pass
