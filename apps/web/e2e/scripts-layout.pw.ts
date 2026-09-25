import { expect, test } from '@playwright/test';
import { installWorkerLogsFixture } from './fixtures/worker-logs';

for (const width of [320, 390, 680, 768, 1024, 1920]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`scripts stay compact and usable at ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme });
      await installWorkerLogsFixture(page);
      await page.goto('/?view=admin');
      const rows = page.locator('.script-entry-trigger');
      await expect(rows).toHaveCount(6);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Scripts6');
      await expect(page.locator('.worker-service')).toHaveCount(0);
      expect((await rows.first().boundingBox())!.y).toBeLessThan(330);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
      for (const row of await rows.all()) {
        const box = (await row.boundingBox())!;
        expect(box.width).toBeGreaterThan(200);
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
      }
      if (process.env.UI_CAPTURE)
        await page.screenshot({
          path: `test-results/scripts-${width}-${theme}.png`,
          fullPage: true,
        });
      await rows.first().focus();
      await rows.first().press('Enter');
      await expect(
        page.getByRole('button', { name: 'Planifier Catalogue League of Legends' }),
      ).toBeVisible();
      await rows.nth(1).click();
      await expect(rows.first()).toHaveAttribute('aria-expanded', 'false');
      await expect(rows.nth(1)).toHaveAttribute('aria-expanded', 'true');
      await page.getByRole('button', { name: 'Autres actions pour LoLTV · matchs LoL' }).click();
      await expect(page.getByRole('menuitem', { name: 'Lancer maintenant' })).toBeVisible();
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: /Services .*disponibles/ }).click();
      await page.getByRole('button', { name: 'Journaux de Cotes Stake' }).click();
      const reader = page.getByRole('dialog', { name: 'Cotes Stake' });
      await expect(reader.locator('.log-line')).toHaveCount(3);
      await expect(reader.locator('.log-line-detail')).toHaveCount(0);
      await reader.getByRole('button', { name: /18:28:00 Erreur/ }).click();
      await expect(reader.getByText('stake_browser.py:event:358')).toBeVisible();
      // A change of breakpoint must preserve the open detail, without clipping it.
      await page.setViewportSize({ width: width <= 680 ? 1024 : 390, height: 844 });
      await expect(reader.getByText('stake_browser.py:event:358')).toBeVisible();
      const detailFits = await reader.locator('.log-line-detail').evaluate((element) => {
        const box = element.getBoundingClientRect();
        return (
          box.left >= 0 && box.right <= innerWidth && element.scrollWidth <= element.clientWidth
        );
      });
      expect(detailFits).toBe(true);
      await reader.press('Escape');
      await expect(reader).toBeHidden();
      await expect(page.getByRole('button', { name: 'Journaux de Cotes Stake' })).toBeFocused();
    });
  }
}

test('journal filters, empty states and sheet dismissal at small heights with reduced motion', async ({
  page,
}) => {
  await installWorkerLogsFixture(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?view=admin');
  await page.getByRole('button', { name: /Services .*disponibles/ }).click();
  await page.getByRole('button', { name: 'Journaux de Cotes Stake' }).click();
  const reader = page.getByRole('dialog', { name: 'Cotes Stake' });
  await expect(reader.locator('.log-line')).toHaveCount(3);
  await reader.getByRole('combobox', { name: 'Exécution' }).click();
  const option = page.getByRole('option', { name: /Stake · cotes/ });
  const optionBox = (await option.boundingBox())!;
  expect(optionBox.x).toBeGreaterThanOrEqual(0);
  expect(optionBox.x + optionBox.width).toBeLessThanOrEqual(320);
  await option.click();
  await expect(reader.getByText('Couverture incomplète')).toBeVisible();
  await reader.getByRole('button', { name: 'Filtres', exact: true }).click();
  await reader.getByRole('textbox', { name: 'Rechercher dans les journaux' }).fill('introuvable');
  await expect(reader.getByText('Aucun événement pour ces filtres.')).toBeVisible();
  const list = reader.locator('.log-lines-scroll');
  expect((await list.boundingBox())!.height).toBeGreaterThan(90);
  await reader.getByRole('button', { name: 'Effacer les filtres' }).click();
  await expect(reader.locator('.log-line')).toHaveCount(3);
  await page.setViewportSize({ width: 844, height: 390 });
  expect((await list.boundingBox())!.height).toBeGreaterThan(60);
  await reader.press('Escape');
  await expect(reader).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Journaux de Cotes Stake' }).click();
  const grip = reader.getByRole('button', { name: 'Fermer la fenêtre, glisser vers le bas' });
  const box = (await grip.boundingBox())!;
  const x = box.x + box.width / 2,
    y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + 200, { steps: 8 });
  await page.mouse.up();
  await expect(reader).toBeHidden();
  await expect(page.getByRole('button', { name: 'Journaux de Cotes Stake' })).toBeFocused();
});
