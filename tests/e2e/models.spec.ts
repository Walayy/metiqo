import { expect, test } from "@playwright/test";
import { chooseSelectOption } from "./helpers/select.js";

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

test("makes calibration and backtests directly accessible before browsing all model cards", async ({
  page,
}) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/models");
  const navigation = page.getByRole("navigation", { name: "Sections des modèles" });
  await expect(navigation).toBeVisible();
  const calibration = page.getByRole("region", {
    name: "Calibration et comparaison aux baselines",
  });
  expect(
    await calibration.evaluate((element) => {
      const champions = document.getElementById("model-champions");
      return (
        champions !== null &&
        Boolean(element.compareDocumentPosition(champions) & Node.DOCUMENT_POSITION_FOLLOWING)
      );
    }),
  ).toBe(true);
  await chooseSelectOption(
    page,
    calibration.getByRole("combobox", { name: "Version affichée" }),
    "mock-mw-v1-outsider_value · champion",
  );
  await navigation.getByRole("link", { name: "Backtests", exact: true }).click();
  const backtests = page.getByRole("region", {
    name: "Performance temporelle et segments",
    exact: true,
  });
  await expect(backtests.getByRole("heading", { level: 2 })).toBeInViewport();
  await navigation.getByRole("link", { name: "Champions", exact: true }).click();
  const card = page.getByRole("region", { name: "Modèle mock-mw-v1-low_value", exact: true });
  await expect(card.getByRole("button", { name: "Retirer", exact: true })).toBeVisible();
  await expect(card.locator("details")).not.toHaveAttribute("open");
  await card.getByText("Traçabilité et promotion", { exact: true }).click();
  await expect(card.getByText("Version exacte de prédiction", { exact: true })).toBeVisible();
  await expect(
    card.getByText("Validation walk-forward et calibration mock", { exact: true }),
  ).toBeVisible();
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
  expect(await tableRegion.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
    true,
  );
  await expect(tableRegion.getByRole("columnheader", { name: "Segment" })).toBeAttached();
  await expect(
    tableRegion.getByRole("cell", { name: "Game winner · global" }).first(),
  ).toBeVisible();
});
