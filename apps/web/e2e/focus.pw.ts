import { expect, test } from '@playwright/test';

test.use({ hasTouch: true });

test('the mobile sheet keeps keyboard focus visible without outlining its full width', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  const openNavigation = page.getByRole('button', { name: 'Ouvrir la navigation' });
  await openNavigation.focus();
  await openNavigation.press('Enter');

  const dialog = page.getByRole('dialog', { name: 'Navigation' });
  const grip = dialog.getByRole('button', { name: 'Fermer la fenêtre, glisser vers le bas' });
  await expect(grip).toBeFocused();
  await expect(grip).toHaveCSS('outline-style', 'none');
  expect(await grip.evaluate((element) => getComputedStyle(element, '::before').outlineStyle)).toBe(
    'solid',
  );

  await dialog.press('Escape');
  await expect(dialog).toBeHidden();
  await openNavigation.tap();
  await expect(grip).toBeFocused();
  await expect(grip).toHaveCSS('outline-style', 'none');
  expect(await grip.evaluate((element) => getComputedStyle(element, '::before').outlineStyle)).toBe(
    'none',
  );

  await grip.press('Tab');
  const close = dialog.getByRole('button', { name: 'Fermer', exact: true });
  await expect(close).toBeFocused();
  await expect(close).toHaveCSS('outline-style', 'solid');
});

test('a touched text field keeps its caret without a persistent focus ring', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Matchs', exact: true })).toBeVisible();

  const search = page.getByRole('textbox', { name: 'Rechercher un match' });
  await search.tap();
  await expect(search).toBeFocused();
  await expect(search.locator('..')).toHaveCSS('outline-style', 'none');
  await search.pressSequentially('T1');
  await expect(search).toHaveValue('T1');
  await expect(search.locator('..')).toHaveCSS('outline-style', 'none');

  await search.press('Tab');
  const clearSearch = page.getByRole('button', { name: 'Effacer la recherche de match' });
  await expect(clearSearch).toBeFocused();
  await expect(clearSearch).toHaveCSS('outline-style', 'solid');
});

test('focus rings stay on keyboard controls, not programmatic page regions', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Matchs', exact: true })).toBeVisible();
  await page.keyboard.press('Tab');
  const skipLink = page.getByRole('link', { name: 'Aller au contenu principal' });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS('outline-style', 'solid');

  await skipLink.press('Enter');
  const main = page.locator('#main-content');
  await expect(main).toBeFocused();
  await expect(main).toHaveCSS('outline-style', 'none');

  const theme = page.getByRole('button', { name: /Activer le thème/ });
  await theme.click();
  await expect(theme).toHaveCSS('outline-style', 'none');
});
