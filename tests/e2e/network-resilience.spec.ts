import { expect, test, type Page } from "@playwright/test";
import { financialReport, operations } from "./helpers/transport-fixtures.js";

const eventId = "1c6f28ad-4fdb-5a42-ac9e-90a863037d49";
const signalId = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";
const paperId = "cef9c5cf-d14f-51dc-a417-91909b3088ba";

for (const kind of ["operations", "finance"] as const) {
  test(`retains the synthetic real ${kind} evidence during a temporary service failure`, async ({
    page,
  }) => {
    let failing = false;
    const isOperations = kind === "operations";
    await page.clock.install();
    await page.route(
      isOperations
        ? "**/api/backend/api/v1/system/status"
        : "**/api/backend/api/v1/paper-bets/metrics?**",
      (route) =>
        route.fulfill({
          status: failing ? 503 : 200,
          json: failing
            ? { code: "DEPENDENCY_UNAVAILABLE" }
            : isOperations
              ? operations
              : financialReport,
        }),
    );
    await page.goto(isOperations ? "/admin" : "/paper-trading");
    const panel = page.getByRole("region", {
      name: isOperations ? "État opérationnel" : "Rapport financier",
      exact: true,
    });
    await expect(panel).toContainText(isOperations ? "SOURCE_TIMEOUT" : "-10,00");
    failing = true;
    await page.context().setOffline(true);
    await page.clock.fastForward(30_001);
    await page.context().setOffline(false);
    await page.clock.runFor(1_500);
    await expect(
      panel.getByRole("heading", { name: "Actualisation indisponible", exact: true }),
    ).toBeVisible();
    await expect(panel).toContainText(isOperations ? "SOURCE_TIMEOUT" : "-10,00");
    if (!isOperations) {
      await expect(panel.getByRole("region", { name: "ROI / yield", exact: true })).toContainText(
        /-100\s*%/,
      );
    }
    failing = false;
    await panel.getByRole("button", { name: "Réessayer", exact: true }).click();
    await expect(
      panel.getByRole("heading", { name: "Actualisation indisponible", exact: true }),
    ).toHaveCount(0);
    await expect(panel).toContainText(isOperations ? "SOURCE_TIMEOUT" : "-10,00");
  });
}

const cases = [
  { path: "/", content: (page: Page) => page.getByRole("row").filter({ hasText: "Aurore 02" }) },
  {
    path: "/events",
    content: (page: Page) => page.getByRole("region", { name: "Aurore 02 contre Bastion 02" }),
  },
  {
    path: `/events/${eventId}`,
    content: (page: Page) =>
      page.getByRole("heading", { level: 1, name: "Aurore 02 vs Bastion 02" }),
  },
  {
    path: `/opportunities/${signalId}`,
    content: (page: Page) =>
      page.getByRole("heading", { level: 1, name: "Aurore 02 vs Bastion 02" }),
  },
  {
    path: "/models",
    content: (page: Page) => page.getByRole("region", { name: "Champions", exact: true }),
  },
  {
    path: "/data",
    content: (page: Page) =>
      page
        .getByRole("region", { name: "Catalogue des sources", exact: true })
        .getByText("mock-provider", { exact: true })
        .first(),
  },
  {
    path: "/admin",
    content: (page: Page) =>
      page
        .getByRole("region", { name: "État opérationnel", exact: true })
        .getByText("Source historique", { exact: true }),
  },
  {
    path: "/paper-trading",
    content: (page: Page) =>
      page.getByRole("region", { name: `Paper bet ${paperId}`, exact: true }),
  },
  {
    path: `/paper-trading/${paperId}`,
    content: (page: Page) => page.getByRole("region", { name: "Détail du paper bet", exact: true }),
  },
];

