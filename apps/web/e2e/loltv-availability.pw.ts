import { expect, test } from '@playwright/test';
import type { EsportMatch } from '../src/domain/matches';
import type { ScriptRun } from '../src/features/admin/contracts';
import { installWorkerLogsFixture } from './fixtures/worker-logs';

// Synthetic responses are confined to these browser regression tests.
for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 768, 1440]) {
    test(`walkovers show Forfait and preserve keyboard access at ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.clock.setFixedTime(new Date('2026-09-25T10:00:00Z'));
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(() => {
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (input, init) => {
          const response = await originalFetch(input, init);
          const url = new URL(input instanceof Request ? input.url : String(input), location.href);
          if (url.pathname !== '/api/v1/matches' || !response.ok) return response;
          const data = (await response.json()) as { items: EsportMatch[] };
          const first = data.items[0]!;
          data.items.push({
            ...first,
            id: 'walkover-fixture',
            status: 'walkover',
            startsAt: '2026-09-25T08:00:00Z',
            format: 'BO3',
            currentScore: { home: 1, away: 0 },
            seriesScore: { home: 1, away: 0 },
            maps: [],
            oddsMarkets: [],
          });
          return new Response(JSON.stringify(data), {
            headers: { 'Content-Type': 'application/json' },
          });
        };
      });
      await page.goto('/');
      await page.getByRole('button', { name: 'Forfaits 1', exact: true }).click();
      const league = page.locator('.league-accordion');
      await league.locator('button.league-trigger').click();
      const fixture = league.locator('.fixture-row');
      await expect(fixture).toHaveAttribute('aria-label', /forfait, 1 : 0/);
      await expect(fixture.locator('.fixture-status')).toHaveText('Forfait');
      await expect(
        page.locator('.match-status-filter').filter({ hasText: 'Forfaits' }),
      ).toHaveAttribute('aria-pressed', 'true');
      await fixture.focus();
      await fixture.press('Enter');
      const dialog = page.locator('.match-dialog');
      await expect(dialog.locator('.series-summary')).toContainText('Forfait');
      await expect(dialog.locator('.match-pending')).toContainText('forfait');
      await expect(dialog.getByRole('tab')).toHaveCount(0);
      await expect(dialog.locator('.live-badge')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
      if (process.env.UI_CAPTURE)
        await page.screenshot({ path: `test-results/walkover-${width}-${theme}.png` });
      await dialog.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(fixture).toBeFocused();
    });

    test(`LoLTV partial history explains incidents at ${width}px ${theme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 900 });
      await installWorkerLogsFixture(page);
      await page.addInitScript(() => {
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (input, init) => {
          const response = await originalFetch(input, init);
          const url = new URL(input instanceof Request ? input.url : String(input), location.href);
          if (url.pathname !== '/api/v1/admin/scripts') return response;
          const data = (await response.json()) as { items: { id: string; runs: ScriptRun[] }[] };
          data.items.find((item) => item.id === 'loltv-matches')!.runs = [
            {
              id: '33333333-3333-4333-8333-333333333333',
              scriptId: 'loltv-matches',
              trigger: 'schedule',
              status: 'succeeded',
              requestedAt: '2026-09-25T22:45:00Z',
              startedAt: '2026-09-25T22:45:00Z',
              finishedAt: '2026-09-25T22:45:30Z',
              error: null,
              complete: false,
              summary: { published: 24 },
              sourceIssues: [
                {
                  code: 'loltv_stale_listing',
                  stage: 'listing',
                  reason: 'Calendrier source en cache depuis plus de 24 heures.',
                  resource: '/matches/results/all/2',
                  cacheAgeSeconds: 3000000,
                },
              ],
            },
          ];
          return new Response(JSON.stringify(data), {
            headers: { 'Content-Type': 'application/json' },
          });
        };
      });
      await page.goto('/?view=admin');
      await page.locator('.script-entry-trigger').filter({ hasText: 'LoLTV' }).click();
      await page.getByRole('button', { name: /Historique de LoLTV/ }).click();
      const history = page.getByRole('dialog', { name: 'Historique' });
      await expect(history.getByText('Couverture incomplète', { exact: true })).toBeVisible();
      await history.locator('.run-trigger').click();
      await expect(history.getByText('Incidents source', { exact: true })).toBeVisible();
      await expect(history.locator('.run-issues li')).toContainText(
        'Calendrier source en cache depuis plus de 24 heures.',
      );
      await expect(history.getByText('24 rencontres observées', { exact: true })).toBeVisible();
      await expect(history.getByText(/aucune nouvelle cote/)).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
      if (process.env.UI_CAPTURE)
        await page.screenshot({ path: `test-results/loltv-history-${width}-${theme}.png` });
      await history.press('Escape');
      await expect(history).toBeHidden();
    });
  }
}
