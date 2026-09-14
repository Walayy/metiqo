"""Observations de pages publiques Stake et historique des tentatives de scraping."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260908_0046"
down_revision = "20260908_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_providers_provider_type", "providers", schema="odds")
    op.create_check_constraint(
        "provider_type",
        "providers",
        "provider_type IN ('mock', 'manual_import', 'licensed_feed', "
        "'stake_authorized', 'public_scrape')",
        schema="odds",
    )
    op.create_table(
        "stake_scrape_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(512)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('operational', 'partial', 'blocked', 'failed')", name="status"
        ),
        sa.CheckConstraint("event_count >= 0", name="event_count"),
        schema="odds",
    )
    op.create_index("ix_stake_runs_finished", "stake_scrape_runs", ["finished_at"], schema="odds")
    op.create_table(
        "stake_page_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", UUID(as_uuid=True), sa.ForeignKey("odds.stake_scrape_runs.id"), nullable=False
        ),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("raw_payload_reference", sa.String(1024), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.UniqueConstraint("sha256", name="uq_stake_capture_sha256"),
        schema="odds",
    )
    op.create_index(
        "ix_stake_capture_event_time",
        "stake_page_captures",
        ["provider_event_id", "observed_at"],
        schema="odds",
    )
    for table in ("stake_scrape_runs", "stake_page_captures"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_prevent_mutation BEFORE UPDATE OR DELETE ON odds.{table} "
            "FOR EACH ROW EXECUTE FUNCTION odds.prevent_observation_mutation()"
        )


def downgrade() -> None:
    # Les observations historiques déjà référencées gardent leur type ; les nouvelles
    # écritures public_scrape sont interdites après retour à l'ancienne version.
    op.drop_table("stake_page_captures", schema="odds")
    op.drop_table("stake_scrape_runs", schema="odds")
    op.drop_constraint("ck_providers_provider_type", "providers", schema="odds")
    op.create_check_constraint(
        "provider_type",
        "providers",
        "provider_type IN ('mock', 'manual_import', 'licensed_feed', 'stake_authorized')",
        schema="odds",
        postgresql_not_valid=True,
    )
