"""Créer l'audit append-only des scores de matching événement.

Revision ID: 20260907_0029
Revises: 20260907_0028
Create Date: 2026-09-07 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0029"
down_revision: str | None = "20260907_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer les tentatives et chaque composante de candidat."""

    op.create_table(
        "event_mapping_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_status", sa.String(length=16), nullable=False),
        sa.Column("selected_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("top_score", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("selections_inverted", sa.Boolean(), nullable=False),
        sa.Column("weights_version", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result_status IN ('auto_matched', 'review', 'rejected')",
            name="ck_event_mapping_attempts_result_status",
        ),
        sa.CheckConstraint(
            "top_score BETWEEN 0 AND 1",
            name="ck_event_mapping_attempts_top_score",
        ),
        sa.CheckConstraint(
            "(result_status = 'auto_matched') = (selected_event_id IS NOT NULL)",
            name="ck_event_mapping_attempts_selected_event",
        ),
        sa.CheckConstraint(
            "length(trim(weights_version)) > 0",
            name="ck_event_mapping_attempts_weights_version",
        ),
        sa.CheckConstraint(
            "length(trim(reason_code)) > 0",
            name="ck_event_mapping_attempts_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["provider_event_id"],
            ["odds.events.id"],
            name="fk_event_mapping_attempts_provider_event_id_events",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_event_mapping_attempts"),
        schema="odds",
    )
    op.create_index(
        "ix_odds_event_mapping_attempts_provider_event_time",
        "event_mapping_attempts",
        ["provider_event_id", "evaluated_at"],
        schema="odds",
    )
    op.create_table(
        "event_mapping_candidate_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("team_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("time_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("competition_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("format_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("selections_inverted", sa.Boolean(), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_event_mapping_candidate_scores_rank"),
        sa.CheckConstraint(
            "team_score BETWEEN 0 AND 1",
            name="ck_event_mapping_candidate_scores_team_score",
        ),
        sa.CheckConstraint(
            "time_score BETWEEN 0 AND 1",
            name="ck_event_mapping_candidate_scores_time_score",
        ),
        sa.CheckConstraint(
            "competition_score BETWEEN 0 AND 1",
            name="ck_event_mapping_candidate_scores_competition_score",
        ),
        sa.CheckConstraint(
            "format_score BETWEEN 0 AND 1",
            name="ck_event_mapping_candidate_scores_format_score",
        ),
        sa.CheckConstraint(
            "total_score BETWEEN 0 AND 1",
            name="ck_event_mapping_candidate_scores_total_score",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["odds.event_mapping_attempts.id"],
            name="fk_event_mapping_scores_attempt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_event_mapping_candidate_scores"),
        sa.UniqueConstraint(
            "attempt_id",
            "rank",
            name="uq_odds_event_mapping_candidate_rank",
        ),
        sa.UniqueConstraint(
            "attempt_id",
            "canonical_event_id",
            name="uq_odds_event_mapping_candidate_event",
        ),
        schema="odds",
    )
    op.create_index(
        "ix_odds_event_mapping_candidates_event_score",
        "event_mapping_candidate_scores",
        ["canonical_event_id", "total_score"],
        schema="odds",
    )
    for table in ("event_mapping_attempts", "event_mapping_candidate_scores"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON odds.{table}
            FOR EACH ROW EXECUTE FUNCTION odds.prevent_observation_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les audits de matching événement."""

    for table in ("event_mapping_candidate_scores", "event_mapping_attempts"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON odds.{table}")
    op.drop_index(
        "ix_odds_event_mapping_candidates_event_score",
        table_name="event_mapping_candidate_scores",
        schema="odds",
    )
    op.drop_table("event_mapping_candidate_scores", schema="odds")
    op.drop_index(
        "ix_odds_event_mapping_attempts_provider_event_time",
        table_name="event_mapping_attempts",
        schema="odds",
    )
    op.drop_table("event_mapping_attempts", schema="odds")
