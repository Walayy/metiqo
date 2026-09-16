import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { fetchResponse, readResponse, requestCooldown } from './http';
import { HttpError, retryDeadline, retryRead } from './http-error';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function setup() {
  const values = new Map<string, string>();
  vi.stubGlobal('location', { origin: 'https://metiquo.test' });
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
  return vi.stubGlobal('fetch', vi.fn()).mocked(fetch);
}

describe('échéances du serveur', () => {
  const now = Date.parse('2026-09-16T10:00:00Z');
  it('comprend les secondes et les dates HTTP même avec une horloge locale décalée', () => {
    expect(retryDeadline('60', null, now)).toBe(now + 60_000);
    expect(
      retryDeadline('Wed, 16 Sep 2026 12:01:00 GMT', 'Wed, 16 Sep 2026 12:00:00 GMT', now),
    ).toBe(now + 60_000);
    expect(retryDeadline('Wed, 16 Sep 2026 10:01:00 GMT', null, now)).toBe(now + 60_000);
    expect(retryDeadline('0', null, now)).toBe(now);
  });
  it('n’invente pas de délai pour une valeur absente, passée ou invalide', () => {
    for (const value of [
      null,
      '',
      '-1',
      '1.5',
      'demain',
      '999999999999999999',
      'Wed, 16 Sep 2026 09:00:00 GMT',
    ])
      expect(retryDeadline(value, null, now)).toBe(0);
  });
  it('ne relance automatiquement ni une interdiction, ni une limite, ni une réponse invalide', () => {
    for (const status of [400, 401, 403, 404, 409, 423, 429])
      expect(retryRead(0, new HttpError(status))).toBe(false);
    expect(retryRead(0, new HttpError(503, { retryAt: now + 30_000 }))).toBe(false);
    expect(retryRead(0, new HttpError(0, { kind: 'invalid-response' }))).toBe(false);
    expect(retryRead(0, new HttpError(502))).toBe(true);
    expect(retryRead(1, new HttpError(502))).toBe(false);
  });
});

describe('transport des erreurs', () => {
  it('respecte un 429 même en HTML, conserve son échéance et bloque les requêtes avant celle-ci', async () => {
    const fetcher = setup();
    let now = Date.parse('2026-09-16T12:00:00Z');
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    fetcher.mockResolvedValueOnce(
      new Response('<html>Too many requests</html>', {
        status: 429,
        headers: { 'Retry-After': '15' },
      }),
    );
    const signal = new AbortController().signal;
    await expect(fetchResponse('/limited', signal)).rejects.toMatchObject({
      status: 429,
      retryAt: now + 15_000,
    });
    now += 5000;
    await expect(fetchResponse('/limited?q=another', signal)).rejects.toMatchObject({
      status: 429,
      retryAfter: 10,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(requestCooldown('/limited', 'GET')?.retryAfter).toBe(10);
    now += 10_000;
    fetcher.mockResolvedValueOnce(new Response('{}'));
    await expect(fetchResponse('/limited', signal)).resolves.toBeInstanceOf(Response);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it('garde un 503 sans JSON et ne prend pas une panne réseau pour une déconnexion du compte', async () => {
    const fetcher = setup();
    fetcher.mockResolvedValueOnce(new Response('upstream unavailable', { status: 503 }));
    await expect(
      fetchResponse('/unavailable', new AbortController().signal, {}, true),
    ).rejects.toMatchObject({ status: 503, retryAt: 0 });
    fetcher.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(fetchResponse('/network', new AbortController().signal)).rejects.toMatchObject({
      status: 0,
      kind: 'network',
    });
  });
  it('ne transforme pas une annulation en erreur visible', async () => {
    const fetcher = setup();
    const controller = new AbortController();
    controller.abort();
    await expect(fetchResponse('/cancelled', controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('rejette une page HTML ou des données incomplètes reçues avec un succès HTTP', async () => {
    const schema = z.object({ count: z.number() });
    await expect(
      readResponse(new Response('<html>bad gateway</html>'), schema),
    ).rejects.toMatchObject({ kind: 'invalid-response' });
    await expect(readResponse(new Response('{"count":"unknown"}'), schema)).rejects.toMatchObject({
      kind: 'invalid-response',
    });
    expect(await readResponse(new Response('{"count":3}'), schema)).toEqual({ count: 3 });
  });
});
