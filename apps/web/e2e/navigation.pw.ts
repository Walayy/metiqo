import { expect, test } from '@playwright/test';

test('the mock interface opens Matchs by default and can navigate to Les values', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/');
  await expect(page).toHaveTitle('Matchs · Metiquo');
  await expect(page.getByRole('heading', { name: 'Matchs' })).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Navigation principale' })
    .getByRole('button', { name: 'Les values' })
    .click();

  await expect(page).toHaveTitle('Les values · Metiquo');
  await expect(page).toHaveURL(/view=values/);
  await expect(page.getByRole('heading', { name: 'Une longueur d’avance.' })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
