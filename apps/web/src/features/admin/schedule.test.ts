import { describe, expect, it } from 'vitest';
import { fromCron, toCron } from './schedule';
import { scriptsSchema } from './contracts';
import { readExplorerLocation, writeExplorerLocation } from '@/features/values/explorer-location';

describe('Planification administrateur', () => {
  it('conserve les crons existants même si le formulaire simplifié ne les décrit pas', () => {
    for (const cron of [
      '0 4 * * *',
      '0 */6 * * *',
      '30 18 * * 1',
      '0 4 1,15 * *',
      '*/15 9-18 * * 1-5',
    ]) {
      expect(toCron(fromCron(cron))).toBe(cron);
    }
  });
  it('refuse un horaire quotidien vide au lieu de planifier minuit', () => {
    expect(toCron({ ...fromCron('0 4 * * *'), at: '' })).toBe('');
  });
  it('préserve la section admin dans les liens et le retour arrière', () => {
    const params = new URLSearchParams('view=admin&league=another-league');
    expect(
      readExplorerLocation(writeExplorerLocation(params, readExplorerLocation(params))),
    ).toMatchObject({ view: 'admin' });
  });
  it('refuse un contrat incomplet ou un faux état de worker', () => {
    expect(scriptsSchema.safeParse({ items: [], worker: { online: 'yes' } }).success).toBe(false);
    expect(
      scriptsSchema.safeParse({
        items: [],
        worker: { online: false, lastSeenAt: null },
        workers: [],
      }).success,
    ).toBe(true);
  });
});
