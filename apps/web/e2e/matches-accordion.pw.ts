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
  await expect(fixture).toHaveAttribute('aria-label', /DN SOOPers Challengers contre/);
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
    /DN SOOPers Challengers contre/,
  );

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await trigger.click();
  await expect(content).toBeHidden();
  await trigger.click();
  await expect(content).toHaveCSS('animation-name', 'none');
});
