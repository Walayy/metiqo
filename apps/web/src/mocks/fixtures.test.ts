import { describe, expect, it } from 'vitest';
import { catalog, opportunities } from './fixtures';
import { valueOf, currentQuote } from '@/domain/value';
import { filterValues } from '@/features/values/filter';
import { defaultFilters } from '@/features/values/filter-state';
describe('Contrat du scénario LoL', () => {
  it('possède des identifiants uniques et des références cohérentes', () => {
    for (const list of [catalog.leagues, catalog.teams, opportunities.items])
      expect(new Set(list.map((x) => x.id)).size).toBe(list.length);
    for (const item of opportunities.items) {
      expect(catalog.leagues.some((l) => l.id === item.leagueId)).toBe(true);
      for (const id of [item.homeId, item.awayId, item.pickId])
        expect(catalog.teams.some((t) => t.id === id)).toBe(true);
      expect([item.homeId, item.awayId]).toContain(item.pickId);
      expect(item.homeId).not.toBe(item.awayId);
      expect(valueOf(item)).toBeGreaterThan(0);
      expect(item.history.at(-1)?.odds).toBe(currentQuote(item).odds);
    }
  });
  it('inclut les six ligues majeures et la LFL avec leurs identités locales', () => {
    for (const slug of ['lck', 'lpl', 'lec', 'lcs', 'cblol-brazil', 'lcp', 'lfl']) {
      const league = catalog.leagues.find((l) => l.slug === slug)!;
      expect(league).toBeDefined();
      expect(catalog.teams.filter((t) => t.leagueId === league.id).length).toBeGreaterThanOrEqual(
        8,
      );
      expect(league.image).toMatch(/^\/logos\/\d+\.webp$/);
    }
  });
  it('combine recherche, ligue, marché, seuil et favoris', () => {
    const item = opportunities.items[0]!;
    const result = filterValues(
      opportunities.items,
      catalog,
      { ...defaultFilters, league: item.leagueId, market: 'winner', minValue: 8 },
      'gen.g',
      [item.id],
      true,
      'value',
      opportunities.referenceDate,
    );
    expect(result.map((i) => i.id)).toEqual([item.id]);
  });
  it('ne crée aucune opportunité quand la sélection ne correspond pas', () => {
    expect(
      filterValues(
        opportunities.items,
        catalog,
        { ...defaultFilters, minValue: 15 },
        '',
        [],
        false,
        'value',
        opportunities.referenceDate,
      ),
    ).toEqual([]);
    expect(
      filterValues(
        opportunities.items,
        catalog,
        defaultFilters,
        'introuvable',
        [],
        false,
        'value',
        opportunities.referenceDate,
      ),
    ).toEqual([]);
  });
  it('trie sur les valeurs brutes et change de tri sans modifier les fixtures', () => {
    const sorted = filterValues(
      opportunities.items,
      catalog,
      defaultFilters,
      '',
      [],
      false,
      'value',
      opportunities.referenceDate,
    );
    expect(sorted[0]?.id).toBe(opportunities.items[0]?.id);
    expect(
      sorted.every((item, index) => !index || valueOf(sorted[index - 1]!) >= valueOf(item)),
    ).toBe(true);
    const chronological = filterValues(
      opportunities.items,
      catalog,
      defaultFilters,
      '',
      [],
      false,
      'time',
      opportunities.referenceDate,
    );
    expect(
      chronological.every(
        (item, index) =>
          !index || Date.parse(chronological[index - 1]!.startsAt) <= Date.parse(item.startsAt),
      ),
    ).toBe(true);
  });
});
