import { catalog, opportunities, WORLD_STAR_LEAGUE_ID } from './fixtures';
import champions from './data/champions.json';
import { matchesSchema } from '@/domain/matches';
import type { EsportMatch, MapSide, MatchMap } from '@/domain/matches';
import { performanceSchema } from '@/features/performance/simulation';
import { dayKey, shiftDay } from '@/features/matches/calendar';

// Fictional rosters, scores and settlements. No assertion about real players or results.
const now = Date.now();
const roles = ['TOP', 'JGL', 'MID', 'BOT', 'SUP'] as const;
const names = ['Aster', 'Nox', 'Solis', 'Vega', 'Echo', 'Orion', 'Kiro', 'Nova', 'Lynx', 'Rune'];
function side(teamId: string, color: 'blue' | 'red', seed: number, rosterOffset: number): MapSide {
  const offset = color === 'blue' ? 0 : 5;
  return {
    teamId,
    side: color,
    towers: color === 'blue' ? 5 : 3,
    dragons: color === 'blue' ? 2 : 1,
    barons: color === 'blue' ? 1 : 0,
    heralds: 0,
    grubs: 0,
    inhibitors: 0,
    players: roles.map((role, i) => ({
      id: `${teamId}-${role}`,
      name: names[rosterOffset + i]!,
      role,
      champion: champions[offset + i]!.name,
      championImage: champions[offset + i]!.image,
      kills: [2, 3, 4, 5, 0][i]! + (seed % 2),
      deaths: [3, 2, 5, 2, 2][i]! + (seed % 2),
      assists: [5, 8, 6, 4, 11][i]!,
      cs: [211, 160, 235, 251, 32][i]! + seed * 2,
      gold: [10400, 9300, 11800, 12600, 6500][i]! + seed * 200 + (color === 'blue' ? 750 : 0),
    })),
  };
}
function maps(
  homeId: string,
  awayId: string,
  format: EsportMatch['format'],
  status: EsportMatch['status'],
  seed: number,
  finishedWinnerId: string | null = null,
): MatchMap[] {
  const max = Number(format.slice(2));
  const won = Math.ceil(max / 2);
  return Array.from({ length: max }, (_, i) => {
    const state =
      status === 'scheduled'
        ? 'scheduled'
        : status === 'live'
          ? i === 0 && max > 1
            ? 'finished'
            : i === (max > 1 ? 1 : 0)
              ? 'live'
              : 'scheduled'
          : i < won
            ? 'finished'
            : 'skipped';
    const started = state === 'live' || state === 'finished';
    return {
      number: i + 1,
      status: state,
      durationSeconds: started ? (state === 'live' ? 1634 : 1927 + i * 37) : 0,
      winnerId: state === 'finished' ? finishedWinnerId ?? homeId : null,
      bans: [],
      sides: started
        ? [
            side(i % 2 ? awayId : homeId, 'blue', seed + i, i % 2 ? 5 : 0),
            side(i % 2 ? homeId : awayId, 'red', seed + i, i % 2 ? 0 : 5),
          ]
        : [],
    };
  });
}
const items = opportunities.items
  .filter((item) => item.market === 'winner')
  .map((item, index): EsportMatch => {
    let startsAt = item.startsAt;
    const today = dayKey(startsAt) === dayKey(new Date(now));
    if (today && index === 0) startsAt = new Date(now - 80 * 60000).toISOString();
    if (today && index === 1) startsAt = new Date(now + 22 * 60000).toISOString();
    if (today && index === 7) startsAt = new Date(now + 70 * 60000).toISOString();
    const status =
      index === 0 ? 'live' : Date.parse(startsAt) < now - 3 * 3600000 ? 'finished' : 'scheduled';
    return {
      id: `match-${item.id}`,
      leagueId: item.leagueId,
      homeId: item.homeId,
      awayId: item.awayId,
      startsAt,
      updatedAt: new Date(now).toISOString(),
      format: item.format,
      status,
      patch: '16.18',
      stage: 'Saison 2026 · Phase finale',
      maps: maps(item.homeId, item.awayId, item.format, status, index),
    };
  });

