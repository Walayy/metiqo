import { z } from 'zod';
import { expectedValue } from '@/domain/value';

export const performanceRecordSchema = z
  .object({
    id: z.string(),
    matchId: z.string(),
    leagueId: z.string(),
    homeId: z.string(),
    awayId: z.string(),
    pickId: z.string(),
    market: z.enum(['winner', 'map1']),
    observedAt: z.iso.datetime({ offset: true }),
    startsAt: z.iso.datetime({ offset: true }),
    settledAt: z.iso.datetime({ offset: true }),
    probability: z.number().gt(0).lt(1),
    odds: z.number().gt(1),
    result: z.enum(['won', 'lost', 'void']),
  })
  .refine(
    (r) =>
      r.homeId !== r.awayId &&
      [r.homeId, r.awayId].includes(r.pickId) &&
      Date.parse(r.observedAt) < Date.parse(r.startsAt) &&
      Date.parse(r.startsAt) <= Date.parse(r.settledAt),
    'La sélection et les dates de décision/règlement doivent être cohérentes.',
  );
export const performanceSchema = z
  .object({
    generatedAt: z.iso.datetime({ offset: true }),
    items: z.array(performanceRecordSchema),
  })
  .refine(
    (data) =>
      new Set(data.items.map((r) => `${r.matchId}:${r.market}`)).size === data.items.length &&
      new Set(data.items.map((r) => r.id)).size === data.items.length,
    'Identifiants uniques et un seul engagement par marché et rencontre.',
  );
export type PerformanceRecord = z.infer<typeof performanceRecordSchema>;
export interface SimulationFilters {
  minValue: number;
  league: string;
  teams: string[];
  market: string;
  days: number;
}
export function simulate(
  records: PerformanceRecord[],
  filters: SimulationFilters,
  stake: number,
  now: number,
) {
  if (
    !Number.isFinite(stake) ||
    stake < 0.01 ||
    stake > 100000 ||
    !Number.isFinite(filters.minValue)
  )
    throw new RangeError('Paramètres de simulation invalides.');
  const selected = records
    .filter(
      (r) =>
        expectedValue(r.probability, r.odds) - filters.minValue >
          Number.EPSILON * 100 * Math.max(1, Math.abs(filters.minValue)) &&
        (filters.league === 'all' || r.leagueId === filters.league) &&
        (!filters.teams.length || filters.teams.includes(r.pickId)) &&
        (filters.market === 'all' || r.market === filters.market) &&
        Date.parse(r.settledAt) <= now &&
        (!filters.days || Date.parse(r.settledAt) >= now - filters.days * 86400000),
    )
    .sort((a, b) => Date.parse(a.settledAt) - Date.parse(b.settledAt) || a.id.localeCompare(b.id));
  const stakeCents = Math.round(stake * 100);
  let cumulative = 0;
  const rows = selected.map((record) => {
    const profitCents =
      record.result === 'won'
        ? Math.round(stakeCents * record.odds * (1 + Number.EPSILON)) - stakeCents
        : record.result === 'lost'
          ? -stakeCents
          : 0;
    cumulative += profitCents;
    return { record, profit: profitCents / 100, cumulative: cumulative / 100 };
  });
  const settled = selected.filter((r) => r.result !== 'void');
  const invested = (settled.length * stakeCents) / 100;
  return {
    rows,
    profit: cumulative / 100,
    invested,
    roi: invested ? cumulative / invested : 0,
    wins: settled.filter((r) => r.result === 'won').length,
    count: settled.length,
    voids: selected.length - settled.length,
  };
}
