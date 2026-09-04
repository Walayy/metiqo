import { expect, test } from "@playwright/test";

test("shows model versions, baselines and walk-forward evidence", async ({ page }) => {
  await page.goto("/models");

  await expect(page.getByRole("heading", { level: 1, name: "Modèles & backtests" })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Résumé des modèles" }).getByRole("region", {
      name: "Champions",
    }),
  ).toContainText("12");
  await expect(
    page.getByRole("region", { name: "Challengers" }).filter({ hasText: "Aucun challenger" }),
  ).toContainText("Aucun challenger");
  await expect(page.getByRole("region", { name: "Modèle mock-mw-v1-low_value" })).toContainText(
    "mock-mw-v1-low_value",
  );

  const calibration = page.getByRole("region", {
    name: "Calibration et comparaison aux baselines",
  });
  await expect(calibration.getByRole("img", { name: /modèle .*baseline/i }).first()).toBeVisible();
  await expect(calibration).toContainText("Une valeur plus basse est préférable");

  const performance = page.getByRole("region", {
    name: "Performance temporelle et segments",
  });
  await expect(performance).toContainText("walk-forward");
  await expect(performance).toContainText("Faible échantillon");
  await expect(
    performance.getByRole("region", { name: "Performance temporelle des backtests" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Capacité des marchés" })).toContainText(
    "MATCH_WINNER",
  );
});

test("contains the models dashboard on mobile without hiding the backtest table", async ({
  page,
}) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/models");

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  const tableRegion = page.getByRole("region", { name: "Performance temporelle des backtests" });
  await expect(tableRegion).toBeVisible();
  expect(await tableRegion.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
    true,
  );
});
