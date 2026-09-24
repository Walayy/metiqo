"""Remove retired SofaScore records and schedule Stake every 20 minutes."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The old live source is retired. Remove its event and execution evidence,
    # plus legacy value rows that were attached to matches created by it.
    op.execute("""CREATE TEMP TABLE _sofascore_match_ids ON COMMIT DROP AS
        SELECT id FROM matches
        WHERE source ILIKE '%sofascore%' OR source_id ILIKE '%sofascore%'""")
    op.execute("""CREATE TEMP TABLE _sofascore_market_ids ON COMMIT DROP AS
        SELECT id FROM markets WHERE source_id ILIKE '%sofascore%'
           OR match_id IN (SELECT id FROM _sofascore_match_ids)""")
    op.execute("""DELETE FROM odds_observations
        WHERE market_id IN (SELECT id FROM _sofascore_market_ids)""")
    op.execute("""DELETE FROM probability_estimates
        WHERE market_id IN (SELECT id FROM _sofascore_market_ids)""")
    op.execute("DELETE FROM markets WHERE id IN (SELECT id FROM _sofascore_market_ids)")
    op.execute("""DELETE FROM match_snapshots
        WHERE source ILIKE '%sofascore%' OR source_id ILIKE '%sofascore%'
           OR source_url ILIKE '%sofascore%'
           OR match_id IN (SELECT id FROM _sofascore_match_ids)""")
    op.execute("""DELETE FROM match_source_links
        WHERE provider ILIKE '%sofascore%' OR source_id ILIKE '%sofascore%'
           OR source_url ILIKE '%sofascore%'
           OR match_id IN (SELECT id FROM _sofascore_match_ids)""")
    op.execute("""DELETE FROM bookmaker_match_links
        WHERE match_id IN (SELECT id FROM _sofascore_match_ids)""")
    op.execute("DELETE FROM matches WHERE id IN (SELECT id FROM _sofascore_match_ids)")
    op.execute("""DELETE FROM teams t WHERE lower(t.id) LIKE 'sofascore:%'
        AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.home_id = t.id OR m.away_id = t.id)
        AND NOT EXISTS (SELECT 1 FROM markets mk WHERE mk.pick_id = t.id)""")
    op.execute("""DELETE FROM leagues l WHERE lower(l.id) LIKE 'sofascore:%'
        AND NOT EXISTS (SELECT 1 FROM teams t WHERE t.league_id = l.id)
        AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.league_id = l.id)""")

    op.execute("DELETE FROM script_runs WHERE lower(script_id) LIKE '%sofascore%'")
    op.execute("DELETE FROM script_schedules WHERE lower(id) LIKE '%sofascore%'")
    op.execute("DELETE FROM collector_state WHERE source ILIKE '%sofascore%'")
    op.execute("DELETE FROM catalog_metadata WHERE source ILIKE '%sofascore%'")
    op.execute("""UPDATE catalog_metadata SET active_version_id = NULL
        WHERE active_version_id IN
          (SELECT id FROM catalog_versions WHERE source ILIKE '%sofascore%')""")
    op.execute("DELETE FROM catalog_versions WHERE source ILIKE '%sofascore%'")
    op.execute("DELETE FROM ingestion_runs WHERE source ILIKE '%sofascore%'")
    op.execute("""UPDATE worker_status
        SET scripts = COALESCE((SELECT jsonb_agg(value)
          FROM jsonb_array_elements(scripts) AS entries(value)
          WHERE value::text NOT ILIKE '%sofascore%'), '[]'::jsonb)
        WHERE scripts::text ILIKE '%sofascore%'""")
    op.execute("""DELETE FROM admin_audit
        WHERE action ILIKE '%sofascore%' OR target ILIKE '%sofascore%'
           OR details::text ILIKE '%sofascore%'""")

    # Align the next tick to a 20-minute boundary and bump the schedule revision
    # so any admin view observes the updated plan.
    op.execute("""UPDATE script_schedules SET cron = '*/20 * * * *',
        next_run_at = to_timestamp((floor(extract(epoch FROM now()) / 1200) + 1) * 1200),
        revision = revision + 1
        WHERE id = 'stake-markets'""")


def downgrade() -> None:
    # Deleted source history cannot be reconstructed from this schema. Roll back
    # only the Stake cadence; do not recreate the retired SofaScore schedule.
    op.execute("""UPDATE script_schedules SET cron = '*/10 * * * *',
        next_run_at = to_timestamp((floor(extract(epoch FROM now()) / 600) + 1) * 600),
        revision = revision + 1
        WHERE id = 'stake-markets'""")
