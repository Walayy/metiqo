import type { z } from 'zod';
import { HttpError, retryDeadline } from './http-error';

interface Cooldown {
  status: number;
  retryAt: number;
}
const memory = new Map<string, Cooldown>();
function cooldownKey(url: string, method: string) {
  const parsed = new URL(url, location.origin);
  return `metiquo:retry:${method}:${parsed.origin}${parsed.pathname}`;
}
function readCooldown(key: string): Cooldown | undefined {
  let value = memory.get(key);
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null');
    if (
      stored &&
      typeof stored === 'object' &&
      'status' in stored &&
      'retryAt' in stored &&
      typeof stored.status === 'number' &&
      typeof stored.retryAt === 'number' &&
      [429, 503].includes(stored.status) &&
      Number.isSafeInteger(stored.retryAt)
    ) {
      value = stored as Cooldown;
    }
  } catch {
    /* The server still enforces its limit when storage is unavailable. */
  }
  if (value && value.retryAt > Date.now()) return value;
  memory.delete(key);
  return undefined;
}
export function requestCooldown(url: string, method = 'POST') {
  const value = readCooldown(cooldownKey(url, method));
  return value ? new HttpError(value.status, { retryAt: value.retryAt }) : null;
}

export async function fetchResponse(
  url: string,
  signal: AbortSignal,
  options: RequestInit = {},
  useDetail = false,
): Promise<Response> {
  signal.throwIfAborted();
  const key = cooldownKey(url, options.method ?? 'GET');
  const cooldown = readCooldown(key);
  if (cooldown) throw new HttpError(cooldown.status, { retryAt: cooldown.retryAt });
  const timeout = AbortSignal.timeout(20_000);
  let response: Response;
  try {
    response = await fetch(url, { ...options, signal: AbortSignal.any([signal, timeout]) });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new HttpError(0, { kind: timeout.aborted ? 'timeout' : 'network' });
  }
  if (!response.ok) {
    const retryAt = [429, 503].includes(response.status)
      ? retryDeadline(response.headers.get('Retry-After'), response.headers.get('Date'))
      : 0;
    if (retryAt > Date.now()) {
      const value = { status: response.status, retryAt };
      memory.set(key, value);
      try {
        sessionStorage.setItem(key, JSON.stringify(value));
      } catch {
        /* In-memory fallback. */
      }
    }
    let message: string | undefined;
    if (useDetail && response.headers.get('Content-Type')?.includes('application/json')) {
      try {
        const data: unknown = await response.json();
        if (
          data &&
          typeof data === 'object' &&
          'detail' in data &&
          typeof data.detail === 'string' &&
          data.detail.length <= 240
        )
          message = data.detail;
      } catch (error) {
        if (signal.aborted) throw error;
      }
    }
    throw new HttpError(response.status, { retryAt, message });
  }
  return response;
}

export async function readResponse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  let data: unknown;
  try {
    data = await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new HttpError(0, { kind: 'invalid-response' });
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) throw new HttpError(0, { kind: 'invalid-response' });
  return parsed.data;
}
