import { expect, test } from "@playwright/test";

const modelVersionId = "11111111-2222-4333-8444-555555555555";
const metadata = {
  appVersion: "0.1.0",
  asOf: "2026-09-07T05:00:00Z",
  computedAt: "2026-09-07T05:00:00Z",
  dataMode: "real",
  freshness: "fresh",
};

function model(status: "candidate" | "champion") {
  return {
    algorithm: "hist_gradient_boosting",
    artifactHash: "b".repeat(64),
    baselineMetrics: { brier: "0.21", calibration_ece: "0.08", log_loss: "0.49" },
    codeCommit: "abcdef1",
    createdAt: "2026-09-07T04:00:00Z",
    datasetHash: "a".repeat(64),
    featureVersion: "lol-full-feature-set-v1",
    gameTitle: "lol",
    marketType: "MATCH_WINNER",
    metrics: { brier: "0.18", calibration_ece: "0.05", log_loss: "0.43" },
    modelVersion: "real-game-winner-v42",
    modelVersionId,
    promotedAt: status === "champion" ? "2026-09-07T05:00:00Z" : null,
    promotionReason:
      status === "champion" ? "Promotion manuelle depuis le tableau des modèles" : null,
    status,
    trainCutoff: "2026-09-01T00:00:00Z",
  };
}

function pageResponse(data: readonly unknown[]) {
  return {
    data,
    meta: metadata,
    page: { limit: 100, offset: 0, total: data.length },
  };
}

test("promotes a real candidate and keeps the exact prediction version visible", async ({
  page,
}) => {
  let status: "candidate" | "champion" = "candidate";

  await page.route("**/api/backend/api/v1/models?**", async (route) => {
    await route.fulfill({
      body: JSON.stringify(pageResponse([model(status)])),
      contentType: "application/json",
    });
  });
  await page.route("**/api/backend/api/v1/backtests?**", async (route) => {
    await route.fulfill({
      body: JSON.stringify(
        pageResponse([
          {
            backtestId: "99999999-8888-4777-8666-555555555555",
            baselineMetrics: { brier: "0.21", calibration_ece: "0.08", log_loss: "0.49" },
            completedAt: "2026-09-07T04:00:00Z",
            endsAt: "2026-09-01T00:00:00Z",
            finalTestUntouched: true,
            kind: "statistical",
            metrics: { brier: "0.18", calibration_ece: "0.05", log_loss: "0.43" },
            modelVersionId,
            observedOddsCount: 0,
            sampleCount: 1280,
            startsAt: "2026-01-01T00:00:00Z",
            usesOnlyObservedOdds: false,
            validationScheme: "walk_forward",
          },
        ]),
      ),
      contentType: "application/json",
    });
  });
  await page.route(
    `**/api/backend/api/v1/admin/models/${modelVersionId}/promote`,
    async (route) => {
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      expect(route.request().postDataJSON()).toEqual({
        reason: "Promotion manuelle depuis le tableau des modèles",
      });
      status = "champion";
      await route.fulfill({
        body: JSON.stringify({ data: model(status), meta: metadata }),
        contentType: "application/json",
      });
    },
  );

  await page.goto("/models");

  const candidate = page.getByRole("region", { name: "Modèle real-game-winner-v42" });
  await expect(candidate).toContainText(modelVersionId);
  await expect(candidate).toContainText("0,43");
  await expect(
    page.getByRole("region", { name: "Performance temporelle des backtests" }),
  ).toContainText("1280");
  await candidate.getByRole("button", { name: "Promouvoir" }).click();

  await expect(page.getByRole("status")).toContainText("Action terminée · champion");
  await expect(page.getByRole("region", { name: "Champions actifs" })).toContainText(
    "real-game-winner-v42",
  );
  await expect(
    page.getByRole("region", { name: "Challengers" }).filter({ hasText: "Aucun challenger" }),
  ).toContainText("Aucun challenger");
});
