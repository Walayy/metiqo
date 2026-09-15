const mode = import.meta.env.VITE_DATA_MODE ?? 'mock';
if (mode !== 'mock' && mode !== 'api') throw new Error('VITE_DATA_MODE doit être mock ou api.');
export const config = {
  dataMode: mode,
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, ''),
} as const;
