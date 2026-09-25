import { expect, test } from '@playwright/test';

const adminId = '11111111-1111-4111-8111-111111111111';
const createdAt = '2026-09-24T09:00:00Z';

async function useAdminResponses(page: import('@playwright/test').Page) {
  await page.addInitScript(
    ({ id, at }) => {
      const users = [
        {
          id,
          email: 'admin@example.test',
          role: 'admin',
          disabled: false,
          verified: true,
          createdAt: at,
          sessions: 2,
        },
        {
          id: '22222222-2222-4222-8222-222222222222',
          email: 'long-administrator.account@example.test',
          role: 'user',
          disabled: false,
          verified: false,
          createdAt: at,
          sessions: 0,
        },
        {
          id: '33333333-3333-4333-8333-333333333333',
          email: 'member@example.test',
          role: 'user',
          disabled: true,
          verified: true,
          createdAt: at,
          sessions: 1,
        },
        {
          id: '44444444-4444-4444-8444-444444444444',
          email: 'viewer@example.test',
          role: 'user',
          disabled: false,
          verified: true,
          createdAt: at,
          sessions: 0,
        },
      ];
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = input instanceof Request ? input.url : String(input);
        const path = new URL(url, location.href).pathname;
        if (path === '/api/v1/auth/session') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                user: { id, email: 'admin@example.test', role: 'admin', createdAt: at },
                expiresAt: '2026-12-01T00:00:00Z',
              }),
              {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              },
            ),
          );
        }
        if (path === '/api/v1/admin/users') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ items: users, total: users.length, page: 1, pageSize: 20 }),
              {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              },
            ),
          );
        }
        return originalFetch(input, init);
      };
    },
    { id: adminId, at: createdAt },
  );
}

for (const { width, height, theme } of [
  { width: 390, height: 844, theme: 'dark' },
  { width: 390, height: 844, theme: 'light' },
  { width: 768, height: 1024, theme: 'light' },
  { width: 768, height: 1024, theme: 'dark' },
  { width: 1440, height: 900, theme: 'dark' },
  { width: 1440, height: 900, theme: 'light' },
] as const) {
  test(`users layout ${width}px ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: theme });
    await useAdminResponses(page);
    await page.goto('/?view=users');
    const title = page.getByRole('heading', { name: /Utilisateurs/ });
    await expect(title).toHaveCount(1);
    const rows = page.locator('.admin-user-row[aria-label]');
    await expect(rows).toHaveCount(4);
    const count = title.locator('.count-pill');
    await expect(count).toHaveText('4');
    const aligned = await title.evaluate((element) => {
      const label = element.querySelector(':scope > span:first-child')!.getBoundingClientRect();
      const pill = element.querySelector('.count-pill')!.getBoundingClientRect();
      return Math.abs((label.top + label.bottom) / 2 - (pill.top + pill.bottom) / 2);
    });
    expect(aligned).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );

    const trigger = page.getByRole('button', { name: 'Afficher mon profil' });
    await expect(trigger).toBeVisible();
    if (width <= 900) {
      await expect(trigger.locator('.account-trigger-label')).toBeHidden();
      expect((await trigger.boundingBox())!.width).toBe(44);
      await expect(rows.first().locator('.user-role')).toBeHidden();
      await expect(rows.first().locator('.user-sessions')).toBeHidden();
    } else {
      await expect(trigger.locator('.account-trigger-label')).toBeVisible();
      await expect(rows.first().locator('.user-role')).toBeVisible();
    }
    if (process.env.UI_CAPTURE) {
      await page.screenshot({ path: `test-results/users-${width}-${theme}.png`, fullPage: true });
    }
    await rows.first().getByRole('button', { name: 'Gérer admin@example.test' }).click();
    const dialog = page.getByRole('dialog', { name: 'Gérer l’utilisateur' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('Inscription')).toBeVisible();
    await expect(dialog.getByText('Sessions', { exact: true })).toBeVisible();
    if (process.env.UI_CAPTURE && width <= 900) {
      await page.waitForTimeout(350);
      await page.screenshot({ path: `test-results/users-editor-${width}-${theme}.png` });
    }
    if (width <= 600) {
      const formClose = dialog
        .locator('.admin-form-actions')
        .getByRole('button', { name: 'Fermer' });
      await formClose.scrollIntoViewIfNeeded();
      await expect(formClose).toBeVisible();
    }
    await dialog.press('Escape');
    await expect(dialog).toBeHidden();
    await trigger.click();
    await expect(page.getByRole('dialog', { name: 'Votre profil' })).toBeVisible();
  });
}

for (const width of [390, 768] as const) {
  test(`guest account access ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = input instanceof Request ? input.url : String(input);
        if (new URL(url, location.href).pathname === '/api/v1/auth/session') {
          return Promise.resolve(
            new Response(JSON.stringify({ user: null, expiresAt: null }), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
          );
        }
        return originalFetch(input, init);
      };
    });
    await page.goto('/');
    const trigger = page.getByRole('button', { name: 'Se connecter ou s’inscrire' });
    await expect(trigger).toBeVisible();
    await expect(trigger.locator('.account-trigger-label')).toBeHidden();
    expect((await trigger.boundingBox())!.width).toBe(44);
    if (process.env.UI_CAPTURE) {
      await page.screenshot({ path: `test-results/guest-${width}.png` });
    }
    await trigger.focus();
    await trigger.press('Enter');
    await expect(page.getByRole('dialog', { name: 'Bienvenue sur Metiquo' })).toBeVisible();
  });
}

test('users layout stays within the viewport across breakpoints', async ({ page }) => {
  await useAdminResponses(page);
  await page.goto('/?view=users');
  const rows = page.locator('.admin-user-row[aria-label]');
  await expect(rows).toHaveCount(4);
  for (const width of [320, 360, 390, 600, 601, 680, 768, 900, 901, 1024, 1100, 1101, 1280, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    const geometry = await page.evaluate(() => {
      const first = document.querySelector('.admin-user-row[aria-label]')!.getBoundingClientRect();
      const action = document.querySelector('.admin-user-action')!.getBoundingClientRect();
      return {
        scrollWidth: document.documentElement.scrollWidth,
        left: first.left,
        right: first.right,
        actionWidth: action.width,
      };
    });
    expect(geometry.scrollWidth, `${width}px overflow`).toBeLessThanOrEqual(width);
    expect(geometry.left, `${width}px left edge`).toBeGreaterThanOrEqual(0);
    expect(geometry.right, `${width}px right edge`).toBeLessThanOrEqual(width);
    expect(geometry.actionWidth, `${width}px action width`).toBeGreaterThanOrEqual(44);
  }
});
