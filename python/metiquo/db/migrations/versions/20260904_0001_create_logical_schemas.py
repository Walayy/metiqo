"""Créer les schémas logiques initiaux.

Revision ID: 20260904_0001
Revises:
Create Date: 2026-09-04 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Une migration reste autonome afin que son historique soit reproductible même si
# la liste active évolue dans metiquo.db.schemas.
SCHEMAS: tuple[str, ...] = ("raw", "core", "odds", "features", "ml", "signals", "ops")


def upgrade() -> None:
    """Créer les espaces logiques sans extension ni donnée implicite."""

    for schema_name in SCHEMAS:
        op.execute(sa.schema.CreateSchema(schema_name))


def downgrade() -> None:
    """Supprimer les schémas vides dans l'ordre inverse."""

    for schema_name in reversed(SCHEMAS):
        op.execute(sa.schema.DropSchema(schema_name))
