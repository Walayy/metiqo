import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

test('mobile sheets return after a short pull and dismiss in one downward swipe', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Matchs', exact: true })).toBeVisible();
  const trigger = page.getByRole('button', { name: 'Ouvrir la navigation' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Navigation' });
  await expect(dialog).toBeVisible();
  const grip = dialog.getByRole('button', { name: 'Fermer la fenêtre, glisser vers le bas' });
  await expect(grip).toBeFocused();
  await expect(dialog).toHaveAttribute('data-sheet-interacted', 'true');
  const expandedTop = await dialog.evaluate((element) => element.getBoundingClientRect().top);
  const box = await grip.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await expect(dialog).toHaveAttribute('data-sheet-dragging', 'true');
  await expect
    .poll(() => grip.evaluate((element) => getComputedStyle(element, '::before').width))
    .toBe('54px');
  expect(
    await grip.evaluate((element) => getComputedStyle(element, '::before').animationName),
  ).toBe('sheet-grip-shimmer');
  await page.mouse.move(x, y + 20, { steps: 4 });
  await page.mouse.up();
  await expect(dialog).toBeVisible();
  await expect
    .poll(() => dialog.evaluate((element) => element.getBoundingClientRect().top))
    .toBeLessThan(expandedTop + 10);

  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + 205, { steps: 8 });
  await page.mouse.move(x, y + 199, { steps: 2 });
  await page.mouse.up();
  await expect(dialog).toBeVisible();
  await expect
    .poll(() => dialog.evaluate((element) => element.getBoundingClientRect().top))
    .toBeLessThan(expandedTop + 10);

  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + 200, { steps: 8 });
  await page.mouse.up();
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

for (const theme of ['light', 'dark'] as const) {
  test(`mobile sheet content follows held touches and springs back in ${theme} mode`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.setViewportSize({ width: 390, height: 500 });
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.getByRole('button', { name: 'Ouvrir la navigation' }).click();
    const dialog = page.getByRole('dialog', { name: 'Navigation' });
    const scroller = dialog.locator('.sidebar-inner');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('data-sheet-interacted', 'true');
    await expect
      .poll(() => scroller.evaluate((element) => element.scrollHeight - element.clientHeight))
      .toBeGreaterThan(20);

    const session = await page.context().newCDPSession(page);
    const box = await scroller.boundingBox();
    expect(box).not.toBeNull();
    const x = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    const offset = () =>
      scroller.evaluate((element) => {
        const firstChild = element.firstElementChild;
        if (!firstChild) return 0;
        const value = getComputedStyle(firstChild).translate.split(' ')[1];
        return Number.parseFloat(value ?? '0') || 0;
      });
    const touch = async (type: 'touchStart' | 'touchMove' | 'touchEnd', position: number) => {
      await session.send('Input.dispatchTouchEvent', {
        type,
        touchPoints: type === 'touchEnd' ? [] : [{ x, y: position, id: 1 }],
      });
      await page.waitForTimeout(32);
    };

    await scroller.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    await touch('touchStart', y);
    await touch('touchMove', y - 35);
    const firstBottomPull = await offset();
    await touch('touchMove', y - 90);
    expect(await offset()).toBeLessThan(firstBottomPull - 10);
    await expect(dialog).toBeVisible();
    await touch('touchEnd', y - 90);
    const returningBottom = await offset();
    expect(returningBottom).toBeLessThan(-5);
    await touch('touchStart', y);
    const regrabbedBottom = await offset();
    await touch('touchMove', y - 45);
    expect(await offset()).toBeLessThan(regrabbedBottom - 5);
    await touch('touchEnd', y - 45);
    await expect.poll(offset).toBeGreaterThan(-1);

    await scroller.evaluate((element) => {
      element.scrollTop = 0;
    });
    await touch('touchStart', y);
    await touch('touchMove', y + 35);
    const firstTopPull = await offset();
    await touch('touchMove', y + 90);
    expect(await offset()).toBeGreaterThan(firstTopPull + 10);
    await touch('touchEnd', y + 90);
    const returningTop = await offset();
    expect(returningTop).toBeGreaterThan(5);
    await expect.poll(offset).toBeLessThan(1);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await touch('touchStart', y);
    await touch('touchMove', y + 55);
    expect(await offset()).toBeGreaterThan(5);
    await touch('touchEnd', y + 55);
    expect(await offset()).toBe(0);
    await expect(dialog).toBeVisible();
    await session.detach();
  });
}

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
  await expect(
    dialog.getByRole('button', { name: 'Fermer la fenêtre, glisser vers le bas' }),
  ).toBeFocused();
  await expect(dialog).toHaveCSS('animation-name', 'none');
  await dialog.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await page.goto('/?view=values');
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
