import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const EVENT_ID = "1c6f28ad-4fdb-5a42-ac9e-90a863037d49";
const SIGNAL_ID = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";
const PAPER_BET_ID = "cef9c5cf-d14f-51dc-a417-91909b3088ba";

const keyPages = [
  "/",
  "/events",
  `/events/${EVENT_ID}`,
  `/opportunities/${SIGNAL_ID}`,
  "/models",
  "/data",
  "/admin",
  "/paper-trading",
  `/paper-trading/${PAPER_BET_ID}`,
] as const;

type BrowserMessage = Readonly<{ text: string; type: string }>;

function monitorBrowser(page: Page) {
  const messages: BrowserMessage[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      messages.push({ text: message.text(), type: message.type() });
    }
  });
  page.on("pageerror", (error) => {
    messages.push({ text: error.message, type: "pageerror" });
  });
  return messages;
}

test("has no WCAG A/AA axe violations or hydration errors on key pages", async ({ page }) => {
  test.setTimeout(120_000);
  const messages = monitorBrowser(page);

  for (const path of keyPages) {
    await test.step(path, async () => {
      messages.length = 0;
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const violations = results.violations.map((violation) => ({
        help: violation.help,
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.map((node) => ({
          failureSummary: node.failureSummary,
          target: node.target,
        })),
      }));
      expect(violations, `Violations axe sur ${path}`).toEqual([]);
      expect(messages, `Console ou hydratation sur ${path}`).toEqual([]);
    });
  }
});

test("keeps cumulative layout shift below 0.05 on key dashboards", async ({ page }) => {
  test.setTimeout(90_000);
  await page.addInitScript(() => {
    const metrics = window as Window & { __metiquoCls?: number };
    metrics.__metiquoCls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { hadRecentInput: boolean; value: number };
        if (!shift.hadRecentInput) metrics.__metiquoCls = (metrics.__metiquoCls ?? 0) + shift.value;
      }
    }).observe({ buffered: true, type: "layout-shift" });
  });

  for (const path of ["/", "/models", "/data", "/admin", "/paper-trading"] as const) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      const cls = await page.evaluate(
        () => (window as Window & { __metiquoCls?: number }).__metiquoCls ?? 0,
      );
      expect(cls, `CLS ${path}`).toBeLessThan(0.05);
    });
  }
});

test("supports keyboard mapping review and always exposes visible focus", async ({ page }) => {
  await page.goto("/admin");

  const radios = page.getByRole("radio");
  await radios.first().focus();
  await page.keyboard.press("ArrowDown");
  await expect(radios.nth(1)).toBeChecked();

  const reason = page.getByLabel("Motif obligatoire");
  await reason.focus();
  const focusStyle = await reason.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(focusStyle.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(2);
});

test("keeps critical mobile controls at least 44 CSS pixels tall", async ({ page }) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto(`/paper-trading?signalId=${SIGNAL_ID}`);

  const controls = [
    page.getByRole("button", { name: "Ouvrir la navigation" }),
    page.getByRole("button", { name: "Changer le thème" }),
    page.getByRole("spinbutton", { name: "Mise fictive (EUR)" }),
    page.getByRole("button", { name: "Créer le paper bet" }),
  ];
  for (const control of controls) {
    await expect(control).toBeVisible();
    const box = await control.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test("disables meaningful animation when reduced motion is requested", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  const timing = await page.getByRole("link", { name: "Événements" }).evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      animationDuration: style.animationDuration,
      transitionDuration: style.transitionDuration,
    };
  });
  expect(Number.parseFloat(timing.animationDuration)).toBeLessThanOrEqual(0.001);
  expect(Number.parseFloat(timing.transitionDuration)).toBeLessThanOrEqual(0.001);
});

test("captures stable desktop, tablet and mobile visual baselines", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const cases = [
    { name: "opportunities-desktop", path: "/", viewport: { height: 900, width: 1440 } },
    { name: "admin-tablet", path: "/admin", viewport: { height: 1024, width: 768 } },
    {
      name: "paper-mobile",
      path: `/paper-trading?signalId=${SIGNAL_ID}`,
      viewport: { height: 844, width: 390 },
    },
  ] as const;

  for (const current of cases) {
    await test.step(current.name, async () => {
      await page.setViewportSize(current.viewport);
      await page.goto(current.path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      await expect(page).toHaveScreenshot(`${current.name}.png`, {
        animations: "disabled",
        maxDiffPixelRatio: 0.03,
      });
      await attachViewportScreenshot(page, testInfo, current.name);
    });
  }
});

async function attachViewportScreenshot(page: Page, testInfo: TestInfo, name: string) {
  const screenshotPath = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ animations: "disabled", path: screenshotPath });
  await testInfo.attach(name, { contentType: "image/png", path: screenshotPath });
}
