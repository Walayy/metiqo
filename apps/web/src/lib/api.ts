import { queryOptions } from '@tanstack/react-query';
import type { z } from 'zod';
import { catalogSchema, opportunitiesSchema } from '@/domain/schemas';
import { config } from './config';
import { transportReady } from './transport';

async function get<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal): Promise<T> {
  await transportReady;
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
  });
  if (!response.ok) throw new Error(`Le chargement a échoué (${response.status}).`);
  return schema.parse(await response.json());
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
