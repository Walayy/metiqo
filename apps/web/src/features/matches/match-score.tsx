import type { EsportMatch } from '@/domain/matches';
import { seriesScore } from '@/domain/matches';
import { UpdatedValue } from './updated-value';

export function MatchScore({ match, fallback = '—' }: { match: EsportMatch; fallback?: string }) {
  const known = Boolean(
    match.seriesScore || match.currentScore || match.maps.some((m) => m.winnerId),
  );
  return (
    <>
      <UpdatedValue
        value={match.status !== 'scheduled' && known ? seriesScore(match, match.homeId) : fallback}
      />
      {match.status !== 'scheduled' && known && (
        <>
          {' '}
          : <UpdatedValue value={seriesScore(match, match.awayId)} />
        </>
      )}
    </>
  );
}
