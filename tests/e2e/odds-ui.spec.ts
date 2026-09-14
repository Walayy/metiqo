import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type {
  StakePublicEvent,
  ObservedOddsQuote,
} from "../../packages/contracts/src/generated/types.gen.js";

const capturedAt = "2026-09-08T16:45:00Z";
const finalMarketLabel = "Total des points — période réglementaire hors prolongation 136,5";
const finalMarketSearch = "periode reglementaire hors prolongation 136,5";
const meta = {
  dataMode: "real",
  freshness: "stale",
  computedAt: capturedAt,
  asOf: capturedAt,
  appVersion: "ui-audit",
};
const event: StakePublicEvent = {
  capture: {
    event: {
      providerEventId: "audit-822193",
      competition: "LEC 2026 Summer Playoffs",
      participants: ["GIANTX", "Natus Vincere"],
      gameTitle: "lol",
      startsAt: "2026-09-11T15:00:00Z",
      collectedAt: capturedAt,
      status: "scheduled",
      bestOf: null,
      sourceReference: "ui-audit-fixture",
    },
    sourceUrl: "https://stake.bet/fr/sports/league-of-legends",
    observedAt: capturedAt,
    expectedTabs: ["tab-main", "tab-map-1"],
    visitedTabs: ["tab-main", "tab-map-1"],
    warnings: [],
    markets: [
      {
        label: "Vainqueur du match",
        tab: "tab-main",
        capturedAt,
        expanded: true,
        rawText: "GIANTX 2,05",
        outcomes: [
          {
            label: "GIANTX",
            displayedLabel: "GIANTX",
            oddsText: "2,05",
            decimalOdds: "2.05",
            status: "open",
          },
          {
            label: "Natus Vincere",
            displayedLabel: "Natus Vincere",
            oddsText: "1,80",
            decimalOdds: "1.80",
            status: "open",
          },
        ],
      },
      {
        label: "Carte 1 — Vainqueur",
        tab: "tab-map-1",
        capturedAt,
        expanded: true,
        rawText: "Suspendu",
        outcomes: [
          {
            label: "GIANTX",
            displayedLabel: "GIANTX",
            oddsText: "",
            decimalOdds: null,
            status: "suspended",
          },
        ],
      },
      ...Array.from({ length: 28 }, (_, index): StakePublicEvent["capture"]["markets"][number] => ({
        label: index === 27 ? finalMarketLabel : `Handicap de points ${String(index + 1)},5`,
        tab: "tab-main",
        capturedAt,
        expanded: true,
        rawText: "GIANTX 3,25",
        outcomes: [
          {
            label: "GIANTX",
            displayedLabel: "GIANTX",
            oddsText: "3,25",
            decimalOdds: "3.25",
            status: "open",
          },
        ],
      })),
    ],
  },
  ageSeconds: 600,
  expiresAt: "2026-09-08T16:46:30Z",
  freshness: "stale",
};
const quote: ObservedOddsQuote = {
  oddsSnapshotId: "audit-observation",
  provider: "stake-observed",
  providerType: "manual_import",
  providerStatus: "operational",
  event: event.capture.event,
  marketLabel: "Vainqueur du match",
  period: "SERIES",
  marketStatus: "open",
  selectionLabel: "GIANTX",
  decimalOdds: "2.05",
  capturedAt,
  ageSeconds: 600,
  freshness: "stale",
  informationalOnly: true,
};

