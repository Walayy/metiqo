import { expect, test } from '@playwright/test';

const at = '2026-09-25T16:20:00Z';
const runId = '22222222-2222-4222-8222-222222222222';

for (const { width, height, theme } of [
  { width: 390, height: 844, theme: 'light' },
  { width: 390, height: 844, theme: 'dark' },
  { width: 768, height: 1024, theme: 'light' },
  { width: 768, height: 1024, theme: 'dark' },
  { width: 1440, height: 900, theme: 'light' },
  { width: 1440, height: 900, theme: 'dark' },
] as const) {
  test(`worker journal ${width}px ${theme} keeps incidents and focus`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript(
      ({ requestedAt, selectedRun }) => {
        const run = {
          id: selectedRun,
          scriptId: 'stake-markets',
          trigger: 'schedule',
          status: 'succeeded',
          requestedAt,
          startedAt: requestedAt,
          finishedAt: '2026-09-25T16:28:00Z',
          error: null,
          complete: false,
          summary: { eventsCollected: 18, quotes: 1234, eventsFailed: 1, snapshots: 18 },
          eventErrors: [{ eventId: '845833', reason: 'Ambiguous source market identity' }],
          interruption: null,
          deferredReason: null,
          statusCorrection: null,
        };
        const recent = {
          id: selectedRun,
          scriptId: 'stake-markets',
          name: 'Stake · cotes pré-match et direct',
          status: 'succeeded',
          requestedAt,
        };
        const lines = [
          {
            id: 101,
            workerId: 2,
            scriptId: 'stake-markets',
            runId: selectedRun,
            recordedAt: requestedAt,
            level: 'info',
            stage: 'exécution',
            message: 'Exécution démarrée.',
            eventId: null,
            context: {},
          },
          {
            id: 102,
            workerId: 2,
            scriptId: 'stake-markets',
            runId: selectedRun,
            recordedAt: '2026-09-25T16:22:00Z',
            level: 'warning',
            stage: 'publication',
            message: 'Rencontre non publiée : identité de marché ambiguë.',
            eventId: '845833',
            context: { kind: 'ValueError' },
          },
          {
            id: 103,
            workerId: 2,
            scriptId: 'stake-markets',
            runId: selectedRun,
            recordedAt: '2026-09-25T16:28:00Z',
            level: 'error',
            stage: 'collecte',
            message: 'Passage Stake interrompu après erreur.',
            eventId: null,
            context: { kind: 'RuntimeError', frames: ['stake_browser.py:event:358'] },
          },
        ];
        Object.assign(window, { __workerLogsFixture: { run, lines } });
        const originalFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {
          const url = new URL(input instanceof Request ? input.url : String(input), location.href);
          const json = (body: object) =>
            Promise.resolve(
              new Response(JSON.stringify(body), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              }),
            );
          if (url.pathname === '/api/v1/auth/session') {
            return json({
              user: {
                id: '11111111-1111-4111-8111-111111111111',
                email: 'admin@example.test',
                role: 'admin',
                createdAt: requestedAt,
              },
              expiresAt: '2026-12-01T00:00:00Z',
            });
          }
          if (url.pathname === '/api/v1/admin/scripts') {
            return json({
              worker: { online: true, lastSeenAt: requestedAt },
              workers: [
                {
                  id: 1,
                  name: 'Collectes sportives',
                  online: false,
                  lastSeenAt: requestedAt,
                  activeRuns: [],
                },
                {
                  id: 2,
                  name: 'Cotes Stake',
                  online: true,
                  lastSeenAt: requestedAt,
                  activeRuns: [],
                },
                {
                  id: 3,
                  name: 'Résultats des sélections',
                  online: false,
                  lastSeenAt: null,
                  activeRuns: [],
                },
              ],
              items: [
                {
                  id: 'stake-markets',
                  workerId: 2,
                  family: 'Stake',
                  name: 'Stake · cotes pré-match et direct',
                  description: 'Historise les cotes.',
                  command: 'sync-stake-markets',
                  cron: '*/20 * * * *',
                  timezone: 'Europe/Paris',
                  enabled: true,
                  revision: 1,
                  nextRunAt: '2026-09-25T16:40:00Z',
                  upcoming: [],
                  available: true,
                  activeRun: null,
                  runs: [run],
                },
              ],
            });
          }
          if (url.pathname === '/api/v1/admin/worker-logs') {
            const workerId = Number(url.searchParams.get('workerId'));
            const selected = url.searchParams.get('runId');
            const level = url.searchParams.get('level');
            const q = url.searchParams.get('q')?.toLowerCase();
            const after = Number(url.searchParams.get('after') || 0);
            const before = Number(url.searchParams.get('before') || 0);
            const entries = lines.filter(
              (line) =>
                line.workerId === workerId &&
                (!selected || line.runId === selected) &&
                (!level || line.level === level) &&
                (!q ||
                  `${line.message} ${line.stage} ${line.eventId ?? ''}`
                    .toLowerCase()
                    .includes(q)) &&
                (!after || line.id > after) &&
                (!before || line.id < before),
            );
            return json({
              items: entries,
              incidents: lines
                .filter((line) => line.workerId === workerId && line.level !== 'info')
                .reverse(),
              hasMore: false,
              recentRuns: workerId === 2 ? [recent] : [],
              run: selected ? run : null,
            });
          }
          return originalFetch(input, init);
        };
      },
      { requestedAt: at, selectedRun: runId },
    );

    await page.goto('/?view=admin');
    await expect(page.locator('.worker-service')).toHaveCount(3);
    const serviceButton = page.getByRole('button', { name: 'Journaux de Cotes Stake' });
    await serviceButton.click();
    const reader = page.getByRole('dialog', { name: 'Cotes Stake' });
    await expect(reader).toBeVisible();
    await expect(
      reader.getByText('Rencontre non publiée : identité de marché ambiguë.').first(),
    ).toBeVisible();
    if (width <= 640) {
      await reader.getByRole('button', { name: 'Filtres' }).click();
      const sheet = page.getByRole('dialog', { name: 'Filtrer les journaux' });
      await sheet.getByRole('button', { name: 'Erreurs' }).click();
      await sheet.getByRole('button', { name: 'Afficher les résultats' }).click();
    } else {
      await reader.getByRole('button', { name: 'Erreurs' }).click();
    }
    await expect(reader.getByText('À examiner')).toBeVisible();
    await expect(reader.getByText(/identité de marché ambiguë/).first()).toBeVisible();
    await expect(reader.locator('.log-line')).toHaveCount(1);
    const bounds = await reader.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
    await reader.press('Escape');
    await expect(reader).toBeHidden();
    await expect(serviceButton).toBeFocused();

    await page.locator('.script-entry-trigger').click();
    await page.getByRole('button', { name: /Historique de Stake/ }).click();
    const history = page.getByRole('dialog', { name: 'Historique' });
    await history.locator('.run-trigger').click();
    const runButton = history.getByRole('button', { name: 'Voir le journal' });
    await runButton.click();
    await expect(page.getByRole('dialog')).toHaveCount(1);
    await expect(reader).toBeVisible();
    await expect(reader.getByText('18 rencontres publiées')).toBeVisible();
    await reader.press('Escape');
    await expect(history).toBeVisible();
    await expect(history.locator('.run-detail')).toBeVisible();
    await expect(history.getByRole('button', { name: 'Voir le journal' })).toBeFocused();

    if (width === 390 && theme === 'light') {
      await history.press('Escape');
      await page.evaluate(() => {
        const fixture = (
          window as unknown as { __workerLogsFixture: { run: { status: string }; lines: object[] } }
        ).__workerLogsFixture;
        fixture.run.status = 'running';
        for (let id = 104; id <= 165; id += 1) {
          fixture.lines.push({
            id,
            workerId: 2,
            scriptId: 'stake-markets',
            runId: '22222222-2222-4222-8222-222222222222',
            recordedAt: '2026-09-25T16:29:00Z',
            level: 'info',
            stage: 'publication',
            message: `Rencontre ${id} publiée.`,
            eventId: String(id),
            context: {},
          });
        }
      });
      await serviceButton.click();
      await reader.locator('.log-run-picker select').selectOption(runId);
      await expect(reader.getByLabel('Suivre en direct')).toBeChecked();
      await expect
        .poll(() => reader.locator('.log-lines-scroll').evaluate((element) => element.scrollTop))
        .toBeGreaterThan(0);
      await reader.locator('.log-lines-scroll').evaluate((element) => {
        element.scrollTop = 0;
      });
      await expect(reader.getByLabel('Suivre en direct')).not.toBeChecked();
      await page.evaluate(() => {
        const fixture = (window as unknown as { __workerLogsFixture: { lines: object[] } })
          .__workerLogsFixture;
        fixture.lines.push({
          id: 166,
          workerId: 2,
          scriptId: 'stake-markets',
          runId: '22222222-2222-4222-8222-222222222222',
          recordedAt: '2026-09-25T16:30:00Z',
          level: 'info',
          stage: 'publication',
          message: 'Nouvelle rencontre publiée.',
          eventId: '166',
          context: {},
        });
      });
      const resume = reader.getByRole('button', { name: /Revenir au direct/ });
      await expect(resume).toBeVisible({ timeout: 10_000 });
      await expect(reader.getByText('Nouvelle rencontre publiée.')).toHaveCount(1);
      await resume.click();
      await expect(reader.getByLabel('Suivre en direct')).toBeChecked();
    }
  });
}
