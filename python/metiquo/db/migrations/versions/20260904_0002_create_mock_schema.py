"""Créer le schéma isolé du mode mock.

Revision ID: 20260904_0002
Revises: 20260904_0001
Create Date: 2026-09-04 14:15:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0002"
down_revision: str | None = "20260904_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOCK_SCHEMA = "mock"


def upgrade() -> None:
    """Créer un namespace physique réservé aux données de démonstration."""

    op.execute(sa.schema.CreateSchema(MOCK_SCHEMA))


def downgrade() -> None:
    """Supprimer le namespace mock lorsqu'il est vide."""

    op.execute(sa.schema.DropSchema(MOCK_SCHEMA))
