import { queryOptions } from '@tanstack/react-query';
import type { z } from 'zod';
import { challengeSchema, sessionSchema } from './contracts';
import { authMessages } from './messages';
import { fetchResponse, readResponse } from '@/lib/http';
import { HttpError } from '@/lib/http-error';

export class AuthError extends HttpError {
  constructor(
    message: string,
    retryAfter = 0,
    status = 0,
    retryAt = retryAfter ? Date.now() + retryAfter * 1000 : 0,
  ) {
    super(status, { message, retryAt });
    this.name = 'AuthError';
  }
}

async function request(path: string, signal: AbortSignal, body?: object) {
  let response: Response;
  try {
    // Auth is always real and same-origin, independently of esport fixtures and API URLs.
    response = await fetchResponse(`/api/v1/auth${path}`, signal, {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', 'X-Metiquo-Auth': '1' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    if (error instanceof HttpError) {
      const messages: Record<number, string> = {
        400: authMessages.codeInvalid,
        403: authMessages.refused,
        422: authMessages.invalidRequest,
      };
      const message = messages[error.status];
      if (message) throw new AuthError(message, 0, error.status, error.retryAt);
    }
    throw error;
  }
  return response;
}

async function read<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  return readResponse(response, schema);
}
export const sessionQuery = queryOptions({
  queryKey: ['auth', 'session'],
  queryFn: async ({ signal }) => read(await request('/session', signal), sessionSchema),
  staleTime: 30_000,
  refetchOnWindowFocus: true,
  refetchInterval: (query) => (query.state.error ? false : 60_000),
  retry: false,
});
export const requestCode = async (email: string, signal: AbortSignal) =>
  read(await request('/request-code', signal, { email }), challengeSchema);
export const verifyCode = async (challengeId: string, code: string, signal: AbortSignal) =>
  read(await request('/verify-code', signal, { challengeId, code }), sessionSchema);
export const logout = async (signal: AbortSignal) => {
  await request('/logout', signal, {});
};
