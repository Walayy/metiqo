import { defaultFilters } from './filter-state';
import type { Filters } from './filter-state';

export interface ExplorerLocation {
  savedOnly: boolean;
  filters: Filters;
  search: string;
  sort: string;
  page: number;
  selectedId: string | null;
  detailOpen: boolean;
}
const keys = ['view', 'league', 'team', 'market', 'min', 'period', 'q', 'sort', 'page', 'detail'];
export function readExplorerLocation(params: URLSearchParams): ExplorerLocation {
  const page = Number(params.get('page'));
  const minimum = Number(params.get('min'));
  const detail = params.get('detail') || null;
  return {
    savedOnly: params.get('view') === 'favorites',
    filters: {
      ...defaultFilters,
      league: params.get('league') || 'all',
      team: params.get('team') || 'all',
      market: ['winner', 'map1'].includes(params.get('market') ?? '')
        ? params.get('market')!
        : 'all',
      minValue: Number.isInteger(minimum) && minimum >= 0 && minimum <= 15 ? minimum : 0,
      period: params.get('period') === 'today' ? 'today' : 'all',
    },
    search: params.get('q') ?? '',
    sort: ['time', 'probability'].includes(params.get('sort') ?? '')
      ? params.get('sort')!
      : 'value',
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    selectedId: detail,
    detailOpen: !!detail,
  };
}
export function writeExplorerLocation(base: URLSearchParams, state: ExplorerLocation) {
  const params = new URLSearchParams(base);
  for (const key of keys) params.delete(key);
  if (state.savedOnly) params.set('view', 'favorites');
  if (state.filters.league !== 'all') params.set('league', state.filters.league);
  if (state.filters.team !== 'all') params.set('team', state.filters.team);
  if (state.filters.market !== 'all') params.set('market', state.filters.market);
  if (state.filters.minValue) params.set('min', String(state.filters.minValue));
  if (state.filters.period !== 'all') params.set('period', state.filters.period);
  if (state.search) params.set('q', state.search);
  if (state.sort !== 'value') params.set('sort', state.sort);
  if (state.page > 1) params.set('page', String(state.page));
  if (state.detailOpen && state.selectedId) params.set('detail', state.selectedId);
  return params;
}
