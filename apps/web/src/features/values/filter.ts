import type { Catalog, Opportunity } from '@/domain/schemas';
import { normalize } from '@/lib/format';
import { valueOf } from '@/domain/value';
import type { Filters } from './filter-state';
export function filterValues(
  items: Opportunity[],
  catalog: Catalog,
  filters: Filters,
  search: string,
  favorites: string[],
  savedOnly: boolean,
  sort: string,
  referenceDate: string,
) {
  const term = normalize(search.trim());
  return items
    .filter((item) => {
      if (savedOnly && !favorites.includes(item.id)) return false;
      if (filters.league !== 'all' && item.leagueId !== filters.league) return false;
      if (filters.team !== 'all' && ![item.homeId, item.awayId].includes(filters.team))
        return false;
      if (filters.market !== 'all' && item.market !== filters.market) return false;
      if (valueOf(item) + Number.EPSILON < filters.minValue) return false;
      if (filters.period === 'today' && item.startsAt.slice(0, 10) !== referenceDate.slice(0, 10))
        return false;
      const home = catalog.teams.find((t) => t.id === item.homeId);
      const away = catalog.teams.find((t) => t.id === item.awayId);
      const league = catalog.leagues.find((l) => l.id === item.leagueId);
      return normalize(
        `${home?.name} ${home?.code} ${away?.name} ${away?.code} ${league?.name}`,
      ).includes(term);
    })
    .sort((a, b) =>
      sort === 'time'
        ? Date.parse(a.startsAt) - Date.parse(b.startsAt)
        : sort === 'probability'
          ? b.probability - a.probability
          : valueOf(b) - valueOf(a),
    );
}
