import { describe, expect, it } from 'vitest';
import { historyInPeriod } from './history-range';

describe('Périodes de suivi', () => {
  const history = [
    { recordedAt: '2026-09-01T10:00:00Z', odds: 1.6 },
    { recordedAt: '2026-09-07T10:00:00Z', odds: 1.7 },
    { recordedAt: '2026-09-13T09:59:59Z', odds: 1.8 },
    { recordedAt: '2026-09-13T10:00:00Z', odds: 1.9 },
    { recordedAt: '2026-09-14T10:00:00Z', odds: 2 },
  ];
  it('ancre la fenêtre au dernier relevé et inclut exactement sa borne', () => {
    expect(historyInPeriod(history, '24h').map((p) => p.odds)).toEqual([1.9, 2]);
    expect(historyInPeriod(history, '7d').map((p) => p.odds)).toEqual([1.7, 1.8, 1.9, 2]);
    expect(historyInPeriod(history, 'all')).toHaveLength(5);
  });
  it('conserve un premier relevé isolé sans inventer de point', () => {
    expect(historyInPeriod([history[0]!], '24h')).toEqual([history[0]]);
  });
});
