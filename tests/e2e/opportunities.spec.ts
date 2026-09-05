import { expect, test } from "@playwright/test";

import type { PageResponseOpportunity } from "../../packages/contracts/src/generated/types.gen.js";

const REFRESHED_SIGNAL_ID = "99999999-9999-4999-8999-999999999999";

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
  await expect(rows.nth(2)).toContainText("4,20");
  await expect(rows.nth(2)).toContainText("Cote mise à jour");
  await expect(rows.nth(2)).toContainText("3,60");
  await expect(rows.nth(2)).toContainText("Baisse 0,60");
});

test("keeps the existing signal row mounted while polling for fresh odds", async ({ page }) => {
  let requestCount = 0;
  let announceRefresh: (() => void) | undefined;
  let releaseRefresh: (() => void) | undefined;
  const refreshStarted = new Promise<void>((resolve) => {
    announceRefresh = resolve;
  });
  const refreshReleased = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });

  await page.clock.install({ time: new Date("2026-09-05T12:00:00Z") });
  await page.route("**/api/backend/api/v1/opportunities?**", async (route) => {
    requestCount += 1;
    const response = await route.fetch();
    if (requestCount > 1) {
      announceRefresh?.();
      await refreshReleased;
      const payload = (await response.json()) as PageResponseOpportunity;
      const sourceSignal = payload.data.find(
        (opportunity) => opportunity.event.teamA === "Aurore 10",
      );
      if (!sourceSignal) throw new Error("Signal mock de changement de cote absent");
      const refreshedSignal = {
        ...sourceSignal,
        book: {
          ...sourceSignal.book,
          capturedAt: "2026-09-04T12:05:00Z",
          decimalOdds: "3.60",
          oddsSnapshotId: "88888888-8888-4888-8888-888888888888",
        },
        meta: {
          ...sourceSignal.meta,
          asOf: "2026-09-04T12:05:00Z",
          computedAt: "2026-09-04T12:05:01Z",
        },
        signalId: REFRESHED_SIGNAL_ID,
      };
      await route.fulfill({
        response,
        json: {
          ...payload,
          data: [refreshedSignal, ...payload.data],
          page: { ...payload.page, total: payload.page.total + 1 },
        },
      });
      return;
    }
    await route.fulfill({ response });
  });

  await page.goto("/");
  const signalRow = page.getByRole("row").filter({ hasText: "Aurore 02" });
  await expect(signalRow).toBeVisible();
  const rowBeforeRefresh = await signalRow.elementHandle();

  await page.clock.fastForward(30_001);
  await refreshStarted;
  await expect(signalRow).toBeVisible();
  const rowDuringRefresh = await signalRow.elementHandle();
  expect(
    await rowBeforeRefresh.evaluate((node, currentNode) => node === currentNode, rowDuringRefresh),
  ).toBe(true);

  releaseRefresh?.();
  await expect(page.locator(`tr[data-signal-id="${REFRESHED_SIGNAL_ID}"]`)).toBeVisible();
  await expect(signalRow).toBeVisible();
  await expect(page.locator('[data-refetching="true"]')).toHaveCount(0);
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
  await page.goto("/?eligibility=all&freshness=stale&grade=BLOCKED");

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
