import { describe, expect, it } from 'vitest';
import { championAsset, championManifestVersion } from './champions';

describe('Manifeste des portraits champions', () => {
  it('résout les noms affichés vers les portraits Data Dragon', () => {
    expect(championAsset("Kai'Sa")).toContain('/champions/Kaisa.png');
    expect(championAsset('Ahri')).toContain('/champions/Ahri.png');
    expect(championManifestVersion).toBe('16.18.1');
  });

  it('privilégie l’asset officiel et garde un repli source pour une identité inconnue', () => {
    expect(championAsset('Ahri', '/custom/ahri.png')).toContain('/champions/Ahri.png');
    expect(championAsset('Champion inconnu', '/custom/unknown.png')).toBe('/custom/unknown.png');
    expect(championAsset('Champion inconnu')).toBe('');
  });
});
