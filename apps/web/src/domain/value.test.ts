import { describe, expect, it } from 'vitest';
import { expectedValue, fairOdds, currentQuote, oddsChange, valueOf } from './value';
import { opportunities } from '@/mocks/fixtures';
describe('Value et cotes', () => {
  it('calcule une espérance positive, nulle ou négative sans arrondir prématurément', () => {
    expect(expectedValue(0.6, 1.8)).toBeCloseTo(8);
    expect(expectedValue(0.5, 2)).toBe(0);
    expect(expectedValue(0.4, 2)).toBeCloseTo(-20);
    expect(expectedValue(0.62, 1.75)).toBeCloseTo(8.5);
  });
  it('rejette les entrées hors du domaine', () => {
    for (const [probability, odds] of [
      [-1, 2],
      [1.1, 2],
      [0.5, 1],
      [NaN, 2],
      [0.5, Infinity],
    ])
      expect(() => expectedValue(probability!, odds!)).toThrow(RangeError);
  });
  it('la cote juste annule la value', () =>
    expect(expectedValue(0.64, fairOdds(0.64))).toBeCloseTo(0));
  it('utilise la cote la plus récente même si elle baisse sous le premier relevé', () => {
    const item = {
      ...opportunities.items[0]!,
      probability: 0.6,
      history: [
        { recordedAt: '2026-09-13T08:00:00.000Z', odds: 2 },
        { recordedAt: '2026-09-14T09:00:00.000Z', odds: 1.8 },
      ],
    };
    expect(currentQuote(item).odds).toBe(1.8);
    expect(oddsChange(item)).toBeCloseTo(-0.2);
    expect(valueOf(item)).toBeCloseTo(8);
  });
  it('accepte le premier relevé sans inventer de variation', () => {
    const item = {
      ...opportunities.items[0]!,
      history: [{ recordedAt: '2026-09-14T09:00:00.000Z', odds: 1.75 }],
    };
    expect(oddsChange(item)).toBe(0);
    expect(currentQuote(item).odds).toBe(1.75);
  });
});
