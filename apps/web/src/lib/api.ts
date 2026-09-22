import { queryOptions } from '@tanstack/react-query';
import type { z } from 'zod';
import { catalogSchema, opportunitiesSchema } from '@/domain/schemas';
import { config } from './config';
import { transportReady } from './transport';
import { fetchResponse, readResponse } from './http';
import { matchesSchema } from '@/domain/matches';
import { performanceSchema } from '@/features/performance/simulation';
import { matchesPollInterval } from '@/features/matches/polling';

async function get<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal): Promise<T> {
  await transportReady;
  return readResponse(await fetchResponse(`${config.apiBaseUrl}${path}`, signal), schema);
}
export const catalogQuery = queryOptions({
  queryKey: ['catalog'],
  queryFn: ({ signal }) => get('/catalog', catalogSchema, signal),
  staleTime: Infinity,
});
export const opportunitiesQuery = queryOptions({
  queryKey: ['opportunities'],
  queryFn: ({ signal }) => get('/opportunities', opportunitiesSchema, signal),
  staleTime: 60_000,
});
export const matchesQuery = queryOptions({
  queryKey: ['matches'],
  queryFn: ({ signal }) => get('/matches', matchesSchema, signal),
  staleTime: 15_000,
  refetchOnWindowFocus: true,
  refetchOnReconnect: true,
  refetchInterval: (query) =>
    matchesPollInterval(
      Boolean(query.state.data?.items.some((match) => match.status === 'live')),
      query.state.error,
    ),
});
export const performanceQuery = queryOptions({
  queryKey: ['performance'],
  queryFn: ({ signal }) => get('/performance', performanceSchema, signal),
  staleTime: 60_000,
});
