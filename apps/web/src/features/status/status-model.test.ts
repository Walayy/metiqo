import { describe, expect, it } from 'vitest';
import { HttpError } from '@/lib/http-error';
import { isKnownLocation, statusContent, waitLabel } from './status-model';

describe('navigation et reprise après une erreur', () => {
  it('distingue un lien inconnu des filtres et vues réellement disponibles', () => {
    for (const query of ['', '?view=admin', '?league=unknown&q=abc&page=3'])
      expect(isKnownLocation('/', query)).toBe(true);
    for (const path of ['/unknown', '/admin', '/404', '/423'])
      expect(isKnownLocation(path, '')).toBe(false);
    expect(isKnownLocation('/', '?view=unknown')).toBe(false);
    expect(isKnownLocation('/', '?view=favorites')).toBe(false);
  });
  it('propose de se connecter pour une session absente, mais pas pour un accès interdit ou suspendu', () => {
    expect(statusContent(new HttpError(401)).action).toBe('login');
    expect(statusContent(new HttpError(403)).action).toBe('home');
    expect(statusContent(new HttpError(423)).action).toBe('home');
    expect(statusContent(new HttpError(404)).action).toBe('home');
    expect(statusContent(new HttpError(429)).action).toBe('retry');
    expect(statusContent(new HttpError(503)).action).toBe('retry');
  });
  it('exprime une longue attente sans afficher des milliers de secondes', () => {
    expect(waitLabel(5)).toBe('5 s');
    expect(waitLabel(65)).toBe('1 min 05 s');
    expect(waitLabel(3610)).toBe('1 h 00 min');
  });
});
