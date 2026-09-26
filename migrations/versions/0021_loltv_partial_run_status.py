"""Correct LoLTV failures only when a source snapshot proves publication during the run.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Counts alone do not prove publication. Only committed LoLTV snapshots
    # captured within the completed, source-locked run qualify for correction.
    op.execute("""
        UPDATE ingestion_runs AS run
        SET status = 'succeeded', error = NULL,
            details = run.details || jsonb_build_object(
                'complete', false,
                'statusCorrection', jsonb_build_object(
                    'basis', 'persisted_loltv_snapshots',
                    'previousStatus', run.status,
                    'previousError', run.error
                )
            )
        WHERE run.source = 'loltv' AND run.status = 'failed'
          AND run.finished_at IS NOT NULL
          AND CASE WHEN jsonb_typeof(run.details -> 'published') = 'number'
              THEN (run.details ->> 'published')::numeric > 0 ELSE false END
          AND EXISTS (
              SELECT 1 FROM match_snapshots AS snapshot
              WHERE snapshot.source = 'loltv'
                AND snapshot.observed_at >= run.started_at
                AND snapshot.observed_at <= run.finished_at
          )
    """)
    op.execute("""
        UPDATE ingestion_runs AS run
        SET details = jsonb_set(
            run.details, '{statusCorrection,previousScriptErrors}',
            (
                SELECT jsonb_object_agg(script.id::text, script.error)
                FROM script_runs AS script
                WHERE script.ingestion_run_id = run.id
                  AND script.script_id = 'loltv-matches' AND script.status = 'failed'
            )
        )
        WHERE run.details -> 'statusCorrection' ->> 'basis' = 'persisted_loltv_snapshots'
          AND EXISTS (
              SELECT 1 FROM script_runs AS script
              WHERE script.ingestion_run_id = run.id
                AND script.script_id = 'loltv-matches' AND script.status = 'failed'
          )
    """)
    op.execute("""
        UPDATE script_runs AS script
        SET status = 'succeeded', error = NULL
        FROM ingestion_runs AS run
        WHERE script.ingestion_run_id = run.id
          AND script.script_id = 'loltv-matches' AND script.status = 'failed'
          AND run.details -> 'statusCorrection' ->> 'basis' = 'persisted_loltv_snapshots'
    """)


def downgrade() -> None:
    # Preserve the corrected history and its previous diagnostic, like migration 0019.
    pass
