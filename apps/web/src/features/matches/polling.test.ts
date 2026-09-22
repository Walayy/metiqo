import { describe, expect, it } from 'vitest';
import { HttpError } from '@/lib/http-error';
import { matchesPollInterval } from './polling';
import { matchesSchema } from '@/domain/matches';
import { liveUpdateFrame } from '@/mocks/live-updates';

describe('actualisation continue des matchs', () => {
  it('reprend après une panne transitoire en respectant Retry-After', () => {
    const now = 100_000;
    expect(matchesPollInterval(true, null)).toBe(15_000);
    expect(matchesPollInterval(false, null)).toBe(30_000);
    expect(matchesPollInterval(true, new HttpError(0, { kind: 'network' }))).toBe(30_000);
    expect(matchesPollInterval(true, new HttpError(503, { retryAt: now + 120_000 }), now)).toBe(
      120_000,
    );
    expect(matchesPollInterval(true, new HttpError(429, { retryAt: now - 1000 }), now)).toBe(
      30_000,
    );
  });
  it('ne répète pas un refus d’accès ni un contrat invalide', () => {
    for (const status of [401, 403, 423, 404])
      expect(matchesPollInterval(true, new HttpError(status))).toBe(false);
    expect(matchesPollInterval(true, new HttpError(0, { kind: 'invalid-response' }))).toBe(false);
  });
  it('le scénario de reprise conserve des contrats valides et les identités de carte', () => {
    const frames = [0, 1, 2, 4, 5].map((frame) => matchesSchema.parse(liveUpdateFrame(frame)));
    const initial = frames[0]!.items.find((match) => match.status === 'live')!;
    const before = initial.maps.find((map) => map.status === 'live')!;
    const after = frames[3]!.items.find((match) => match.id === initial.id)!;
    expect(before.durationSeconds).toBeNull();
    expect(after.maps.find((map) => map.number === before.number)?.status).toBe('finished');
    expect(after.maps.find((map) => map.status === 'live')?.number).toBe(before.number + 1);
  });
});
