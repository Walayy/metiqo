import { expect, test } from "@playwright/test";

const ADMISSIBLE_SIGNAL = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";
const VOID_PAPER_BET = "cef9c5cf-d14f-51dc-a417-91909b3088ba";

test("creates and settles a paper bet from an admissible signal", async ({ page }) => {
  await page.goto(`/paper-trading?signalId=${ADMISSIBLE_SIGNAL}`);

  await expect(page.getByRole("heading", { level: 1, name: "Paper trading" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("aucun argent réel");
  const creation = page.getByRole("region", { name: "Créer une décision paper" });
  await expect(creation).toContainText(ADMISSIBLE_SIGNAL);
  await creation.getByRole("button", { name: "Créer le paper bet" }).click();
  await expect(creation.getByRole("status").filter({ hasText: "Paper bet créé" })).toContainText(
    "aucune exécution réelle",
  );

  const settlement = creation.getByRole("region", { name: "Règlement fictif" });
  await settlement.getByLabel("Statut").selectOption("lost");
  await settlement.getByLabel("P&L fictif").fill("-10");
  await settlement.getByLabel("Motif").fill("Défaite confirmée dans le scénario mock");
  await settlement.getByRole("button", { name: "Enregistrer le règlement fictif" }).click();
  await expect(creation.getByRole("status").filter({ hasText: "Règlement lost" })).toContainText(
    /-10,00\s*€/,
  );
});

test("shows a versioned paper-bet detail without any real execution", async ({ page }) => {
  await page.goto(`/paper-trading/${VOID_PAPER_BET}`);

  await expect(page.getByRole("heading", { level: 1, name: "Paper bet" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Aucune exécution réelle");
  const detail = page.getByRole("region", { name: "Détail du paper bet" });
  await expect(detail).toContainText("Annulé / void");
  await expect(detail).toContainText("lol-match-winner-v1");
  await expect(detail.getByRole("link", { name: "Ouvrir le signal source" })).toBeVisible();
});

test("renders losses as prominently as gains in the P&L summary", async ({ page }) => {
  await page.route("**/api/backend/api/v1/paper-bets?**", async (route) => {
    const base = {
      closingOddsSnapshotId: null,
      currency: "EUR",
      entryOdds: "2.00",
      oddsSnapshotId: "00000000-0000-4000-8000-000000000001",
      placedAt: "2026-09-04T10:00:00Z",
      predictionId: "00000000-0000-4000-8000-000000000002",
      settlementReason: "Scénario de test",
      settlementRulesVersion: "lol-match-winner-v1",
      settledAt: "2026-09-04T12:00:00Z",
      signalId: ADMISSIBLE_SIGNAL,
      stakeAmount: "10.00",
    };
    await route.fulfill({
      contentType: "application/json",
      json: {
        data: [
          { ...base, paperBetId: "win", profitLoss: "14.00", status: "won" },
          { ...base, paperBetId: "loss", profitLoss: "-10.00", status: "lost" },
        ],
        meta: {
          appVersion: "test",
          asOf: "2026-09-04T12:00:00Z",
          computedAt: "2026-09-04T12:00:00Z",
          dataMode: "mock",
          freshness: "fresh",
        },
        page: { limit: 100, offset: 0, total: 2 },
      },
    });
  });
  await page.goto("/paper-trading");

  await expect(page.getByRole("region", { name: "Gains paper" })).toContainText("+14,00 €");
  await expect(page.getByRole("region", { name: "Pertes paper" })).toContainText(/-10,00\s*€/);
  await expect(page.getByRole("region", { name: "Paper bet loss" })).toContainText(/-10,00\s*€/);
});
