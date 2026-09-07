import { expect, test } from "@playwright/test";

// Contrats de transport synthétiques en mode réel ; le même parcours serveur
// est vérifié sur PostgreSQL dans test_real_paper_api.py.
const id = "aaaaaaaa-2222-4333-8444-555555555555";
const meta = {
  dataMode: "real",
  freshness: "fresh",
  asOf: "2026-09-07T12:00:00Z",
  computedAt: "2026-09-07T12:00:00Z",
  appVersion: "0.1.0",
};
const bet = {
  paperBetId: id,
  signalId: "f31e365e-ab44-53b2-b839-e1b9f2e3625b",
  predictionId: "bbbbbbbb-2222-4333-8444-555555555555",
  oddsSnapshotId: "cccccccc-2222-4333-8444-555555555555",
  closingOddsSnapshotId: "dddddddd-2222-4333-8444-555555555555",
  clv: "-0.2",
  clvIsProxy: true,
  entryOdds: "8",
  stakeAmount: "10",
  currency: "EUR",
  placedAt: "2026-09-07T09:00:00Z",
  status: "lost",
  settledAt: "2026-09-07T12:00:00Z",
  profitLoss: "-10",
  settlementReason: "OE_RESULT_LOST",
  settlementRulesVersion: "game-winner-v1",
};

test("real paper shows observed loss, samples, CLV and complete report link", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/backend/api/v1/paper-bets?**", (route) =>
    route.fulfill({ json: { data: [bet], meta, page: { offset: 0, limit: 100, total: 1 } } }),
  );
  await page.route("**/api/backend/api/v1/paper-bets/metrics?**", (route) =>
    route.fulfill({
      json: {
        data: {
          reportId: id,
          currency: "EUR",
          computedAt: meta.computedAt,
          methodVersion: "paper-finance-v1",
          reportFingerprint: "a".repeat(64),
          signals: 2,
          bets: 1,
          settled: 1,
          open: 0,
          pendingReview: 0,
          estimates: {
            profit_loss: { value: "-10", sampleSize: 1, unavailableReason: null },
            roi: { value: "-1", sampleSize: 1, unavailableReason: null },
            clv: { value: "-0.2", sampleSize: 1, unavailableReason: null },
            yield_ci_low: {
              value: null,
              sampleSize: 1,
              unavailableReason: "INSUFFICIENT_DAY_BLOCKS",
            },
          },
        },
        meta,
      },
    }),
  );
  await page.goto("/paper-trading");
  await expect(page.getByRole("region", { name: "P&L net", exact: true })).toContainText(
    /-10,00\s*€/,
  );
  await expect(page.getByRole("region", { name: "ROI / yield", exact: true })).toContainText(
    /-100\s*%/,
  );
  await expect(page.getByRole("region", { name: "ROI / yield", exact: true })).toContainText(
    "n = 1",
  );
  await expect(
    page.getByRole("region", { name: "CLV · proxy de prix", exact: true }),
  ).toContainText(/-20\s*%/);
  await expect(page.getByRole("region", { name: "Intervalle à 95 % · borne basse" })).toContainText(
    "Indisponible",
  );
  await expect(
    page.getByRole("link", { name: "Télécharger le rapport complet et son audit" }),
  ).toHaveAttribute("href", `/api/backend/api/v1/paper-reports/${id}`);
  await expect(page.getByRole("region", { name: `Paper bet ${id}` })).toContainText("Perdu");
  expect(errors).toEqual([]);
});

test("real settlement requests OE evidence without choosing status or P&L", async ({ page }) => {
  let current = {
    ...bet,
    status: "open",
    settledAt: null as string | null,
    profitLoss: null as string | null,
    settlementReason: null as string | null,
  };
  await page.route(`**/api/backend/api/v1/paper-bets/${id}`, (route) =>
    route.fulfill({ json: { data: current, meta } }),
  );
  await page.route("**/api/backend/api/v1/admin/paper-bets/settle", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    expect(body).not.toHaveProperty("status");
    expect(body).not.toHaveProperty("profitLoss");
    expect(body.actor).toBe("reviewer");
    current = { ...current, status: "pending_review", settlementReason: "RESULT_NOT_AVAILABLE" };
    await route.fulfill({ json: { data: current, meta } });
  });
  await page.goto(`/paper-trading/${id}`);
  const form = page.getByRole("region", { name: "Règlement depuis OE" });
  await expect(form.getByRole("combobox")).toHaveCount(0);
  await form.getByLabel("Auteur").fill("reviewer");
  await form.getByLabel("Motif de vérification").fill("Lire la dernière publication OE");
  await form.getByRole("button", { name: "Vérifier le règlement" }).click();
  await expect(form.getByRole("status")).toContainText("Revue requise");
  await expect(page.getByRole("region", { name: "Détail du paper bet" })).toContainText(
    "Revue requise",
  );
  await expect(page.getByRole("region", { name: "Détail du paper bet" })).toContainText(
    "Non réalisé",
  );
});
