import { describe, expect, it } from 'vitest';
import { matches, performance } from '@/mocks/esport';
import { catalog } from '@/mocks/fixtures';
import { countdown, matchSchema, matchWinnerId, seriesScore, sideKills, sideGold } from './matches';
import { performanceSchema } from '@/features/performance/simulation';
describe('Rencontres et données de simulation', () => {
  const live = matches.items.find((m) => m.status === 'live')!;
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
