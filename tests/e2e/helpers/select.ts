import { expect, type Locator, type Page } from "@playwright/test";

/** Exercise the visible shared select, including its portalled menu. */
export async function chooseSelectOption(page: Page, trigger: Locator, optionLabel: string) {
  await trigger.click();
  // While Radix exposes its modal portal, the trigger's containing region can be aria-hidden.
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.getByRole("option", { name: optionLabel, exact: true }).click();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(trigger).toHaveText(optionLabel);
}
