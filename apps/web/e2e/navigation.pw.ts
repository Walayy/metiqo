import { expect, test } from '@playwright/test';

test('the mock interface loads and opens Matchs', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Une longueur d’avance.' })).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Navigation principale' })
    .getByRole('button', { name: 'Matchs' })
    .click();

  await expect(page).toHaveTitle('Matchs · Metiquo');
  await expect(page.getByRole('heading', { name: 'Matchs' })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
