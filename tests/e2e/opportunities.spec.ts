import { expect, test } from "@playwright/test";

test("shows admissible opportunities sorted by conservative EV", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Opportunités" })).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Résumé du dashboard" })
      .getByRole("region", { name: "Opportunités admissibles" }),
  ).toContainText("2");

  const rows = page.getByRole("row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1)).toContainText("Aurore 02");
  await expect(rows.nth(1)).toContainText("+8,0 %");
  await expect(rows.nth(2)).toContainText("Aurore 10");
  await expect(rows.nth(2)).toContainText("Baisse 0,60");
});

test("keeps filters and display choices shareable in the URL", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Équipe").fill("Aurore 10");
  await page.getByRole("button", { name: "Appliquer" }).click();
  await expect(page).toHaveURL(/team=Aurore(?:\+|%20)10/);
  await expect(page.getByRole("row")).toHaveCount(2);
  await expect(page.getByRole("row").nth(1)).toContainText("Aurore 10");

  await page.getByRole("link", { name: "Vue cartes" }).click();
  await expect(page).toHaveURL(/display=cards/);
  await expect(page.getByTestId("opportunity-card-view")).toBeVisible();

  await page.getByLabel("Trier par").selectOption("start-asc");
  await expect(page).toHaveURL(/sort=start-asc/);
});

test("renders an explicit no-opportunity state", async ({ page }) => {
  await page.goto("/?competition=aucune-ligue");

  await expect(
    page.getByRole("heading", { level: 2, name: "Aucune opportunité admissible" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Réinitialiser les filtres" })).toBeVisible();
});

test("keeps a stale snapshot visible but clearly blocks the decision", async ({ page }) => {
  await page.goto("/?eligibility=all&freshness=stale");

  await expect(
    page.getByRole("heading", { level: 2, name: "Données anciennes — décision bloquée" }),
  ).toBeVisible();
  await expect(page.getByRole("row").nth(1)).toContainText("Aurore 03");
  await expect(page.getByRole("row").nth(1)).toContainText("Bloqué");
  await expect(page.getByRole("row").nth(1)).toContainText("Ancienne");
});

test("keeps the card dashboard within a mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/?display=cards");

  await expect(page.getByTestId("opportunity-card-view")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ouvrir la navigation" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  const screenshotPath = testInfo.outputPath("opportunities-mobile.png");
  await page.screenshot({ fullPage: true, path: screenshotPath });
  await testInfo.attach("opportunities-mobile", {
    contentType: "image/png",
    path: screenshotPath,
  });
});

test("contains the wide table at an intermediate desktop width", async ({ page }) => {
  await page.setViewportSize({ height: 900, width: 1132 });
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Opportunités admissibles", exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  const tableRegion = page.getByRole("region", {
    name: "Tableau des opportunités, défilement horizontal disponible",
  });
  await expect(tableRegion).toBeVisible();
  expect(await tableRegion.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
    true,
  );
});
