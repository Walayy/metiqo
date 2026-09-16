import type { Opportunity } from '@/domain/schemas';
import { normalize } from '@/lib/format';
import type { Catalog } from '@/domain/schemas';

const parisDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
export const dayKey = (date: string | Date) => parisDay.format(new Date(date));
export function validDay(day: string) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(day) &&
    Number.isFinite(Date.parse(`${day}T12:00:00Z`)) &&
    new Date(`${day}T12:00:00Z`).toISOString().slice(0, 10) === day
  );
}
export function shiftDay(day: string, offset: number) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
export function boundedDay(day: string, today: string) {
  if (!validDay(day)) return today;
  return day < shiftDay(today, -7)
    ? shiftDay(today, -7)
    : day > shiftDay(today, 7)
      ? shiftDay(today, 7)
      : day;
}
export function dayLabel(day: string, compact = false) {
  return new Intl.DateTimeFormat('fr-FR', {
    weekday: compact ? 'short' : 'long',
    day: 'numeric',
    month: compact ? 'short' : 'long',
    ...(!compact ? { year: 'numeric' as const } : {}),
    timeZone: 'Europe/Paris',
  }).format(new Date(`${day}T12:00:00Z`));
}
export interface Match {
  id: string;
  first: Opportunity;
  markets: Opportunity[];
}
export function dailyMatches(
  items: Opportunity[],
  day: string,
  catalog: Catalog,
  league: string,
  search: string,
) {
  const grouped = new Map<string, Match>();
  const term = normalize(search);
  for (const item of items) {
    if (dayKey(item.startsAt) !== day || (league !== 'all' && item.leagueId !== league)) continue;
    const teams = catalog.teams.filter((team) => [item.homeId, item.awayId].includes(team.id));
    const competition = catalog.leagues.find((entry) => entry.id === item.leagueId);
    if (
      !normalize(
        `${teams.map((team) => `${team.name} ${team.code}`).join(' ')} ${competition?.name ?? ''}`,
      ).includes(term)
    )
      continue;
    // The current API has market IDs only. Keep repeat pairings at different times distinct.
    const id = JSON.stringify([item.leagueId, ...[item.homeId, item.awayId].sort(), item.startsAt]);
    const match = grouped.get(id);
    if (match) match.markets.push(item);
    else grouped.set(id, { id, first: item, markets: [item] });
  }
  return [...grouped.values()].sort(
    (a, b) =>
      Date.parse(a.first.startsAt) - Date.parse(b.first.startsAt) || a.id.localeCompare(b.id),
  );
}
