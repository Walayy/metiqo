import { describe, expect, it } from 'vitest';
import { challengeSchema, codeSchema, sessionSchema } from './contracts';

describe('contrats de connexion', () => {
  it('préserve les zéros initiaux et exige six chiffres ASCII', () => {
    expect(codeSchema.parse('000042')).toBe('000042');
    for (const input of ['12345', '1234567', '１２３４５６', 123456]) {
      expect(codeSchema.safeParse(input).success).toBe(false);
    }
  });
  it('accepte une session anonyme et rejette un rôle inconnu ou une expiration invalide', () => {
    expect(sessionSchema.parse({ user: null, expiresAt: null }).user).toBeNull();
    const user = {
      id: '4e3b4d5c-7030-4617-90ce-b24c2726437f',
      email: 'admin@metiquo.fr',
      createdAt: '2026-09-15T12:00:00Z',
      role: 'admin',
    };
    expect(sessionSchema.safeParse({ user, expiresAt: '2026-10-15T12:00:00Z' }).success).toBe(true);
    expect(
      sessionSchema.safeParse({ user: { ...user, role: 'owner' }, expiresAt: null }).success,
    ).toBe(false);
    expect(
      challengeSchema.safeParse({
        challengeId: user.id,
        expiresAt: 'demain',
        resendAt: 'maintenant',
      }).success,
    ).toBe(false);
  });
});
