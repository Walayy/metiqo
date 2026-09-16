import { useEffect, useRef } from 'react';
import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import type { z } from 'zod';
import { sessionQuery } from '@/features/auth/api';
import { scriptsSchema, usersSchema } from './contracts';
import { fetchResponse, readResponse } from '@/lib/http';
import { HttpError } from '@/lib/http-error';

export { HttpError as AdminError } from '@/lib/http-error';

export async function adminRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  method = 'GET',
  body?: object,
): Promise<T> {
  const response = await fetchResponse(
    `/api/v1/admin${path}`,
    signal,
    {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      headers:
        method === 'GET'
          ? undefined
          : { 'Content-Type': 'application/json', 'X-Metiquo-Auth': '1' },
      body: body ? JSON.stringify(body) : undefined,
    },
    true,
  );
  return readResponse(response, schema);
}
export const scriptsQuery = queryOptions({
  queryKey: ['admin', 'scripts'],
  queryFn: ({ signal }) => adminRequest('/scripts', scriptsSchema, signal),
  refetchInterval: (query) => (query.state.error ? false : 5_000),
  retry: false,
});
export const usersQuery = (search: string, page: number) =>
  queryOptions({
    queryKey: ['admin', 'users', search, page],
    queryFn: ({ signal }) =>
      adminRequest(`/users?q=${encodeURIComponent(search)}&page=${page}`, usersSchema, signal),
    retry: false,
  });

export function useAdminAction<T>(schema: z.ZodType<T>, onSuccess?: () => void) {
  const client = useQueryClient();
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  return useMutation({
    mutationFn: ({
      path,
      method = 'POST',
      body,
    }: {
      path: string;
      method?: string;
      body?: object;
    }) => {
      controller.current?.abort();
      controller.current = new AbortController();
      return adminRequest(path, schema, controller.current.signal, method, body);
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['admin'] }),
        client.invalidateQueries({ queryKey: sessionQuery.queryKey }),
      ]);
      onSuccess?.();
    },
    onError: (error) => {
      if (error instanceof HttpError && [401, 403, 423].includes(error.status)) {
        void client.invalidateQueries({ queryKey: sessionQuery.queryKey });
      }
    },
  });
}
