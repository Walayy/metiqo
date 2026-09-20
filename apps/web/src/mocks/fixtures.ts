import rawCatalog from './data/catalog.json';
import { catalogSchema, opportunitiesSchema } from '@/domain/schemas';
import type { Opportunity } from '@/domain/schemas';
import { dayKey, shiftDay } from '@/features/matches/calendar';

// SofaScore and Riot expose the WSCI as a cross-region tournament, not as
// LCK CL. These identities are kept separate so the mock follows the same
// competition boundary as the real API.
export const WORLD_STAR_LEAGUE_ID = 'sofascore:tournament:37525';
const worldStarTeams = [
  {
    id: 'sofascore:team:edward-gaming-youth-team',
    slug: 'edward-gaming-youth-team',
    name: 'EDward Gaming Youth Team',
    code: 'EDG.Y',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/6cdce7934ff16693ac61ba5c4bece5be981e3ec33f9066e8eb79247f5472f678.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:t1-esports-academy',
    slug: 't1-esports-academy',
    name: 'T1 Esports Academy',
    code: 'T1.EA',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/1691bad188725e2ed4f96a5ed205a0f079bdaa1a3fd4cc84b230992ca8657446.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:fuego',
    slug: 'fuego',
    name: 'Fuego',
    code: 'FUE',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/ebeb8c10fa75dde4ec2afc0a6e476123f2f62d6755f46adec21caccc45e4d9ed.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:dn-soopers-challengers',
    slug: 'dn-soopers-challengers',
    name: 'DN SOOPers Challengers',
    code: 'DNS.C',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/1272dab6ec63368e25c843adf14bad8b635861fdacb07d4aaa343e019f806883.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:kt-rolster-challengers',
    slug: 'kt-rolster-challengers',
    name: 'KT Rolster Challengers',
    code: 'KT.C',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/813dae98e508549de700e26d49ed4118fc80b011f1596d3b5a4320dcc8631bd8.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:bilibili-gaming-junior',
    slug: 'bilibili-gaming-junior',
    name: 'Bilibili Gaming Junior',
    code: 'BLG.J',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/9c1865c3bc241e00878ef7c68637f2c3a15c351a8e212443f3dd5e642c3b8645.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:movistar-koi-fenix',
    slug: 'movistar-koi-fenix',
    name: 'Movistar KOI Fénix',
    code: 'MKF',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/23b293c28ac1f75498df37adde131d47ba00c42176d80dddeb583ee0ec11cdd4.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:ctbc-flying-oyster-academy',
    slug: 'ctbc-flying-oyster-academy',
    name: 'CTBC Flying Oyster Academy',
    code: 'CFO.A',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/6890791525e832bc05c5ccfb7c8696f6c25f10b237928b0a847a160d12016d6b.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:dplus-kia-challengers',
    slug: 'dplus-kia-challengers',
    name: 'Dplus KIA Challengers',
    code: 'DK.C',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/e50cc75515c06eec0f3c853a0ea19acd5a2b7c061e6dfdb94570d54140cd80aa.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:vivo-keyd-stars-academy',
    slug: 'vivo-keyd-stars-academy',
    name: 'Vivo Keyd Stars Academy',
    code: 'VKS.A',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/75483a90f4286ea66e61208eea926e47000c68f1ea749672842274417cbdf9eb.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:fennel',
    slug: 'fennel',
    name: 'FENNEL',
    code: 'FL',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/bff4e6fbb18420f9148f014aad2735b773b513d822ee38ed0e2f438ca6ddb7b1.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:cupid-esports',
    slug: 'cupid-esports',
    name: 'Cupid Esports',
    code: 'CPD',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/177df1c9a34e1888cda7b267302dbf187607c0120b586a297ce4c741ff3d7745.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:galions',
    slug: 'galions',
    name: 'Galions',
    code: 'GL',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/a4a3e949125a4769fff51144e2d2844d4607289a3b0772352295618cea31b96f.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:saigon-warriors',
    slug: 'saigon-warriors',
    name: 'Saigon Warriors',
    code: 'SGW',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/6f963edfb6e6037602d5ddfc01b055c7e9df8287fa1ef1788d74e0d820037b08.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:solary',
    slug: 'solary',
    name: 'Solary',
    code: 'SLY',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/9d558e37d1734ead28c9f5b964183af886c4b09e8bc93c87ff459d9c1f1d15cd.webp',
    sourceImage: '',
  },
  {
    id: 'sofascore:team:zsk',
    slug: 'zsk',
    name: 'ZSK',
    code: 'ZSK',
    leagueId: WORLD_STAR_LEAGUE_ID,
    image: '/api/v1/catalog/logos/26ce386aabfbb379a4a7580097d64bc04e4607be8a4d3606954baf7890be0b92.webp',
    sourceImage: '',
  },
] as const;
export const catalog = catalogSchema.parse({
  ...rawCatalog,
  leagues: [
    ...rawCatalog.leagues,
    {
      id: WORLD_STAR_LEAGUE_ID,
      slug: 'world-star-challengers-invitational-2026',
      name: 'World Star Challengers Invitational',
      region: 'INTERNATIONAL',
      image: '/api/v1/catalog/logos/d1893c739b023747318e2b11ff376aa9763a27160f5b18575631bf9fde634325.webp',
      sourceImage: 'http://static.lolesports.com/leagues/1788259526036_WSCIlogo_1-061.png',
      tier: 'international',
    },
  ],
  teams: [...rawCatalog.teams, ...worldStarTeams],
});
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
  if (league.id === WORLD_STAR_LEAGUE_ID) continue;
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
