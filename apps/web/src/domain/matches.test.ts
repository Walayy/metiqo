import { describe, expect, it } from 'vitest';
import { matches, performance } from '@/mocks/esport';
import { catalog } from '@/mocks/fixtures';
import { countdown, matchSchema, seriesScore, sideKills } from './matches';
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
  it('affiche un décompte sans nombre négatif ni direct inféré', () => {
    const at = '2026-09-16T12:00:00Z';
    expect(countdown(at, Date.parse(at) - 65000)).toBe('Dans 1 min 05 s');
    expect(countdown(at, Date.parse(at) + 1000)).toBe('Début attendu');
    expect(countdown(at, Date.parse(at) - 3660000)).toBe('Dans 1 h 01');
  });
});
