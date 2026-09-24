import { expect, test } from '@playwright/test';

test('match accordions animate in both directions and keep team names accessible', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/');
  const league = page
    .locator('.league-accordion')
    .filter({ hasText: 'World Star Challengers Invitational' });
  const trigger = league.locator('.league-trigger');
  const content = league.locator('.ui-accordion-content');
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(content).toBeVisible();
  await expect(content).toHaveCSS('animation-name', 'accordion-expand');
  const fixture = content.locator('.fixture-row').first();
  const accessibleName = await fixture.getAttribute('aria-label');
  expect(accessibleName).toMatch(/.+ contre .+, .*voir le match/);
  await expect(fixture.locator('.fixture-team-copy').first()).toBeVisible();

  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'accordion-collapse');
  await expect(content).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  await trigger.click();
  await expect(content).toBeVisible();
  await expect(content.locator('.fixture-team-copy').first()).toBeHidden();
  await expect(content.locator('.fixture-team .logo-frame').first()).toBeVisible();
  await expect(content.locator('.fixture-row').first()).toHaveAttribute(
    'aria-label',
    accessibleName!,
  );

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await trigger.click();
  await expect(content).toBeHidden();
  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'none');
});

test('match odds expand without moving the dialog and adapt to a narrower screen', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/');
  const league = page.locator('.league-accordion').filter({ hasText: 'LPL' }).first();
  await league.locator('.league-trigger').click();
  await league.locator('.fixture-row').first().click();

  const dialog = page.locator('.match-dialog');
  const trigger = dialog.getByRole('button', { name: /Cotes & résultats/ });
  const content = dialog.locator('.match-odds-section .ui-disclosure-content');
  await expect(trigger).toBeVisible();
  await expect.poll(async () => (await dialog.boundingBox())?.y).toBe(70);
  const before = await dialog.boundingBox();
  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'accordion-expand');
  await expect(content).toBeVisible();
  const afterOpen = await dialog.boundingBox();
  expect(afterOpen?.y).toBeCloseTo(before!.y, 0);
  expect(afterOpen?.height).toBeCloseTo(before!.height, 0);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      content.evaluate((element) =>
        Math.abs(element.getBoundingClientRect().height - element.scrollHeight),
      ),
    )
    .toBeLessThan(1);
  await expect(dialog.getByRole('region', { name: 'Vainqueur de la carte 1' })).toBeVisible();

  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'accordion-collapse');
  await expect(content).toBeHidden();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'none');
});