type WscResult = 'home' | 'away' | null;
type WscFixture = readonly [string, string, string, WscResult, string];

// Schedule checked on SofaScore on 20 September 2026. The five completed
// games retain only the explicit results visible in that source; the rest
// stay scheduled until a source reports a result.
const worldStarSchedule: readonly WscFixture[] = [
  ['2026-09-20T08:00:00+02:00', 'edward-gaming-youth-team', 't1-esports-academy', 'home', 'A'],
  ['2026-09-20T09:00:00+02:00', 'fuego', 'dn-soopers-challengers', 'away', 'A'],
  ['2026-09-20T10:15:00+02:00', 'kt-rolster-challengers', 'bilibili-gaming-junior', 'home', 'B'],
  ['2026-09-20T11:15:00+02:00', 'movistar-koi-fenix', 'ctbc-flying-oyster-academy', 'home', 'B'],
  ['2026-09-20T12:15:00+02:00', 'dn-soopers-challengers', 't1-esports-academy', 'away', 'A'],
  ['2026-09-20T13:15:00+02:00', 'fuego', 'edward-gaming-youth-team', null, 'A'],
  ['2026-09-20T14:15:00+02:00', 'ctbc-flying-oyster-academy', 'bilibili-gaming-junior', null, 'B'],
  ['2026-09-20T15:15:00+02:00', 'movistar-koi-fenix', 'kt-rolster-challengers', null, 'B'],
  ['2026-09-21T08:00:00+02:00', 'vivo-keyd-stars-academy', 'dplus-kia-challengers', null, 'C'],
  ['2026-09-21T09:00:00+02:00', 'fennel', 'cupid-esports', null, 'C'],
  ['2026-09-21T10:00:00+02:00', 'galions', 'saigon-warriors', null, 'D'],
  ['2026-09-21T11:00:00+02:00', 'solary', 'zsk', null, 'D'],
  ['2026-09-21T12:00:00+02:00', 'cupid-esports', 'dplus-kia-challengers', null, 'C'],
  ['2026-09-21T13:00:00+02:00', 'fennel', 'vivo-keyd-stars-academy', null, 'C'],
  ['2026-09-21T14:00:00+02:00', 'zsk', 'saigon-warriors', null, 'D'],
  ['2026-09-21T15:00:00+02:00', 'solary', 'galions', null, 'D'],
  ['2026-09-22T08:00:00+02:00', 'movistar-koi-fenix', 'bilibili-gaming-junior', null, 'B'],
  ['2026-09-22T09:00:00+02:00', 'ctbc-flying-oyster-academy', 'kt-rolster-challengers', null, 'B'],
  ['2026-09-22T10:00:00+02:00', 'fuego', 't1-esports-academy', null, 'A'],
  ['2026-09-22T11:00:00+02:00', 'dn-soopers-challengers', 'edward-gaming-youth-team', null, 'A'],
  ['2026-09-22T12:00:00+02:00', 'kt-rolster-challengers', 'bilibili-gaming-junior', null, 'B'],
  ['2026-09-22T13:00:00+02:00', 'movistar-koi-fenix', 'ctbc-flying-oyster-academy', null, 'B'],
  ['2026-09-22T14:00:00+02:00', 'edward-gaming-youth-team', 't1-esports-academy', null, 'A'],
  ['2026-09-22T15:00:00+02:00', 'fuego', 'dn-soopers-challengers', null, 'A'],
  ['2026-09-24T08:00:00+02:00', 'dn-soopers-challengers', 't1-esports-academy', null, 'A'],
  ['2026-09-24T09:00:00+02:00', 'fuego', 'edward-gaming-youth-team', null, 'A'],
  ['2026-09-24T10:00:00+02:00', 'ctbc-flying-oyster-academy', 'bilibili-gaming-junior', null, 'B'],
  ['2026-09-24T11:00:00+02:00', 'movistar-koi-fenix', 'kt-rolster-challengers', null, 'B'],
  ['2026-09-24T12:00:00+02:00', 'fuego', 't1-esports-academy', null, 'A'],
  ['2026-09-24T13:00:00+02:00', 'dn-soopers-challengers', 'edward-gaming-youth-team', null, 'A'],
  ['2026-09-24T14:00:00+02:00', 'movistar-koi-fenix', 'bilibili-gaming-junior', null, 'B'],
  ['2026-09-24T15:00:00+02:00', 'ctbc-flying-oyster-academy', 'kt-rolster-challengers', null, 'B'],
  ['2026-09-25T08:00:00+02:00', 'cupid-esports', 'dplus-kia-challengers', null, 'C'],
  ['2026-09-25T09:00:00+02:00', 'fennel', 'vivo-keyd-stars-academy', null, 'C'],
  ['2026-09-25T10:00:00+02:00', 'zsk', 'saigon-warriors', null, 'D'],
  ['2026-09-25T11:00:00+02:00', 'solary', 'galions', null, 'D'],
  ['2026-09-25T12:00:00+02:00', 'fennel', 'dplus-kia-challengers', null, 'C'],
  ['2026-09-25T13:00:00+02:00', 'cupid-esports', 'vivo-keyd-stars-academy', null, 'C'],
  ['2026-09-25T14:00:00+02:00', 'solary', 'saigon-warriors', null, 'D'],
  ['2026-09-25T15:00:00+02:00', 'zsk', 'galions', null, 'D'],
];

