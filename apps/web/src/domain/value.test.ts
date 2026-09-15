import { describe, expect, it } from 'vitest';
import { expectedValue, fairOdds, bestOffer } from './value';
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
  it('sélectionne la meilleure offre même lorsque la liste est inversée', () => {
    const item = opportunities.items[0]!;
    expect(bestOffer({ ...item, offers: [...item.offers].reverse() }).odds).toBe(1.75);
  });
});
