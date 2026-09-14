import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const screens = [
  ["opportunities", "/", "Opportunités"],
  ["events", "/events", "Événements"],
  ["odds", "/odds", "Cotes"],
  ["event", "/events/1c6f28ad-4fdb-5a42-ac9e-90a863037d49", "Aurore 02 vs Bastion 02"],
  ["signal", "/opportunities/f31e365e-ab44-53b2-b839-e1b9f2e3625b", "Aurore 02 vs Bastion 02"],
  ["models", "/models", "Modèles & backtests"],
  ["data", "/data", "Santé des données"],
  ["admin", "/admin", "Administration"],
  ["paper", "/paper-trading", "Paper trading"],
  ["paper-detail", "/paper-trading/cef9c5cf-d14f-51dc-a417-91909b3088ba", "Paper bet"],
  ["settings", "/settings", "Paramètres"],
] as const;

for (const width of [320, 390, 768, 1024, 1440, 1920]) {
  for (const theme of ["light", "dark"] as const) {
    test(`audits every route at ${width.toString()}px in ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(180_000);
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => {
        localStorage.setItem("metiquo-theme", value);
      }, theme);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const [name, path, title] of screens) {
        await test.step(name, async () => {
          await page.goto(path);
          await expect(
            page.getByRole("heading", { level: 1, name: title, exact: true }),
          ).toBeVisible();
          await page.waitForLoadState("networkidle");
          const layout = await page.evaluate(() => {
            const root = document.documentElement;
            const main = document.querySelector("main");
            if (!main) throw new Error("Main content missing");
            const verticalTableScroll = Array.from(document.querySelectorAll(".ui-table-region"))
              .filter((element) => element.scrollHeight > element.clientHeight + 2)
              .map((element) => element.getAttribute("aria-label"));
            return {
              rootOverflow: root.scrollWidth - root.clientWidth,
              mainOverflow: main.scrollWidth - main.clientWidth,
              verticalTableScroll,
              theme: root.getAttribute("data-theme"),
            };
          });
          expect.soft(layout.rootOverflow, `${path}: document overflow`).toBeLessThanOrEqual(1);
          expect.soft(layout.mainOverflow, `${path}: main overflow`).toBeLessThanOrEqual(1);
          expect.soft(layout.verticalTableScroll, `${path}: nested vertical scroll`).toEqual([]);
          expect.soft(layout.theme).toBe(theme);
          if (width === 320 || width === 1440) {
            const result = await new AxeBuilder({ page })
              .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
              .analyze();
            expect
              .soft(
                result.violations.map(({ id, nodes }) => ({
                  id,
                  nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })),
                })),
                `${path}: accessibility`,
              )
              .toEqual([]);
            await page.screenshot({
              animations: "disabled",
              fullPage: true,
              path: testInfo.outputPath(`${name}-${width.toString()}-${theme}.png`),
            });
          }
        });
      }
      expect(errors).toEqual([]);
    });
  }
}

test("keeps all mobile navigation links reachable on a short landscape screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 667, height: 320 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Ouvrir la navigation" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Navigation", exact: true });
  await expect(dialog).toBeVisible();
  const settings = dialog.getByRole("link", { name: "Paramètres", exact: true });
  await settings.focus();
  const bounds = await settings.boundingBox();
  if (!bounds) throw new Error("Settings link missing");
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(320);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("keeps sidebar appearance controls reachable on a short desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 400 });
  await page.goto("/");
  const theme = page.getByRole("button", { name: "Changer le thème" });
  await theme.focus();
  const bounds = await theme.boundingBox();
  if (!bounds) throw new Error("Theme button missing");
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(400);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitemradio", { name: "Système" })).toBeChecked();
  await page.getByRole("menuitemradio", { name: "Sombre" }).click();
  await theme.click();
  await expect(page.getByRole("menuitemradio", { name: "Sombre" })).toBeChecked();
});

test("offers an accessible return route for an unknown address without forced vertical scroll", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/page-inexistante-audit");
  await expect(page.getByRole("heading", { level: 1, name: "Page introuvable" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900);
  await page.getByRole("link", { name: "Revenir aux opportunités" }).click();
  await expect(page.getByRole("heading", { name: "Opportunités", level: 1 })).toBeVisible();
});