const worldStarMatches = worldStarSchedule.map(
  ([startsAt, homeSlug, awaySlug, result, group], index): EsportMatch => {
    const home = catalog.teams.find((team) => team.slug === homeSlug);
    const away = catalog.teams.find((team) => team.slug === awaySlug);
    if (!home || !away) throw new Error(`Équipe WSCI absente : ${homeSlug} ou ${awaySlug}`);
    const status: EsportMatch['status'] = result ? 'finished' : 'scheduled';
    return {
      id: `match-wsci-${index + 1}`,
      leagueId: WORLD_STAR_LEAGUE_ID,
      homeId: home.id,
      awayId: away.id,
      startsAt: new Date(startsAt).toISOString(),
      updatedAt: new Date(now).toISOString(),
      format: 'BO1',
      status,
      patch: null,
      stage: `World Star Challengers Invitational · Groupe ${group}`,
      maps: maps(
        home.id,
        away.id,
        'BO1',
        status,
        index + 100,
        result === 'home' ? home.id : result === 'away' ? away.id : null,
      ),
    };
  },
);
const allItems = [...items, ...worldStarMatches];
export const matches = matchesSchema.parse({
  generatedAt: new Date(now).toISOString(),
  items: allItems.filter(
    (item) =>
      ![-3, 3].some((offset) => dayKey(item.startsAt) === shiftDay(dayKey(new Date(now)), offset)),
  ),
});
export const performance = performanceSchema.parse({
  generatedAt: new Date(now).toISOString(),
  items: Array.from({ length: 120 }, (_, i) => {
    const match = items[i % Math.min(10, items.length)]!;
    const startsAt = now - (61 - Math.floor(i / 2)) * 86400000 + (i % 2) * 4 * 3600000;
    return {
      id: `history-${i}`,
      matchId: `history-match-${i}`,
      leagueId: match.leagueId,
      homeId: match.homeId,
      awayId: match.awayId,
      pickId: i % 3 ? match.homeId : match.awayId,
      market: i % 4 ? 'winner' : 'map1',
      observedAt: new Date(startsAt - 6 * 3600000).toISOString(),
      startsAt: new Date(startsAt).toISOString(),
      settledAt: new Date(startsAt + 2 * 3600000).toISOString(),
      probability: 0.54 + (i % 6) * 0.025,
      odds: 1.65 + (i % 7) * 0.08,
      result: i % 29 === 0 ? 'void' : (i * 7) % 13 < 7 ? 'won' : 'lost',
    };
  }),
});
// References are validated here as well as at the HTTP/UI boundary.
for (const match of matches.items) {
  if (
    !catalog.teams.some((t) => t.id === match.homeId) ||
    !catalog.teams.some((t) => t.id === match.awayId)
  )
    throw new Error('Identité de scénario absente.');
}
