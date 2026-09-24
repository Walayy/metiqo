import { describe, expect, it } from 'vitest';
import { readExplorerLocation, writeExplorerLocation } from './explorer-location';
import { filterValues } from './filter';
import { catalog, opportunities } from '@/mocks/fixtures';

describe('Contexte partagé dans l’URL', () => {
  it('ouvre Matchs par défaut et conserve une URL explicite pour les values', () => {
    const home = readExplorerLocation(new URLSearchParams());
    expect(home.view).toBe('matches');
    expect(writeExplorerLocation(new URLSearchParams(), home).get('view')).toBeNull();
    const values = readExplorerLocation(new URLSearchParams('view=values'));
    expect(values.view).toBe('values');
    expect(writeExplorerLocation(new URLSearchParams(), values).get('view')).toBe('values');
    expect(readExplorerLocation(new URLSearchParams('view=unknown')).view).toBe('matches');
  });
  it('restaure la vue, les filtres, le tri, la page et un détail sans perdre un paramètre externe', () => {
    const original = new URLSearchParams(
      'mock=slow&view=values&league=ligue-ouverte&team=equipe-ouverte&market=map1&min=4&q=Gen.G&sort=probability&page=3&detail=match-42',
    );
    const state = readExplorerLocation(original);
    expect(state).toMatchObject({
      view: 'values',
      page: 3,
      search: 'Gen.G',
      sort: 'probability',
      selectedId: 'match-42',
      detailOpen: true,
      filters: { league: 'ligue-ouverte', team: 'equipe-ouverte', market: 'map1', minValue: 4 },
    });
    const restored = writeExplorerLocation(original, state);
    expect(restored.get('mock')).toBe('slow');
    expect(readExplorerLocation(restored)).toEqual(state);
  });
  it('borne les valeurs non valides sans fermer les identifiants de ligues et équipes', () => {
    const state = readExplorerLocation(
      new URLSearchParams(
        'page=-4&min=Infinity&sort=unknown&market=unknown&period=unknown&league=future-league',
      ),
    );
    expect(state).toMatchObject({
      page: 1,
      sort: 'value',
      filters: { minValue: 0, market: 'all', period: 'all', league: 'future-league' },
    });
    expect(readExplorerLocation(new URLSearchParams('page=1.5&min=16')).page).toBe(1);
  });
  it('retire le détail fermé de l’URL même si son contenu reste monté pour la transition', () => {
    const params = new URLSearchParams('page=2&detail=match-42');
    const state = { ...readExplorerLocation(params), detailOpen: false };
    expect(writeExplorerLocation(params, state).get('detail')).toBeNull();
    expect(writeExplorerLocation(params, state).get('page')).toBe('2');
  });
  it('le filtre équipe retrouve ses deux côtés et ne confond pas un nom partiel avec son identifiant', () => {
    const item = opportunities.items[0]!;
    for (const team of [item.homeId, item.awayId]) {
      const state = readExplorerLocation(new URLSearchParams({ team }));
      const rows = filterValues(
        opportunities.items,
        catalog,
        state.filters,
        '',
        'value',
        opportunities.referenceDate,
      );
      expect(rows.some((row) => row.id === item.id)).toBe(true);
      expect(rows.every((row) => row.homeId === team || row.awayId === team)).toBe(true);
    }
    const state = readExplorerLocation(new URLSearchParams('team=unknown-team'));
    expect(
      filterValues(
        opportunities.items,
        catalog,
        state.filters,
        '',
        'value',
        opportunities.referenceDate,
      ),
    ).toEqual([]);
  });
});
