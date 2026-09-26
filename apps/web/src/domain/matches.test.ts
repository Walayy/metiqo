import { describe, expect, it } from 'vitest';
import { matches, performance } from '@/mocks/esport';
import { catalog } from '@/mocks/fixtures';
import { countdown, matchSchema, matchWinnerId, seriesScore, sideKills, sideGold } from './matches';
import { performanceSchema } from '@/features/performance/simulation';
import { expectedValue } from './value';
describe('Rencontres et données de simulation', () => {
  const live = matches.items.find((m) => m.status === 'live')!;
  it('conserve le score administratif d’un forfait sans inventer de cartes ni de vainqueur sportif', () => {
    const walkover = matchSchema.parse({
      ...live,
      status: 'walkover',
      maps: [],
      seriesScore: { home: 1, away: 0 },
      currentScore: { home: 1, away: 0 },
    });
    expect(seriesScore(walkover, walkover.homeId)).toBe(1);
    expect(matchWinnerId(walkover)).toBeNull();
    expect(matchSchema.safeParse({ ...walkover, maps: live.maps }).success).toBe(false);
    expect(matchSchema.safeParse({ ...walkover, seriesScore: { home: 3, away: 0 } }).success).toBe(
      true,
    );
  });
  it('conserve un format inconnu sans déduire de vainqueur ou de cartes manquantes', () => {
    const finished = matches.items.find((m) => m.status === 'finished')!;
    const partial = {
      ...finished,
      format: null,
      maps: finished.maps.filter((m) => m.status === 'finished'),
    };
    expect(matchSchema.safeParse(partial).success).toBe(true);
    expect(matchWinnerId(partial)).toBeNull();
    expect(
      matchSchema.safeParse({ ...partial, maps: [{ ...partial.maps[0], number: 6 }] }).success,
    ).toBe(false);
  });
  it('dérive le score des cartes terminées uniquement', () => {
    expect(seriesScore(live, live.homeId)).toBe(1);
    expect(seriesScore(live, live.awayId)).toBe(0);
    expect(live.maps.filter((m) => m.status === 'live')).toHaveLength(1);
    expect(matchSchema.safeParse({ ...live, status: 'finished' }).success).toBe(false);
    expect(matchSchema.safeParse({ ...live, startsAt: '2026-09-16T14:00:00+02:00' }).success).toBe(
      true,
    );
  });
  it('vérifie les références, joueurs, rôles et comptes cohérents du scénario', () => {
    expect(new Set(matches.items.map((m) => m.id)).size).toBe(matches.items.length);
    for (const match of matches.items) {
      expect(matchSchema.safeParse(match).success).toBe(true);
      expect(catalog.leagues.some((l) => l.id === match.leagueId)).toBe(true);
      for (const map of match.maps)
        for (const side of map.sides) {
          expect(catalog.teams.some((t) => t.id === side.teamId)).toBe(true);
          const opponent = map.sides.find((s) => s.teamId !== side.teamId)!;
          expect(sideKills(side)).toBe(opponent.players.reduce((sum, p) => sum + p.deaths, 0));
        }
    }
    expect(performanceSchema.safeParse(performance).success).toBe(true);
  });
  it('valide les deux issues Stake, les suspensions et une value du même résultat', () => {
    const match = matches.items.find((item) => item.oddsMarkets?.length)!;
    const market = match.oddsMarkets![0]!;
    expect(matchSchema.safeParse(match).success).toBe(true);
    expect(market.selections).toHaveLength(2);

    const value = matches.items
      .flatMap((item) => item.oddsMarkets ?? [])
      .flatMap((item) => item.selections)
      .find((selection) => selection.probability !== null);
    expect(value).toBeDefined();
    expect(expectedValue(value!.probability!, value!.odds!)).toBeGreaterThan(0);

    const suspended = matches.items
      .flatMap((item) => item.oddsMarkets ?? [])
      .flatMap((item) => item.selections)
      .find((selection) => selection.suspended);
    expect(suspended).toMatchObject({ odds: null, probability: null, suspended: true });
    expect(
      matchSchema.safeParse({
        ...match,
        oddsMarkets: [
          {
            ...market,
            selections: [
              { ...market.selections[0], suspended: true, odds: null },
              market.selections[1],
            ],
          },
        ],
      }).success,
    ).toBe(true);
  });
  it('distingue les phases sans attribuer de value actuelle à une cote historique', () => {
    const live = matches.items.find((item) => item.status === 'live' && item.oddsMarkets?.length)!;
    const before = live.oddsMarkets!.find((market) => market.phase === 'prematch')!;
    const during = live.oddsMarkets!.find((market) => market.phase === 'live')!;
    expect(before.historical).toBe(true);
    expect(during.historical).toBe(false);
    expect(Date.parse(before.observedAt)).toBeLessThan(Date.parse(during.observedAt));
    expect(
      matchSchema.safeParse({
        ...live,
        oddsMarkets: [
          {
            ...before,
            selections: before.selections.map((pick) => ({ ...pick, probability: 0.6 })),
          },
        ],
      }).success,
    ).toBe(false);
    expect(
      matchSchema.safeParse({ ...live, oddsMarkets: [{ ...during, phase: 'unknown' }] }).success,
    ).toBe(false);
    expect(matchSchema.safeParse({ ...live, oddsMarkets: [before, before] }).success).toBe(false);
  });
  it('expose les issues réglées des sélections historiques sans les confondre avec les prix', () => {
    const finished = matches.items.find(
      (item) =>
        item.status === 'finished' &&
        item.oddsMarkets?.some((market) =>
          market.selections.some((pick) => pick.result === 'void'),
        ),
    )!;
    expect(finished).toBeDefined();
    expect(finished.oddsMarkets!.every((market) => market.historical)).toBe(true);
    expect(
      finished
        .oddsMarkets!.flatMap((market) => market.selections)
        .some((pick) => pick.result === 'lost'),
    ).toBe(true);
    expect(
      finished
        .oddsMarkets!.flatMap((market) => market.selections)
        .some((pick) => pick.result === 'void'),
    ).toBe(true);
  });
  it('expose le vainqueur de série et les bans uniquement pour les cartes commencées', () => {
    const finished = matches.items.find((m) => m.status === 'finished')!;
    expect(matchWinnerId(finished)).toBeTruthy();
    expect(
      finished.maps
        .filter((map) => map.status === 'finished')
        .every((map) => map.bans.length === 10),
    ).toBe(true);
    expect(
      matches.items
        .flatMap((match) => match.maps)
        .filter((map) => map.status === 'scheduled')
        .every((map) => map.bans.length === 0),
    ).toBe(true);
  });
  it('refuse les cartes incohérentes, les côtés identiques et les faux vainqueurs', () => {
    const finished = live.maps[0]!;
    for (const map of [
      { ...finished, number: 5 },
      { ...finished, winnerId: 'unknown' },
      { ...finished, status: 'scheduled' },
      { ...finished, sides: finished.sides.map((s) => ({ ...s, side: 'blue' })) },
    ])
      expect(matchSchema.safeParse({ ...live, maps: [map] }).success).toBe(false);
  });
  it('conserve explicitement les statistiques que la source ne publie pas encore', () => {
    const sourceMap = live.maps[0]!;
    const partial = {
      ...sourceMap,
      durationSeconds: null,
      bans: [],
      sides: sourceMap.sides.map((side) => ({
        ...side,
        heralds: null,
        grubs: null,
        players: side.players.map((player) => ({ ...player, gold: null })),
      })),
    };
    expect(matchSchema.safeParse({ ...live, maps: [partial, ...live.maps.slice(1)] }).success).toBe(
      true,
    );
  });
  it('accepte un score final sourcé avec des cartes partiellement publiées', () => {
    const map = live.maps[0]!;
    const result = {
      ...live,
      format: 'BO3',
      status: 'finished',
      currentScore: { home: 2, away: 0 },
      seriesScore: { home: 2, away: 0 },
      maps: [{ ...map, number: 2, winnerId: live.homeId }],
    };
    const parsed = matchSchema.parse(result);
    expect(matchWinnerId(parsed)).toBe(live.homeId);
    expect(seriesScore(parsed, live.homeId)).toBe(2);
    expect(matchSchema.safeParse({ ...result, seriesScore: { home: 1, away: 0 } }).success).toBe(
      false,
    );
  });
  it('conserve les côtés et totaux inconnus sans inventer de zéro', () => {
    const map = live.maps[0]!;
    const sides = map.sides.map((side) => ({ ...side, side: null, players: [] }));
    expect(
      matchSchema.safeParse({ ...live, maps: [{ ...map, sides }, ...live.maps.slice(1)] }).success,
    ).toBe(true);
    expect(sideGold(sides[0]!)).toBeNull();
    expect(sideKills(sides[0]!)).toBeNull();
  });
  it('affiche un décompte sans nombre négatif ni direct inféré', () => {
    const at = '2026-09-16T12:00:00Z';
    expect(countdown(at, Date.parse(at) - 65000)).toBe('Dans 1 min 05 s');
    expect(countdown(at, Date.parse(at) + 1000)).toBe('Début attendu');
    expect(countdown(at, Date.parse(at) - 3660000)).toBe('Dans 1 h 01');
  });
  it('conserve les dix bans visibles même si leurs portraits ne sont pas tous identifiés', () => {
    const map = live.maps[0]!;
    const bans = map.bans.map((ban) => ({ ...ban, champion: null }));
    const partial = { ...live, maps: [{ ...map, bans }, ...live.maps.slice(1)] };
    expect(matchSchema.parse(partial).maps[0]!.bans).toHaveLength(10);
    partial.maps[0]!.bans[0]!.championImage = '';
    expect(matchSchema.safeParse(partial).success).toBe(false);
  });
});
