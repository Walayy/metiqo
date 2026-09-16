import { expect, it } from 'vitest';
import { supportUrl } from './links';
it('accepte uniquement une destination HTTPS sans identifiants intégrés', () => {
  expect(supportUrl('https://example.com/support')).toBe('https://example.com/support');
  for (const value of [
    undefined,
    '',
    '/support',
    'javascript:alert(1)',
    'http://example.com',
    'https://user:pass@example.com',
  ])
    expect(supportUrl(value)).toBeNull();
});
