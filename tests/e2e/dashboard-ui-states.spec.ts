import { expect, test } from "@playwright/test";
import type {
  PageResponseOpportunity,
  PaperBet,
} from "../../packages/contracts/src/generated/types.gen.js";

const meta = {
  appVersion: "ui-audit",
  asOf: "2026-09-08T12:00:00Z",
  computedAt: "2026-09-08T12:00:00Z",
  dataMode: "mock",
  freshness: "fresh",
};

function pageResponse(data: readonly unknown[], offset = 0, total = data.length) {
  return { data, meta, page: { limit: 100, offset, total } };
}

function source(providerCode: string) {
  return {
    providerCode,
    checkedAt: meta.computedAt,
    lastSuccessAt: meta.computedAt,
    lastCaptureAt: meta.computedAt,
    status: "operational",
    freshness: "fresh",
    detail: "Source disponible",
    failureCount: 0,
    ageSeconds: 0,
  };
}

test("keeps health panels loading until reads complete and renders every source", async ({
  page,
}) => {
  const pending: (() => void)[] = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(
    /\/api\/backend\/api\/v1\/admin\/(data-sources|ingestion-runs|quality-issues|capabilities)\?/,
    async (route) => {
      await new Promise<void>((resolve) => {
        pending.push(resolve);
      });
      const data = route.request().url().includes("data-sources")
        ? [source("primary-provider"), source(`secondary-${"longidentifier".repeat(12)}`)]
        : [];
      await route.fulfill({ json: pageResponse(data) });
    },
  );
  await page.goto("/data");
  await expect.poll(() => pending.length).toBeGreaterThanOrEqual(4);
  try {
    for (const name of [
      "Catalogue des sources",
      "Tentatives d’ingestion",
      "Capacités par snapshot",
      "Anomalies bloquantes",
      "Quarantaine",
    ]) {
      const panel = page.getByRole("region", { name, exact: true });
      await expect(panel.locator('[data-remote-state="loading"]')).toHaveCount(1);
      await expect(panel.locator('[data-remote-state="empty"]')).toHaveCount(0);
    }
  } finally {
    for (const resume of pending) resume();
  }
  const catalogue = page.getByRole("region", { name: "Catalogue des sources", exact: true });
  await expect(catalogue).toContainText("primary-provider");
  await expect(catalogue).toContainText("secondary-");
  await expect(page.getByRole("region", { name: "Quarantaine", exact: true })).toContainText(
    "Aucun snapshot",
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test("offers the event beyond the first hundred without mobile overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/backend/api/v1/events?**", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    const data = Array.from({ length: offset === 0 ? 100 : 1 }, (_, index) => ({
      eventId: `event-${String(offset + index)}`,
      teamA: `Équipe ${String(offset + index + 1)}`,
      teamB: "Adversaire",
      competition: "Ligue de test",
      startsAt: "2026-09-09T12:00:00Z",
      bestOf: 3,
      status: "scheduled",
    }));
    await route.fulfill({ json: pageResponse(data, offset, 101) });
  });
  await page.goto("/events");
  const pagination = page.getByRole("navigation", { name: "Pagination des événements" });
  await expect(pagination).toContainText("Page 1 sur 2");
  await pagination.getByRole("button", { name: "Page suivante" }).click();
  await expect(page.getByRole("region", { name: "Équipe 101 contre Adversaire" })).toBeVisible();
  await expect(pagination).toContainText("Page 2 sur 2");
  await expect(pagination.getByRole("button", { name: "Page suivante" })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await pagination.getByRole("button", { name: "Page précédente" }).click();
  await expect(pagination).toContainText("Page 1 sur 2");
});

test("presents missing model evidence as unavailable and explains empty sections", async ({
  page,
}) => {
  await page.route("**/api/backend/api/v1/models?**", (route) =>
    route.fulfill({
      json: pageResponse([
        {
          algorithm: "Logistic regression",
          modelVersion: "candidate-without-evidence",
          modelVersionId: "test-candidate",
          status: "candidate",
          metrics: {},
          baselineMetrics: {},
          featureVersion: "features-v1",
          promotionReason: null,
          promotedAt: null,
        },
      ]),
    }),
  );
  await page.route("**/api/backend/api/v1/backtests?**", (route) =>
    route.fulfill({ json: pageResponse([]) }),
  );
  await page.goto("/models");
  const model = page.getByRole("region", {
    name: "Modèle candidate-without-evidence",
    exact: true,
  });
  await expect(model.getByText("N/D", { exact: true })).toHaveCount(2);
  await expect(page.getByRole("heading", { name: "Aucun champion actif" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Métriques indisponibles" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Aucun backtest", exact: true })).toBeVisible();
});

test("does not call missing sources healthy or an hour-old snapshot current", async ({ page }) => {
  await page.route("**/api/backend/api/v1/opportunities?**", async (route) => {
    const response = await route.fetch();
    const result = (await response.json()) as PageResponseOpportunity;
    for (const opportunity of result.data) {
      opportunity.book.capturedAt = new Date(
        Date.parse(result.meta.computedAt) - 3_600_000,
      ).toISOString();
    }
    await route.fulfill({ json: result });
  });
  await page.route("**/api/backend/api/v1/admin/data-sources?**", (route) =>
    route.fulfill({ json: pageResponse([]) }),
  );
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Santé des sources", exact: true })).toContainText(
    "Non disponible",
  );
  await expect(
    page.getByRole("region", { name: "Dernière mise à jour", exact: true }),
  ).toContainText("Il y a 1 h");
});

