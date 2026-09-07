import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { financialReport, operations } from "./helpers/transport-fixtures.js";

const keyPages = [
  "/",
  "/events",
  "/events/1c6f28ad-4fdb-5a42-ac9e-90a863037d49",
  "/opportunities/f31e365e-ab44-53b2-b839-e1b9f2e3625b",
  "/models",
  "/data",
  "/admin",
  "/paper-trading",
  "/paper-trading/cef9c5cf-d14f-51dc-a417-91909b3088ba",
] as const;

const viewports = {
  desktop: { width: 1440, height: 960 },
  mobile: { width: 390, height: 844 },
} as const;

// Panel captures exclude fixed shell chrome; CLS uses the unmodified page.
const panelCaptureStyle =
  'header.sticky, a[href="#main-content"] { visibility: hidden !important; }';

interface VisualMetrics {
  shifts: { value: number; sources: string[] }[];
  paintedThemes: (string | null)[];
}

async function observe(page: Page) {
  const messages: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) messages.push(message.text());
  });
  page.on("pageerror", (error) => messages.push(error.message));
  await page.addInitScript(() => {
    const metrics: VisualMetrics = { shifts: [], paintedThemes: [] };
    (window as Window & { __visualMetrics?: VisualMetrics }).__visualMetrics = metrics;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & {
          hadRecentInput: boolean;
          value: number;
          sources: { node?: Node | null }[];
        };
        if (!shift.hadRecentInput) {
          metrics.shifts.push({
            value: shift.value,
            sources: shift.sources.map(({ node }) =>
              (node instanceof Element ? node.outerHTML : (node?.textContent ?? "")).slice(0, 250),
            ),
          });
        }
      }
    }).observe({ type: "layout-shift", buffered: true });
    function sampleTheme() {
      if (document.querySelector("main"))
        metrics.paintedThemes.push(document.documentElement.getAttribute("data-theme"));
      requestAnimationFrame(sampleTheme);
    }
    requestAnimationFrame(sampleTheme);
  });
  return messages;
}

