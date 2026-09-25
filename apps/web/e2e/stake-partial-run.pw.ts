import { expect, test } from '@playwright/test';

const requestedAt = '2026-09-25T16:20:03Z';

for (const { width, height, theme } of [
  { width: 390, height: 844, theme: 'light' },
  { width: 390, height: 844, theme: 'dark' },
  { width: 768, height: 1024, theme: 'light' },
  { width: 768, height: 1024, theme: 'dark' },
  { width: 1440, height: 900, theme: 'light' },
  { width: 1440, height: 900, theme: 'dark' },
] as const) {
  test(`partial Stake run remains readable at ${width}px in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((at) => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const path = new URL(input instanceof Request ? input.url : String(input), location.href)
          .pathname;
        if (path === '/api/v1/auth/session') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                user: {
                  id: '11111111-1111-4111-8111-111111111111',
                  email: 'admin@example.test',
                  role: 'admin',
                  createdAt: at,
                },
                expiresAt: '2026-12-01T00:00:00Z',
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        if (path === '/api/v1/admin/scripts') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                worker: { online: true, lastSeenAt: at },
                items: [
                  {
                    id: 'stake-markets',
                    family: 'Stake',
                    name: 'Stake · cotes pré-match et direct',
                    description: 'Historise les marchés et les cotes.',
                    command: 'sync-stake-markets',
                    cron: '*/20 * * * *',
                    timezone: 'Europe/Paris',
                    enabled: true,
                    revision: 1,
                    nextRunAt: '2026-09-25T16:40:00Z',
                    upcoming: [],
                    available: true,
                    activeRun: null,
                    runs: [
                      {
                        id: '22222222-2222-4222-8222-222222222222',
                        scriptId: 'stake-markets',
                        trigger: 'schedule',
                        status: 'succeeded',
                        requestedAt: at,
                        startedAt: at,
                        finishedAt: '2026-09-25T16:28:19Z',
                        error: null,
                        complete: false,
                        summary: {
                          eventsCollected: 18,
                          markets: 415,
                          quotes: 1234,
                          eventsFailed: 1,
                          snapshots: 18,
                        },
                        eventErrors: [
                          {
                            eventId: '845833',
                            reason: 'Ambiguous source market identity',
                          },
                        ],
                        interruption: {
                          stage: 'event_traversal',
                          eventId: '845833',
                          kind: 'RuntimeError',
                          frames: ['stake_browser.py:event:358'],
                        },
                        deferredReason: null,
                      },
                      {
                        id: '33333333-3333-4333-8333-333333333333',
                        scriptId: 'stake-markets',
                        trigger: 'schedule',
                        status: 'succeeded',
                        requestedAt: '2026-09-25T16:00:00Z',
                        startedAt: '2026-09-25T16:00:00Z',
                        finishedAt: '2026-09-25T16:09:00Z',
                        error: null,
                        complete: false,
                        summary: {
                          eventsCollected: 12,
                          quotes: 324,
                          eventsFailed: 2,
                          snapshots: 12,
                        },
                        eventErrors: [],
                        interruption: null,
                        deferredReason: null,
                        statusCorrection: {
                          basis: 'persisted_stake_quotes',
                          previousStatus: 'failed',
                          previousError: 'stake_collection: Error',
                        },
                      },
                    ],
                  },
                ],
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        return originalFetch(input, init);
      };
    }, requestedAt);

    await page.goto('/?view=admin');
    await expect(page.getByRole('heading', { name: 'Scripts' })).toBeVisible();
    await page.locator('.script-entry-trigger').click();
    const historyButton = page.getByRole('button', { name: /Historique de Stake/ });
    await historyButton.click();
    const dialog = page.getByRole('dialog', { name: 'Historique' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('Couverture incomplète').first()).toBeVisible();
    await expect(dialog.getByText('Terminée', { exact: true }).first()).toBeVisible();
    await dialog.locator('.run-trigger').first().click();
    await expect(dialog.getByText('Stake 845833', { exact: true })).toBeVisible();
    await expect(dialog.getByText('Arrêt technique après publication')).toBeVisible();
    await dialog.locator('.run-trigger').nth(1).click();
    await expect(
      dialog.getByText(/Statut historique corrigé grâce aux relevés conservés/),
    ).toBeVisible();
    const bounds = await dialog.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
    await dialog.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(historyButton).toBeFocused();
  });
}
