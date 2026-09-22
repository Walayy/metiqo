import { HttpError } from '@/lib/http-error';

export function matchesPollInterval(live: boolean, error: Error | null, now = Date.now()) {
  if (!error) return live ? 15_000 : 30_000;
  if (!(error instanceof HttpError)) return false;
  if (error.kind === 'invalid-response' || [401, 403, 404, 410, 423].includes(error.status))
    return false;
  if (
    error.kind === 'network' ||
    error.kind === 'timeout' ||
    error.status >= 500 ||
    error.status === 429
  )
    return Math.max(30_000, error.retryAt - now);
  return false;
}
