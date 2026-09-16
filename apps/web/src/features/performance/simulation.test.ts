import { describe, expect, it } from 'vitest';
import { performanceRecordSchema, performanceSchema, simulate } from './simulation';
import type { PerformanceRecord, SimulationFilters } from './simulation';

const defaults: SimulationFilters = {
  minValue: 0,
  league: 'all',
  teams: [],
  market: 'all',
  days: 0,
};
const base: PerformanceRecord = {
  id: 'a',
  matchId: 'a',
  leagueId: 'l',
  homeId: 'h',
  awayId: 'a',
  pickId: 'h',
  market: 'winner',
  observedAt: '2026-09-01T08:00:00Z',
  startsAt: '2026-09-01T10:00:00Z',
  settledAt: '2026-09-01T12:00:00Z',
  odds: 2,
  probability: 0.6,
  result: 'won',
};
const now = Date.parse('2026-09-16T12:00:00Z');
describe('Simulation historique', () => {
  it('déduit les mises, rembourse les annulations et exclut celles-ci du dénominateur', () => {
    const result = simulate(
      [
        base,
        { ...base, id: 'b', matchId: 'b', result: 'lost' },
        { ...base, id: 'c', matchId: 'c', result: 'void' },
      ],
      defaults,
      10,
      now,
    );
    expect(result.rows.map((r) => r.cumulative)).toEqual([10, 0, 0]);
    expect(result.invested).toBe(20);
    expect(result.roi).toBe(0);
    expect(result.wins).toBe(1);
    expect(result.voids).toBe(1);
  });
  it('arrondit le retour au centime et calcule le rendement sur les mises réglées', () => {
    const result = simulate([{ ...base, odds: 1.755 }], defaults, 10, now);
    expect(result.profit).toBe(7.55);
    expect(result.roi).toBeCloseTo(75.5);
    expect(simulate([{ ...base, probability: 0.999, odds: 1.005 }], defaults, 1, now).profit).toBe(
      0.01,
    );
  });
  it('ne retient pas une value exactement au seuil malgré les arrondis binaires', () => {
    expect(
      simulate([{ ...base, probability: 0.55, odds: 2 }], { ...defaults, minValue: 10 }, 10, now)
        .count,
    ).toBe(0);
  });
  it('combine seuil strict, marché, ligue, sélection et période sans voir le futur', () => {
    const recent = { ...base, settledAt: '2026-09-15T12:00:00Z' };
    expect(
      simulate([recent], { ...defaults, league: 'l', teams: ['h'], days: 7 }, 10, now).count,
    ).toBe(1);
    for (const patch of [
      { league: 'other' },
      { teams: ['a'] },
      { market: 'map1' },
      { minValue: 20 },
    ])
      expect(simulate([recent], { ...defaults, ...patch }, 10, now).count).toBe(0);
    expect(simulate([base], { ...defaults, days: 7 }, 10, now).count).toBe(0);
    expect(
      simulate([{ ...base, settledAt: '2026-09-17T12:00:00Z' }], defaults, 10, now).count,
    ).toBe(0);
  });
  it('rejette le biais temporel, les doublons de marché et les mises invalides', () => {
    expect(
      performanceRecordSchema.safeParse({ ...base, observedAt: '2026-09-01T11:00:00Z' }).success,
    ).toBe(false);
    expect(
      performanceSchema.safeParse({
        generatedAt: new Date(now).toISOString(),
        items: [base, { ...base, id: 'other' }],
      }).success,
    ).toBe(false);
    for (const stake of [0, -10, NaN, Infinity, 100001])
      expect(() => simulate([base], defaults, stake, now)).toThrow();
  });
  it('ordonne les règlements sans modifier l’entrée, y compris sans résultat', () => {
    const records = [{ ...base, id: 'b', settledAt: '2026-09-02T12:00:00Z' }, base];
    expect(simulate(records, defaults, 10, now).rows.map((r) => r.record.id)).toEqual(['a', 'b']);
    expect(records[0]!.id).toBe('b');
    expect(simulate([], defaults, 10, now)).toMatchObject({
      rows: [],
      profit: 0,
      roi: 0,
      count: 0,
    });
  });
});
