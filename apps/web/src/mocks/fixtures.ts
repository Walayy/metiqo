import rawCatalog from './data/catalog.json';
import { catalogSchema, opportunitiesSchema } from '@/domain/schemas';
import type { Opportunity } from '@/domain/schemas';
export const catalog = catalogSchema.parse(rawCatalog);
const scenarioDate = '2026-09-14T08:00:00.000Z';

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
const bookmakerNames = ['Pinnacle', 'Unibet', 'Betway'];
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
  const startsAt = new Date(
    Date.parse(scenarioDate) + ((index % 8) * 60 + 360) * 60_000 + (index >= 8 ? 86_400_000 : 0),
  ).toISOString();
  const bookmakers = [...bookmakerNames.slice(index % 3), ...bookmakerNames.slice(0, index % 3)];
  return {
    id: `demo-${league.slug}-${homeId}-${awayId}-${market}`,
    leagueId,
    homeId,
    awayId,
    pickId: homeId,
    startsAt,
    format: league.slug === 'lfl' ? 'BO1' : 'BO3',
    market,
    probability,
    offers: bookmakers.map((bookmaker, i) => ({
      bookmaker,
      odds: Math.round((odds - i * 0.04) * 100) / 100,
    })),
    history: [
      { label: '08:00', odds: odds - 0.11 },
      { label: '09:00', odds: odds - 0.11 },
      { label: '10:00', odds: odds - 0.08 },
      { label: '11:00', odds: odds - 0.09 },
      { label: '12:00', odds: odds - 0.05 },
      { label: '13:00', odds: odds - 0.05 },
      { label: '14:00', odds: odds - 0.02 },
      { label: '15:00', odds },
    ],
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
  scenarioDate,
  generatedAt: scenarioDate,
  items,
});
