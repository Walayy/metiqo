import { describe, expect, it } from 'vitest';
import { oddsHistorySchema, opportunitySchema } from './schemas';
import { opportunities } from '@/mocks/fixtures';

describe('Contrat du suivi Stake', () => {
  const first = { recordedAt: '2026-09-13T23:55:00.000Z', odds: 1.8 };
  const last = { recordedAt: '2026-09-14T02:10:00.000Z', odds: 1.7 };
  it('accepte un suivi sur plusieurs jours avec des intervalles irréguliers', () => {
    expect(oddsHistorySchema.safeParse([first, last]).success).toBe(true);
  });
  it('accepte une cote inchangée à une nouvelle date', () => {
    expect(oddsHistorySchema.safeParse([first, { ...last, odds: first.odds }]).success).toBe(true);
  });
  it('refuse les dates inversées, dupliquées, absentes et les historiques vides', () => {
    for (const history of [
      [],
      [last, first],
      [first, first],
      [{ odds: 1.8 }],
      [{ ...first, recordedAt: '08:00' }],
    ]) {
      expect(oddsHistorySchema.safeParse(history).success).toBe(false);
    }
  });
  it('refuse les cotes non exploitables', () => {
    for (const odds of [0, 1, -1, NaN, Infinity])
      expect(oddsHistorySchema.safeParse([{ ...first, odds }]).success).toBe(false);
  });
  it('refuse une source autre que Stake et les anciens contrats multi-bookmakers', () => {
    const item = opportunities.items[0]!;
    expect(opportunitySchema.safeParse({ ...item, bookmaker: 'unibet' }).success).toBe(false);
    expect(
      opportunitySchema.safeParse({
        ...item,
        bookmaker: undefined,
        offers: [{ bookmaker: 'Stake', odds: 1.75 }],
      }).success,
    ).toBe(false);
  });
});
