import rawCatalog from './data/catalog.json';
import { catalogSchema, opportunitiesSchema } from '@/domain/schemas';
import type { Opportunity } from '@/domain/schemas';
import { dayKey, shiftDay } from '@/features/matches/calendar';
export const catalog = catalogSchema.parse(rawCatalog);
const referenceDate = `${dayKey(new Date())}T08:00:00.000Z`;

// Every pairing, price, probability and time below is fictional. Identities are sourced.
const curated: [string, string, string, number, number][] = [
  ['lck', 'T1', 'GEN', 0.62, 1.75],
  ['lpl', 'BLG', 'TES', 0.67, 1.6],
  ['lec', 'KC', 'G2', 0.56, 1.9],
  ['lfl', 'KCB', 'SLY', 0.58, 1.82],
  ['cblol-brazil', 'FUR', 'PAIN', 0.61, 1.72],
  ['lcs', 'FLY', 'C9', 0.64, 1.63],
  ['lcp', 'CFO', 'GAM', 0.6, 1.72],
  ['lck', 'HLE', 'DK', 0.72, 1.44],
  ['lec', 'FNC', 'VIT', 0.53, 1.95],
  ['lpl', 'JDG', 'WBG', 0.55, 1.88],
];
function makeItem(
  leagueId: string,
  homeId: string,
  awayId: string,
  probability: number,
  odds: number,
  index: number,
  market: Opportunity['market'] = 'winner',
): Opportunity {
  const league = catalog.leagues.find((l) => l.id === leagueId)!;
  const slot = (index - 8) % 14;
  const offset = index < 8 ? 0 : slot < 7 ? slot - 7 : slot - 6;
  const startsAt = new Date(
    Date.parse(`${shiftDay(referenceDate.slice(0, 10), offset)}T08:00:00Z`) +
      ((index % 8) * 60 + 360) * 60_000,
  ).toISOString();
  const lastQuoteAt = Math.min(Date.parse(referenceDate), Date.parse(startsAt) - 3_600_000);
  return {
    id: `demo-${league.slug}-${homeId}-${awayId}-${market}-${startsAt.slice(0, 10)}`,
    leagueId,
    homeId,
    awayId,
    pickId: homeId,
    startsAt,
    format: league.slug === 'lfl' ? 'BO1' : 'BO3',
    market,
    probability,
    bookmaker: 'stake',
    history: (index % 3 === 1
      ? [0.08, 0.08, 0.05, 0.06, 0.03, 0.03, 0.01, 0]
      : [-0.11, -0.11, -0.08, -0.09, -0.05, -0.05, -0.02, 0]
    ).map((delta, point) => ({
      recordedAt: new Date(lastQuoteAt - (7 - point) * 4 * 3_600_000).toISOString(),
      odds: Math.round((odds + delta) * 100) / 100,
    })),
  };
}
const items: Opportunity[] = curated.map(([slug, homeCode, awayCode, probability, odds], index) => {
  const league = catalog.leagues.find((l) => l.slug === slug);
  const home = catalog.teams.find((t) => t.leagueId === league?.id && t.code === homeCode);
  const away = catalog.teams.find((t) => t.leagueId === league?.id && t.code === awayCode);
  if (!league || !home || !away)
    throw new Error(`Identité manquante : ${slug} ${homeCode} ${awayCode}`);
  return makeItem(league.id, home.id, away.id, probability, odds, index);
});
for (const league of catalog.leagues) {
  if (items.some((item) => item.leagueId === league.id)) continue;
  const [home, away] = catalog.teams.filter((t) => t.leagueId === league.id);
  if (!home || !away) continue;
  items.push(
    makeItem(league.id, home.id, away.id, 0.6, 1.71 + (items.length % 5) * 0.01, items.length),
  );
}
const first = items[0]!;
items.push(makeItem(first.leagueId, first.homeId, first.awayId, 0.59, 1.78, 0, 'map1'));
export const opportunities = opportunitiesSchema.parse({
  referenceDate,
  generatedAt: referenceDate,
  items,
});
