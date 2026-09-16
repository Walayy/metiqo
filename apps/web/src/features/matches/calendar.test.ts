import { describe, expect, it } from 'vitest';
import { boundedDay, dailyMatches, dayKey, shiftDay, validDay } from './calendar';
import { catalog, opportunities } from '@/mocks/fixtures';
import { readExplorerLocation, writeExplorerLocation } from '@/features/values/explorer-location';

describe('Journées du calendrier', () => {
  it('utilise les minuits de Paris, y compris au changement d’heure', () => {
    expect(dayKey('2026-09-15T22:05:00Z')).toBe('2026-09-16');
    expect(dayKey('2026-10-24T22:30:00Z')).toBe('2026-10-25');
    expect(dayKey('2026-10-25T23:05:00Z')).toBe('2026-10-26');
    expect(shiftDay('2026-03-29', -1)).toBe('2026-03-28');
    expect(shiftDay('2026-10-25', 1)).toBe('2026-10-26');
  });
  it('borne les dates à sept jours dans chaque sens et valide les dates civiles', () => {
    expect(boundedDay('2026-08-01', '2026-09-16')).toBe('2026-09-09');
    expect(boundedDay('2026-12-01', '2026-09-16')).toBe('2026-09-23');
    expect(boundedDay('', '2026-09-16')).toBe('2026-09-16');
    expect(validDay('2026-02-30')).toBe(false);
    expect(validDay('2026-13-01')).toBe(false);
    expect(shiftDay('2026-12-31', 1)).toBe('2027-01-01');
  });
  it('regroupe les marchés, conserve les rencontres répétées et trie les horaires', () => {
    const item = { ...opportunities.items[0]!, startsAt: '2026-09-15T22:10:00Z' };
    const second = { ...item, id: 'other-market', market: 'map1' as const };
    const repeat = { ...item, id: 'repeat', startsAt: '2026-09-16T16:00:00Z' };
    const outside = { ...item, id: 'outside', startsAt: '2026-09-15T21:59:00Z' };
    const matches = dailyMatches([repeat, item, second, outside], '2026-09-16', catalog, 'all', '');
    expect(matches).toHaveLength(2);
    expect(matches[0]?.markets.map((market) => market.id)).toEqual([item.id, second.id]);
    expect(matches[1]?.first.id).toBe('repeat');
    expect(dailyMatches([item], '2026-09-16', catalog, 'unknown-league', '')).toEqual([]);
    expect(dailyMatches([item], '2026-09-16', catalog, 'all', 'introuvable')).toEqual([]);
  });
  it('restaure la vue et la date dans un lien partagé, sans accepter une date impossible', () => {
    const params = new URLSearchParams('view=matches&date=2026-09-16');
    const state = readExplorerLocation(params);
    expect(state).toMatchObject({ view: 'matches', day: '2026-09-16' });
    expect(readExplorerLocation(writeExplorerLocation(params, state))).toEqual(state);
    expect(readExplorerLocation(new URLSearchParams('date=2026-02-30')).day).toBe('');
    for (const view of ['matches', 'values', 'performance', 'users', 'admin'])
      expect(readExplorerLocation(new URLSearchParams({ view })).view).toBe(view);
  });
});
