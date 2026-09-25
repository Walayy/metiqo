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

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 390, 768, 1440]) {
    test(`the odds cue fits match rows at ${width}px in ${theme} mode`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');
      const league = page.locator('.league-accordion').filter({ hasText: 'LCK' }).first();
      await league.locator('.league-trigger').click();
      const fixture = league.locator('.fixture-row').filter({
        has: page.locator('.fixture-odds-tab'),
      });
      const cue = fixture.locator('.fixture-odds-tab').filter({ visible: true });
      await expect(league.locator('.fixture-odds-tab').filter({ visible: true })).toHaveCount(1);
      await expect(cue).toBeEmpty();
      await expect(page.locator('.match-odds-legend')).toHaveText(
        'Cotes Stake dans le détail du match',
      );
      await expect(fixture).toHaveAttribute('aria-label', /cotes consultables dans le détail/);
      const cueBox = await cue.boundingBox();
      const rowBox = await fixture.boundingBox();
      expect(cueBox).not.toBeNull();
      expect(rowBox).not.toBeNull();
      expect(cueBox!.x).toBeGreaterThanOrEqual(rowBox!.x);
      expect(cueBox!.x + cueBox!.width).toBeLessThanOrEqual(rowBox!.x + rowBox!.width);
      expect(cueBox!.y).toBeGreaterThanOrEqual(rowBox!.y);
      expect(cueBox!.y + cueBox!.height).toBeLessThanOrEqual(rowBox!.y + rowBox!.height);
      const timeBox = await fixture.locator('.fixture-time').boundingBox();
      const scoreBox = await fixture.locator('.fixture-score').boundingBox();
      const legendBox = await page.locator('.match-odds-legend').boundingBox();
      const resultsBox = await page.locator('.match-results').boundingBox();
      expect(timeBox).not.toBeNull();
      expect(scoreBox).not.toBeNull();
      expect(legendBox).not.toBeNull();
      expect(resultsBox).not.toBeNull();
      if (width <= 680) {
        expect(cueBox!.y).toBeLessThan(scoreBox!.y + scoreBox!.height / 2);
        expect(Math.abs(cueBox!.x + cueBox!.width / 2 - scoreBox!.x - scoreBox!.width / 2)).toBeLessThan(2);
        expect(legendBox!.y + legendBox!.height).toBeLessThanOrEqual(resultsBox!.y);
      } else {
        expect(cueBox!.x).toBeGreaterThan(timeBox!.x + timeBox!.width / 2);
        expect(legendBox!.y).toBeGreaterThanOrEqual(resultsBox!.y + resultsBox!.height);
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
      ).toBeLessThanOrEqual(1);
      if (width === 390 && theme === 'light') {
        await page.emulateMedia({ reducedMotion: 'reduce' });
        const duration = await cue.evaluate((element) =>
          Number.parseFloat(getComputedStyle(element).transitionDuration),
        );
        expect(duration).toBeLessThan(0.001);
      }
      if (width === 1440 && theme === 'dark') {
        await fixture.focus();
        await fixture.press('Enter');
      } else {
        await fixture.click();
      }
      await expect(page.getByRole('button', { name: /Cotes & résultats/ })).toBeVisible();
    });
  }
}
