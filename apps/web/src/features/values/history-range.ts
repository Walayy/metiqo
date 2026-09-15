import type { Opportunity } from '@/domain/schemas';

export type HistoryPeriod = 'all' | '24h' | '7d';
export function historyInPeriod(history: Opportunity['history'], period: HistoryPeriod) {
  const latest = history.at(-1);
  if (!latest || period === 'all') return history;
  const since = Date.parse(latest.recordedAt) - (period === '24h' ? 24 : 168) * 3_600_000;
  return history.filter((point) => Date.parse(point.recordedAt) >= since);
}
