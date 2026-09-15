export interface Filters {
  league: string;
  market: string;
  minValue: number;
  bookmaker: string;
  period: string;
}
export const defaultFilters: Filters = {
  league: 'all',
  market: 'all',
  minValue: 0,
  bookmaker: 'all',
  period: 'all',
};
