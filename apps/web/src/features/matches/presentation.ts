import type { EsportMatch, MapSide } from '@/domain/matches';
import { sideGold } from '@/domain/matches';

export const matchStatuses = [
  { id: 'all', label: 'Tous' },
  { id: 'live', label: 'En direct' },
  { id: 'scheduled', label: 'À venir' },
  { id: 'finished', label: 'Terminés' },
  { id: 'walkover', label: 'Forfaits' },
  { id: 'changed', label: 'Reportés / annulés' },
] as const;
export type MatchFilter = (typeof matchStatuses)[number]['id'];
export function matchesStatus(match: EsportMatch, filter: MatchFilter) {
  return (
    filter === 'all' ||
    (filter === 'changed'
      ? match.status === 'postponed' || match.status === 'cancelled'
      : match.status === filter)
  );
}
export function statusCounts(matches: EsportMatch[]) {
  return Object.fromEntries(
    matchStatuses.map(({ id }) => [id, matches.filter((m) => matchesStatus(m, id)).length]),
  ) as Record<MatchFilter, number>;
}
const statusOrder = { live: 0, scheduled: 1, postponed: 2, cancelled: 2, finished: 3, walkover: 3 };
export function compareMatches(a: EsportMatch, b: EsportMatch) {
  return (
    statusOrder[a.status] - statusOrder[b.status] ||
    Date.parse(a.startsAt) - Date.parse(b.startsAt) ||
    a.id.localeCompare(b.id)
  );
}
export function formatDuration(seconds: number | null) {
  return seconds == null
    ? null
    : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
export function observationAge(timestamp: string, now: number) {
  const seconds = Math.max(0, Math.floor((now - Date.parse(timestamp)) / 1000));
  if (seconds < 60) return 'il y a moins d’une minute';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h ${String(minutes % 60).padStart(2, '0')}`;
  return `il y a ${Math.floor(hours / 24)} j`;
}
export function goldDifference(home?: MapSide, away?: MapSide) {
  const left = home ? sideGold(home) : null;
  const right = away ? sideGold(away) : null;
  return left == null || right == null ? null : left - right;
}
