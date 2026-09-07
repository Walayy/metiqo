import { expect, type Locator, type Page } from "@playwright/test";

/** Reach a control using real sequential keyboard navigation, without focus(). */
export async function tabTo(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  await expect(target).toBeEnabled();
  for (let step = 0; step < 100; step += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) {
      const focus = await target.evaluate((element) => {
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        const front = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return {
          outlineWidth: Number.parseFloat(style.outlineWidth),
          outlineStyle: style.outlineStyle,
          shadow: style.boxShadow,
          visible: front === element || (front !== null && element.contains(front)),
        };
      });
      expect(focus.visible, "Le contrôle au focus doit rester visible devant le contenu fixe").toBe(
        true,
      );
      expect(
        (focus.outlineStyle !== "none" && focus.outlineWidth >= 2) || focus.shadow !== "none",
      ).toBe(true);
      return;
    }
    await page.keyboard.press("Tab");
  }
  throw new Error(`Contrôle inaccessible après 100 tabulations : ${await target.innerText()}`);
}

export async function typeAt(page: Page, target: Locator, text: string) {
  await tabTo(page, target);
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type(text);
}

export async function activate(page: Page, target: Locator) {
  await tabTo(page, target);
  await page.keyboard.press("Enter");
}
