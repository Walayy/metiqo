"""Correct historical Stake runs with persisted odds that were marked failed.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only source runs with an actual persisted quote qualify. Preserve the old
    # diagnostic in JSONB because earlier workers did not record event details.
    op.execute("""
        UPDATE ingestion_runs AS run
        SET status = 'succeeded',
            error = NULL,
            details = run.details || jsonb_build_object(
                'complete', false,
                'statusCorrection', jsonb_build_object(
                    'basis', 'persisted_stake_quotes',
                    'previousStatus', run.status,
                    'previousError', run.error
                )
            )
        WHERE run.source = 'stake'
          AND run.status = 'failed'
          AND EXISTS (
              SELECT 1
              FROM bookmaker_snapshots AS snapshot
              JOIN bookmaker_quotes AS quote ON quote.snapshot_id = snapshot.id
              WHERE snapshot.run_id = run.id
          )
    """)
    op.execute("""
        UPDATE script_runs AS script
        SET status = 'succeeded', error = NULL
        FROM ingestion_runs AS run
        WHERE script.ingestion_run_id = run.id
          AND script.script_id = 'stake-markets'
          AND script.status = 'failed'
          AND run.details -> 'statusCorrection' ->> 'basis' = 'persisted_stake_quotes'
    """)


def downgrade() -> None:
    # Keep the corrected history. Reintroducing a known false failure would be
    # misleading, and the original generic diagnostics remain in details.
    pass
