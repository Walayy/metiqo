import { expect, test } from '@playwright/test';

import { installWorkerLogsFixture } from './fixtures/worker-logs';

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
    await installWorkerLogsFixture(page);

    await page.goto('/?view=admin');
    await page.getByRole('button', { name: /Services .*disponibles/ }).click();
    await expect(page.locator('.worker-service')).toHaveCount(3);
    const serviceButton = page.getByRole('button', { name: 'Journaux de Cotes Stake' });
    await serviceButton.click();
    const reader = page.getByRole('dialog', { name: 'Cotes Stake' });
    await expect(reader).toBeVisible();
    await expect(
      reader.getByText('Rencontre non publiée : identité de marché ambiguë.').first(),
    ).toBeVisible();
    await reader.getByRole('button', { name: 'Filtres', exact: true }).click();
    await reader.getByRole('button', { name: 'Erreurs', exact: true }).click();
    await expect(reader.locator('.log-line')).toHaveCount(1);
    await reader.getByRole('button', { name: /2 incidents récents/ }).click();
    await expect(reader.getByText('À examiner')).toBeVisible();
    await expect(reader.getByText(/identité de marché ambiguë/).first()).toBeVisible();
    await expect(reader.locator('.log-line')).toHaveCount(1);
    if (process.env.UI_CAPTURE)
      await page.screenshot({ path: `test-results/logs-${width}-${theme}.png` });
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

    await page
      .locator('.script-entry-trigger')
      .filter({ hasText: 'Cotes pré-match et direct' })
      .click();
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
      await reader.getByRole('combobox', { name: 'Exécution' }).click();
      await page.getByRole('option', { name: /Stake · cotes/ }).click();
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