test("keeps opportunity display and sort when paging and resets the page on filtering", async ({
  page,
}) => {
  let fixture: PageResponseOpportunity | undefined;
  const reads: URLSearchParams[] = [];
  await page.route("**/api/backend/api/v1/opportunities?**", async (route) => {
    const requestUrl = new URL(route.request().url());
    reads.push(requestUrl.searchParams);
    if (!fixture) {
      const response = await route.fetch();
      fixture = (await response.json()) as PageResponseOpportunity;
    }
    const offset = Number(requestUrl.searchParams.get("offset"));
    await route.fulfill({
      json: {
        ...fixture,
        data: offset === 0 ? fixture.data : fixture.data.slice(0, 1),
        page: { offset, limit: 100, total: 101 },
      },
    });
  });
  await page.goto("/?eligibility=all&sort=start-asc&display=cards");
  const pagination = page.getByRole("navigation", { name: "Pagination des opportunités" });
  await expect(pagination).toContainText("Page 1 sur 2");
  await pagination.getByRole("button", { name: "Page suivante" }).click();
  await expect(pagination).toContainText("Page 2 sur 2");
  const secondPage = new URL(page.url());
  expect(secondPage.searchParams.get("offset")).toBe("100");
  expect(secondPage.searchParams.get("display")).toBe("cards");
  expect(secondPage.searchParams.get("eligibility")).toBe("all");
  expect(secondPage.searchParams.get("sort")).toBe("start-asc");
  await page.getByLabel("Équipe", { exact: true }).fill("Aurore");
  await page.getByRole("button", { name: "Appliquer", exact: true }).click();
  await expect(pagination).toContainText("Page 1 sur 2");
  const filtered = new URL(page.url());
  expect(filtered.searchParams.has("offset")).toBe(false);
  expect(filtered.searchParams.get("team")).toBe("Aurore");
  expect(
    reads.some((params) => params.get("offset") === "0" && params.get("team") === "Aurore"),
  ).toBe(true);
});

test("validates a paper amount, accepts Enter and refreshes history after creation", async ({
  page,
}) => {
  let created = false;
  let historyReads = 0;
  let metricReads = 0;
  let creationRequests = 0;
  const bet: PaperBet = {
    paperBetId: "ui-keyboard-paper",
    signalId: "f31e365e-ab44-53b2-b839-e1b9f2e3625b",
    predictionId: "ui-prediction",
    oddsSnapshotId: "ui-odds",
    closingOddsSnapshotId: null,
    placedAt: meta.computedAt,
    settledAt: null,
    currency: "EUR",
    stakeAmount: "12.50",
    entryOdds: "2.00",
    profitLoss: null,
    status: "open",
    settlementReason: null,
    settlementRulesVersion: "lol-match-winner-v1",
  };
  await page.route("**/api/backend/api/v1/paper-bets**", async (route) => {
    const request = route.request();
    if (request.url().includes("/metrics?")) {
      metricReads += 1;
      await route.fulfill({
        json: { data: { currency: "EUR", methodVersion: "test", reportId: null }, meta },
      });
    } else if (request.method() === "POST") {
      creationRequests += 1;
      expect(request.postDataJSON()).toMatchObject({ stakeAmount: "12.50" });
      created = true;
      await route.fulfill({ json: { data: bet, meta } });
    } else {
      historyReads += 1;
      await route.fulfill({ json: pageResponse(created ? [bet] : []) });
    }
  });
  await page.goto(`/paper-trading?signalId=${bet.signalId}`);
  const creation = page.getByRole("region", { name: "Créer une décision paper", exact: true });
  const amount = creation.getByLabel("Mise fictive (EUR)");
  await amount.fill("0");
  await expect(amount).toHaveAttribute("aria-invalid", "true");
  await expect(
    creation.getByRole("button", { name: "Créer le paper bet", exact: true }),
  ).toBeDisabled();
  await amount.press("Enter");
  expect(creationRequests).toBe(0);
  await expect.poll(() => historyReads).toBeGreaterThan(0);
  await expect.poll(() => metricReads).toBeGreaterThan(0);
  const initialHistoryReads = historyReads;
  const initialMetricReads = metricReads;
  await amount.fill("12.50");
  await amount.press("Enter");
  await expect(creation.getByRole("status").filter({ hasText: "Paper bet créé" })).toBeVisible();
  expect(creationRequests).toBe(1);
  await expect.poll(() => historyReads).toBeGreaterThan(initialHistoryReads);
  await expect.poll(() => metricReads).toBeGreaterThan(initialMetricReads);
  await expect(page.getByRole("region", { name: "Historique et P&L", exact: true })).toContainText(
    bet.paperBetId,
  );
  await expect(
    creation.getByRole("button", { name: "Paper bet créé", exact: true }),
  ).toBeDisabled();
});