for (const width of [320, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`renders populated odds, source tabs and suspended markets at ${String(width)} in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => {
        localStorage.setItem("metiquo-theme", value);
      }, theme);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/api/backend/api/v1/odds/stake/status", (route) =>
        route.fulfill({
          json: {
            data: {
              enabled: true,
              state: "operational",
              checkedAt: capturedAt,
              lastSuccessAt: capturedAt,
              nextAttemptAt: "2026-09-08T16:55:00Z",
              detail: null,
              eventCount: 1,
            },
            meta,
          },
        }),
      );
      await page.route("**/api/backend/api/v1/odds/stake/events?**", (route) =>
        route.fulfill({ json: { data: [event], page: { offset: 0, limit: 5, total: 1 }, meta } }),
      );
      await page.route("**/api/backend/api/v1/odds/quotes?**", (route) =>
        route.fulfill({ json: { data: [quote], page: { offset: 0, limit: 20, total: 1 }, meta } }),
      );
      await page.goto("/odds");
      const stakeTab = page.getByRole("tab", { name: "Marchés Stake", exact: true });
      await expect(stakeTab).toHaveAttribute("aria-selected", "true");
      await expect(page.getByText("2,05", { exact: true })).toBeVisible();
      await expect(page.getByText("Cotes périmées", { exact: true })).toBeVisible();
      await expect(page.getByText(/Format non confirmé/)).toBeVisible();
      const audit = async (name: string) => {
        // Selection updates immediately, while the foreground/background transitions finish later.
        // Audit the settled source controls instead of sampling their intermediate colors.
        await page.getByRole("tablist", { name: "Source des cotes" }).evaluate(async (tablist) => {
          await Promise.all(
            tablist
              .getAnimations({ subtree: true })
              .map((animation) => animation.finished.catch(() => undefined)),
          );
        });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
          ),
        ).toBeLessThanOrEqual(1);
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        expect(result.violations).toEqual([]);
        await page.screenshot({
          fullPage: true,
          animations: "disabled",
          path: testInfo.outputPath(`${name}-${String(width)}-${theme}.png`),
        });
      };
      const stakePanel = page.getByRole("tabpanel", { name: "Marchés Stake", exact: true });
      await expect(stakePanel.locator("details")).toHaveCount(8);
      await expect(
        stakePanel.getByText("8 marchés affichés sur 29 · Match et série"),
      ).toBeVisible();
      await audit("stake-populated");
      const moreMarkets = stakePanel.getByRole("button", { name: "Afficher plus de marchés" });
      await moreMarkets.focus();
      await page.keyboard.press("Enter");
      await expect(stakePanel.locator("details")).toHaveCount(16);
      await expect(
        stakePanel.getByText("16 marchés affichés sur 29 · Match et série"),
      ).toBeVisible();
      await expect(moreMarkets).toBeFocused();
      const marketSearch = stakePanel.getByRole("searchbox", {
        name: "Rechercher un marché pour GIANTX contre Natus Vincere",
      });
      await marketSearch.focus();
      await marketSearch.pressSequentially(finalMarketSearch);
      await expect(marketSearch).toHaveValue(finalMarketSearch);
      await expect(stakePanel.locator("details")).toHaveCount(1);
      await expect(
        stakePanel.locator("summary").filter({ hasText: finalMarketLabel }),
      ).toBeVisible();
      await expect(marketSearch).toBeFocused();
      await audit("stake-search");
      await marketSearch.press("ControlOrMeta+A");
      await marketSearch.press("Backspace");
      await expect(marketSearch).toHaveValue("");
      await expect(stakePanel.locator("details")).toHaveCount(8);
      await page.getByRole("combobox").selectOption("tab-map-1");
      await expect(page.getByText("Suspendu", { exact: true })).toBeVisible();
      await expect(page.getByText("2,05", { exact: true })).toBeHidden();
      await stakeTab.focus();
      await page.keyboard.press("ArrowRight");
      const observedTab = page.getByRole("tab", { name: "Relevés de vainqueurs", exact: true });
      await expect(observedTab).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(observedTab).toHaveAttribute("aria-selected", "true");
      await expect(page.getByText("Cote enregistrée : 2,05", { exact: true })).toBeVisible();
      await expect(page.getByText("Information uniquement", { exact: true })).toBeVisible();
      await audit("observed-populated");
      expect(errors).toEqual([]);
    });
  }
}