for (const scenario of cases) {
  test(`preserves the last readable ${scenario.path} after a failed refresh and recovers`, async ({
    page,
  }) => {
    let failing = false;
    let failedReads = 0;
    await page.clock.install();
    await page.route("**/api/backend/api/v1/**", async (route) => {
      if (
        failing &&
        route.request().method() === "GET" &&
        !route.request().url().includes("/auth/")
      ) {
        failedReads += 1;
        await route.fulfill({
          status: 503,
          json: { code: "DEPENDENCY_UNAVAILABLE", detail: "Source momentanément indisponible" },
        });
      } else await route.continue();
    });
    await page.goto(scenario.path);
    const content = scenario.content(page);
    await expect(content).toBeVisible();
    await content.evaluate((element) => {
      element.setAttribute("data-network-identity", "original");
    });
    await page.waitForLoadState("networkidle");
    failing = true;
    await page.context().setOffline(true);
    await page.clock.fastForward(30_001);
    await page.context().setOffline(false);
    await expect.poll(() => failedReads).toBeGreaterThan(0);
    await page.clock.runFor(1_500);
    await expect(
      page.getByRole("heading", { name: "Actualisation indisponible", exact: true }).first(),
    ).toBeVisible();
    await expect(content).toBeVisible();
    await expect(content).toHaveAttribute("data-network-identity", "original");
    failing = false;
    const notices = page.getByRole("heading", { name: "Actualisation indisponible", exact: true });
    while (await notices.count()) {
      const before = await notices.count();
      await page.getByRole("button", { name: "Réessayer", exact: true }).first().click();
      await expect.poll(() => notices.count()).toBeLessThan(before);
    }
    await expect(
      page.getByRole("heading", { name: "Actualisation indisponible", exact: true }),
    ).toHaveCount(0);
    await expect(content).toBeVisible();
    await expect(content).toHaveAttribute("data-network-identity", "original");
  });
}

test("distinguishes a temporary paper read failure from a missing decision", async ({ page }) => {
  let status = 503;
  await page.route(`**/api/backend/api/v1/paper-bets/${paperId}`, (route) =>
    route.fulfill({ status, json: { detail: "Read unavailable" } }),
  );
  await page.goto(`/paper-trading/${paperId}`);
  await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Paper bet introuvable", exact: true }),
  ).toHaveCount(0);
  status = 404;
  await page.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Paper bet introuvable", exact: true }),
  ).toBeVisible();
});

test("bounds a transport that never answers and permits recovery", async ({ page }) => {
  test.setTimeout(45_000);
  let release!: () => void;
  const stalled = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/backend/api/v1/events?**", async (route) => {
    await stalled;
    await route.continue().catch(() => undefined);
  });
  try {
    await page.goto("/events");
    await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toBeEnabled({
      timeout: 35_000,
    });
    release();
    await page.getByRole("button", { name: "Réessayer", exact: true }).click();
    await expect(page.getByRole("region", { name: "Aurore 02 contre Bastion 02" })).toBeVisible();
  } finally {
    release();
  }
});

test("removes private cached content when the session is explicitly no longer authorized", async ({
  page,
}) => {
  let authenticated = true;
  const owner = { id: "aaaaaaaa-2222-4333-8444-555555555555", username: "owner" };
  await page.clock.install();
  await page.route("**/api/backend/api/v1/auth/session", (route) =>
    route.fulfill({
      json: { mode: "owner", authenticated, owner: authenticated ? owner : null },
    }),
  );
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: "Aurore 02" });
  await expect(row).toBeVisible();
  authenticated = false;
  await page.context().setOffline(true);
  await page.clock.fastForward(30_001);
  await page.context().setOffline(false);
  await expect(page.getByRole("heading", { name: "Connexion Owner", exact: true })).toBeVisible();
  await expect(row).toHaveCount(0);
  await page.route("**/api/backend/api/v1/opportunities?**", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  authenticated = true;
  await page.context().setOffline(true);
  await page.clock.fastForward(30_001);
  await page.context().setOffline(false);
  await expect(page.getByRole("button", { name: "Déconnexion", exact: true })).toBeVisible();
  await page.clock.runFor(1_500);
  await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toBeVisible();
  await expect(row).toHaveCount(0);
});

test("keeps an already loaded private-mode-disabled page visible while the network is offline", async ({
  page,
}) => {
  await page.goto("/");
  const row = page.getByRole("row").filter({ hasText: "Aurore 02" });
  await expect(row).toBeVisible();
  await page.context().setOffline(true);
  await expect(page.getByRole("status", { name: "Connexion réseau", exact: true })).toContainText(
    "Hors connexion",
  );
  await expect(row).toBeVisible();
  await page.context().setOffline(false);
  await expect(
    page.getByRole("status", { name: "Connexion réseau", exact: true }),
  ).not.toContainText("Hors connexion");
  await expect(row).toBeVisible();
});

test("ends an initial unavailable session check with an explicit retry", async ({ page }) => {
  await page.route("**/api/backend/api/v1/auth/session", (route) => route.abort("timedout"));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Connexion indisponible", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toBeEnabled();
  await expect(
    page.getByRole("heading", { name: "Vérification de la connexion", exact: true }),
  ).toHaveCount(0);
  await page.unroute("**/api/backend/api/v1/auth/session");
  await page.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: "Aurore 02" })).toBeVisible();
});
