import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

test('mobile dialogs snap, reopen, dismiss, and restore focus', async ({ page }) => {
  await page.goto('/');
  const trigger = page.getByRole('button', { name: 'Filtres' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Affiner les opportunités' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Réduire la fenêtre' })).toBeFocused();
  await expect(dialog).toHaveAttribute('data-sheet-interacted', 'true');
  const expandedTop = await dialog.evaluate((element) => element.getBoundingClientRect().top);
  const grip = dialog.locator('.modal-sheet-grip');
  const box = await grip.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + 200, { steps: 8 });
  await page.mouse.up();
  await expect(dialog.getByRole('button', { name: 'Agrandir la fenêtre' })).toBeVisible();
  await expect
    .poll(() => dialog.evaluate((element) => element.getBoundingClientRect().top))
    .toBeGreaterThan(expandedTop + 50);

  await dialog.getByRole('button', { name: 'Agrandir la fenêtre' }).press('ArrowUp');
  await expect(dialog.getByRole('button', { name: 'Réduire la fenêtre' })).toBeVisible();
  await expect
    .poll(() => dialog.evaluate((element) => element.getBoundingClientRect().top))
    .toBeLessThan(expandedTop + 10);

  await dialog.getByRole('button', { name: 'Réduire la fenêtre' }).click();
  await expect(dialog.getByRole('button', { name: 'Agrandir la fenêtre' })).toBeVisible();
  const compactBox = await dialog.locator('.modal-sheet-grip').boundingBox();
  expect(compactBox).not.toBeNull();
  const compactY = compactBox!.y + compactBox!.height / 2;
  await page.mouse.move(x, compactY);
  await page.mouse.down();
  await page.mouse.move(x, compactY + 180, { steps: 8 });
  await page.mouse.up();
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('the email dialog avoids an automatic mobile keyboard and respects reduced motion', async ({
  page,
}) => {
  // Stub the anonymous session before MSW starts; service workers bypass page.route in CI.
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (new URL(url, location.href).pathname === '/api/v1/auth/session')
        return Promise.resolve(
          new Response(JSON.stringify({ user: null, expiresAt: null }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      return originalFetch(input, init);
    };
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const trigger = page.getByRole('button', { name: 'Se connecter ou s’inscrire' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Bienvenue sur Metiquo' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Réduire la fenêtre' })).toBeFocused();
  await expect(dialog).toHaveCSS('animation-name', 'none');
  await dialog.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.getByRole('button', { name: 'Filtres' }).click();
  const desktop = page.getByRole('dialog', { name: 'Affiner les opportunités' });
  await expect(desktop).toBeVisible();
  await expect(desktop.locator('.modal-sheet-grip')).toBeHidden();
  const box = await desktop.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThan(0);
  expect(box!.x + box!.width).toBeLessThan(768);
});