async function assertStable(page: Page, testInfo: TestInfo, messages: string[]) {
  await page.waitForLoadState("networkidle");
  const metrics = await page.evaluate(
    () => (window as Window & { __visualMetrics?: VisualMetrics }).__visualMetrics,
  );
  expect(metrics).toBeDefined();
  await testInfo.attach("layout-metrics", {
    contentType: "application/json",
    body: JSON.stringify(metrics, null, 2),
  });
  const cls = metrics?.shifts.reduce((sum, shift) => sum + shift.value, 0) ?? 1;
  expect.soft(cls, JSON.stringify(metrics?.shifts)).toBeLessThan(0.05);
  expect.soft(messages).toEqual([]);
  expect
    .soft(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
}

for (const [size, viewport] of Object.entries(viewports)) {
  for (const path of keyPages) {
    test(`slow response keeps ${size} ${path} stable`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      const messages = await observe(page);
      await page.route("**/api/backend/**", async (route) => {
        const response = await route.fetch();
        await new Promise((resolve) => setTimeout(resolve, 750));
        await route.fulfill({ response });
      });
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await assertStable(page, testInfo, messages);
    });
  }

  for (const kind of ["operations", "finance"] as const) {
    test(`reserves ${size} ${kind} dimensions until the real response arrives`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(viewport);
      const messages = await observe(page);
      let release!: () => void;
      const gate = new Promise<void>((resolve) => (release = resolve));
      const isOperations = kind === "operations";
      await page.route(
        isOperations
          ? "**/api/backend/api/v1/system/status"
          : "**/api/backend/api/v1/paper-bets/metrics?**",
        async (route) => {
          await gate;
          await route.fulfill({ json: isOperations ? operations : financialReport });
        },
      );
      await page.goto(isOperations ? "/admin" : "/paper-trading");
      const panel = page.getByRole("region", {
        name: isOperations ? "État opérationnel" : "Rapport financier",
        exact: true,
      });
      await expect(panel).toBeVisible();
      await panel.scrollIntoViewIfNeeded();
      // Two painted frames ensure the loading layout is actually measured.
      await page.evaluate(
        () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
      );
      const before = await panel.boundingBox();
      await panel.screenshot({
        path: testInfo.outputPath(`${kind}-${size}-loading.png`),
        style: panelCaptureStyle,
      });
      release();
      await expect(panel).toContainText(isOperations ? "SOURCE_TIMEOUT" : "-10,00");
      const after = await panel.boundingBox();
      await testInfo.attach("panel-dimensions", {
        contentType: "application/json",
        body: JSON.stringify({ before, after }, null, 2),
      });
      expect.soft(Math.abs((after?.height ?? 0) - (before?.height ?? 0))).toBeLessThanOrEqual(4);
      await assertStable(page, testInfo, messages);
      await panel.screenshot({
        path: testInfo.outputPath(`${kind}-${size}-ready.png`),
        style: panelCaptureStyle,
      });
      await expect(panel).toHaveScreenshot(`${kind}-${size}.png`, {
        animations: "disabled",
        maxDiffPixelRatio: 0.01,
        stylePath: "tests/e2e/panel-capture.css",
      });
    });
  }

  test(`keeps the ${size} odds graph mounted and sized during a slow refresh`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.clock.install();
    const messages = await observe(page);
    let requests = 0;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    await page.route("**/api/backend/api/v1/events/*/odds-history?**", async (route) => {
      const response = await route.fetch();
      requests += 1;
      if (requests > 1) await gate;
      await route.fulfill({ response });
    });
    await page.goto("/events/1c6f28ad-4fdb-5a42-ac9e-90a863037d49");
    const chart = page.getByRole("img", { name: "Évolution de la cote observée" });
    await expect(chart).toBeVisible();
    const original = await chart.elementHandle();
    const before = await chart.boundingBox();
    await page.context().setOffline(true);
    await expect(page.getByRole("status", { name: "Connexion réseau", exact: true })).toContainText(
      "Hors connexion",
    );
    await page.screenshot({ path: testInfo.outputPath(`network-${size}-offline.png`) });
    await page.clock.fastForward(30_001);
    await page.context().setOffline(false);
    await expect.poll(() => requests).toBe(2);
    await expect(chart).toBeVisible();
    expect(await original.evaluate((element) => element.isConnected)).toBe(true);
    expect(await chart.boundingBox()).toEqual(before);
    release();
    await expect(page.locator('[data-refetching="true"]')).toHaveCount(0);
    expect(await chart.boundingBox()).toEqual(before);
    await assertStable(page, testInfo, messages);
  });
}

test("cancels loading animation immediately when reduced motion changes", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/backend/api/v1/paper-bets/metrics?**", async (route) => {
    await gate;
    await route.fulfill({ json: financialReport });
  });
  await page.goto("/paper-trading");
  const skeletons = page
    .getByRole("region", { name: "Rapport financier" })
    .locator("[data-remote-skeleton]");
  await expect(skeletons).toHaveCount(32);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await skeletons.evaluateAll((nodes) =>
      nodes.every((node) => getComputedStyle(node, "::after").animationName === "none"),
    ),
  ).toBe(true);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  expect(
    await skeletons.evaluateAll((nodes) =>
      nodes.every(
        (node) => getComputedStyle(node, "::after").animationName === "metiquo-skeleton-shimmer",
      ),
    ),
  ).toBe(true);
  release();
  await expect(skeletons).toHaveCount(0);
});

for (const theme of ["dark", "light"] as const) {
  test(`paints only the stored ${theme} theme despite an opposite system preference`, async ({
    page,
  }, testInfo) => {
    const messages = await observe(page);
    await page.emulateMedia({ colorScheme: theme === "dark" ? "light" : "dark" });
    await page.addInitScript((stored) => {
      localStorage.setItem("metiquo-theme", stored);
    }, theme);
    await page.goto("/");
    await assertStable(page, testInfo, messages);
    const themes = await page.evaluate(
      () => (window as Window & { __visualMetrics?: VisualMetrics }).__visualMetrics?.paintedThemes,
    );
    expect(new Set(themes)).toEqual(new Set([theme]));
  });
}
