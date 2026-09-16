import { queryOptions } from '@tanstack/react-query';
import type { z } from 'zod';
import { challengeSchema, sessionSchema } from './contracts';
import { authMessages } from './messages';

export class AuthError extends Error {
  constructor(
    message: string,
    readonly retryAfter = 0,
  ) {
    super(message);
    this.name = 'AuthError';
  }
}

async function request(path: string, signal: AbortSignal, body?: object) {
  let response: Response;
  try {
    // Auth is always real and same-origin, independently of esport fixtures and API URLs.
    response = await fetch(`/api/v1/auth${path}`, {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
      headers: body ? { 'Content-Type': 'application/json', 'X-Metiquo-Auth': '1' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new AuthError(authMessages.offline);
  }
  if (!response.ok) {
    const retryAfter = Number(response.headers.get('Retry-After')) || 0;
    const messages: Record<number, string> = {
      400: authMessages.codeInvalid,
      403: authMessages.refused,
      422: authMessages.invalidRequest,
      429: authMessages.rateLimited,
      503: authMessages.unavailable,
    };
    throw new AuthError(messages[response.status] ?? authMessages.failed, retryAfter);
  }
  return response;
}

async function read<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new AuthError(authMessages.invalidResponse);
  return parsed.data;
}
export const sessionQuery = queryOptions({
  queryKey: ['auth', 'session'],
  queryFn: async ({ signal }) => read(await request('/session', signal), sessionSchema),
  staleTime: 30_000,
  refetchOnWindowFocus: true,
  refetchInterval: 60_000,
  retry: false,
});
export const requestCode = async (email: string, signal: AbortSignal) =>
  read(await request('/request-code', signal, { email }), challengeSchema);
export const verifyCode = async (challengeId: string, code: string, signal: AbortSignal) =>
  read(await request('/verify-code', signal, { challengeId, code }), sessionSchema);
export const logout = async (signal: AbortSignal) => {
  await request('/logout', signal, {});
};
