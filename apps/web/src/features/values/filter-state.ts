export interface Filters {
  league: string;
  team: string;
  market: string;
  minValue: number;
  period: string;
}
export const defaultFilters: Filters = {
  league: 'all',
  team: 'all',
  market: 'all',
  minValue: 0,
  period: 'all',
};
