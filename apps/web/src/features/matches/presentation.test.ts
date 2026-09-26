import { describe, expect, it } from 'vitest';
import { matches } from '@/mocks/esport';
import type { EsportMatch } from '@/domain/matches';
import {
  compareMatches,
  formatDuration,
  goldDifference,
  matchesStatus,
  observationAge,
  statusCounts,
} from './presentation';

describe('Lecture des rencontres', () => {
  const fixture = matches.items[0]!;
  it('rend les directs prioritaires sans masquer les rencontres reportées ou annulées', () => {
    const rows: EsportMatch[] = ['finished', 'cancelled', 'scheduled', 'live', 'postponed'].map(
      (status, i) => ({ ...fixture, id: String(i), status: status as EsportMatch['status'] }),
    );
    expect(rows.toSorted(compareMatches).map((row) => row.status)).toEqual([
      'live',
      'scheduled',
      'cancelled',
      'postponed',
      'finished',
    ]);
    expect(statusCounts(rows)).toEqual({
      all: 5,
      live: 1,
      scheduled: 1,
      finished: 1,
      walkover: 0,
      changed: 2,
    });
    expect(rows.filter((row) => matchesStatus(row, 'changed')).map((row) => row.status)).toEqual([
      'cancelled',
      'postponed',
    ]);
  });
  it('distingue les forfaits des matchs terminés et des rencontres à venir', () => {
    const walkover = { ...fixture, status: 'walkover' as const, maps: [] };
    expect(matchesStatus(walkover, 'walkover')).toBe(true);
    expect(matchesStatus(walkover, 'finished')).toBe(false);
    expect(matchesStatus(walkover, 'scheduled')).toBe(false);
    expect(statusCounts([walkover])).toMatchObject({ all: 1, walkover: 1, finished: 0 });
  });
  it('départage un même statut par horaire puis identifiant stable', () => {
    const rows = [
      { ...fixture, id: 'b', startsAt: '2026-09-21T15:00:00Z' },
      { ...fixture, id: 'z', startsAt: '2026-09-21T14:00:00Z' },
      { ...fixture, id: 'a', startsAt: '2026-09-21T15:00:00Z' },
    ];
    expect(rows.toSorted(compareMatches).map((row) => row.id)).toEqual(['z', 'a', 'b']);
  });
  it('ne calcule aucun avantage en or à partir d’une composition incomplète', () => {
    const side = matches.items
      .flatMap((m) => m.maps)
      .flatMap((m) => m.sides)
      .find((s) => s.players.length === 5)!;
    const home = { ...side, players: side.players.map((p) => ({ ...p, gold: 2000 })) };
    const away = { ...side, players: side.players.map((p) => ({ ...p, gold: 1800 })) };
    expect(goldDifference(home, away)).toBe(1000);
    expect(goldDifference(away, home)).toBe(-1000);
    expect(goldDifference(home, home)).toBe(0);
    expect(goldDifference(home, { ...away, players: away.players.slice(1) })).toBeNull();
    expect(
      goldDifference(home, { ...away, players: away.players.map((p) => ({ ...p, gold: null })) }),
    ).toBeNull();
  });
  it('distingue une durée nulle d’une durée inconnue et conserve l’âge réel du relevé', () => {
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(1678)).toBe('27:58');
    const timestamp = '2026-09-21T19:00:00Z';
    expect(observationAge(timestamp, Date.parse(timestamp) + 120000)).toBe('il y a 2 min');
    expect(observationAge(timestamp, Date.parse(timestamp) + 86400000)).toBe('il y a 1 j');
    expect(observationAge(timestamp, Date.parse(timestamp) - 1000)).toBe(
      'il y a moins d’une minute',
    );
  });
});
