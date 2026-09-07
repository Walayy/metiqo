import { expect, test } from "@playwright/test";

const modelVersionId = "11111111-2222-4333-8444-555555555555";
const metadata = {
  appVersion: "0.1.0",
  asOf: "2026-09-07T05:00:00Z",
  computedAt: "2026-09-07T05:00:00Z",
  dataMode: "real",
  freshness: "fresh",
};

function model(status: "candidate" | "champion" | "blocked") {
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

test("exposes a blocked registered version without offering promotion", async ({
  page,
}, testInfo) => {
  await page.route("**/api/backend/api/v1/models?**", async (route) => {
    await route.fulfill({ json: pageResponse([model("blocked")]) });
  });
  await page.route("**/api/backend/api/v1/backtests?**", async (route) => {
    await route.fulfill({ json: pageResponse([]) });
  });
  await page.goto("/models");
  const blocked = page.getByRole("region", { name: "Versions bloquées et retirées" });
  await expect(blocked).toContainText(modelVersionId);
  await expect(blocked).toContainText("blocked");
  await expect(blocked.getByRole("button", { name: "Promouvoir" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("blocked-model.png"), fullPage: true });
});

test("reuses the training request identity after losing its acknowledgement", async ({ page }) => {
  const keys: string[] = [];
  await page.route("**/api/backend/api/v1/admin/models/train", async (route) => {
    keys.push(route.request().headers()["idempotency-key"] ?? "");
    if (keys.length === 1) {
      await route.abort("connectionclosed");
    } else {
      await route.fulfill({ json: { data: model("candidate"), meta: metadata } });
    }
  });
  await page.goto("/models");
  const train = page.getByRole("button", { name: "Entraîner un candidat" });
  await train.click();
  await expect(
    page.getByRole("alert").filter({ hasText: "La réponse à la demande" }),
  ).toBeVisible();
  expect(keys).toHaveLength(1);
  await train.click();
  await expect(page.getByRole("status").filter({ hasText: "Action terminée" })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
});

for (const outcome of ["succeeded", "failed", "cancelled"] as const) {
  test(`observes queued training until ${outcome} without claiming a model was promoted`, async ({
    page,
  }, testInfo) => {
    const jobId = "61111111-2222-4333-8444-555555555555";
    let state: "queued" | "running" | typeof outcome = "queued";
    let posts = 0;
    let reads = 0;
    const job = () => ({
      dataMode: "real",
      jobId,
      name: "model.train",
      status: state,
      errorCode: state === "failed" ? "INVALID_STATE" : null,
      modelVersionId: state === "succeeded" ? modelVersionId : null,
    });
    await page.route("**/api/backend/api/v1/models?**", async (route) => {
      await route.fulfill({
        json: pageResponse(state === "succeeded" ? [model("candidate")] : []),
      });
    });
    await page.route("**/api/backend/api/v1/backtests?**", async (route) => {
      await route.fulfill({ json: pageResponse([]) });
    });
    await page.route("**/api/backend/api/v1/admin/models/train", async (route) => {
      posts += 1;
      await route.fulfill({ status: 202, json: { data: job(), meta: metadata } });
    });
    await page.route(`**/api/backend/api/v1/admin/jobs/${jobId}`, async (route) => {
      reads += 1;
      await route.fulfill({ json: { data: job(), meta: metadata } });
    });
    await page.goto("/models");
    const train = page.getByRole("button", { name: "Entraîner un candidat" });
    await train.click();
    const progress = page.getByRole("status", { name: "Entraînement" });
    await expect(progress).toContainText("En attente");
    await expect(train).toBeDisabled();
    state = "running";
    await expect(progress).toContainText("En cours");
    state = outcome;
    if (outcome === "succeeded") {
      await expect(progress).toContainText("Terminé");
      await expect(progress).toContainText(modelVersionId);
      await expect(
        page
          .getByRole("region", { name: "Challengers", exact: true })
          .filter({ has: page.getByRole("region", { name: "Modèle real-game-winner-v42" }) }),
      ).toContainText("real-game-winner-v42");
      await expect(
        page
          .getByRole("region", { name: "Champions actifs" })
          .getByRole("region", { name: /^Modèle / }),
      ).toHaveCount(0);
    } else {
      await expect(progress).toContainText(
        outcome === "failed" ? "Échec · INVALID_STATE" : "Annulé",
      );
    }
    await expect(train).toBeEnabled();
    expect(posts).toBe(1);
    expect(reads).toBeGreaterThanOrEqual(3);
    await page.screenshot({ path: testInfo.outputPath(`training-${outcome}.png`), fullPage: true });
  });
}

test("hides a training status after a permission refusal and restores it only after a successful read", async ({
  page,
}) => {
  const jobId = "71111111-2222-4333-8444-555555555555";
  const job = { dataMode: "real", jobId, name: "model.train", status: "queued" };
  let permission = 200;
  await page.route("**/api/backend/api/v1/admin/models/train", async (route) => {
    await route.fulfill({ status: 202, json: { data: job, meta: metadata } });
  });
  await page.route(`**/api/backend/api/v1/admin/jobs/${jobId}`, async (route) => {
    await route.fulfill({
      status: permission,
      json: permission === 200 ? { data: job, meta: metadata } : { detail: "Accès refusé" },
    });
  });
  await page.goto("/models");
  await page.getByRole("button", { name: "Entraîner un candidat" }).click();
  await expect(page.getByRole("status", { name: "Entraînement" })).toContainText("En attente");
  permission = 403;
  await expect(
    page.getByRole("alert").filter({ hasText: "Suivi de l’entraînement indisponible" }),
  ).toBeVisible();
  await expect(page.getByRole("status", { name: "Entraînement" })).toHaveCount(0);
  permission = 200;
  await page.getByRole("button", { name: "Réessayer le suivi" }).click();
  await expect(page.getByRole("status", { name: "Entraînement" })).toContainText("En attente");
});

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

  await expect(page.getByRole("status").filter({ hasText: "Action terminée" })).toContainText(
    "Action terminée · champion",
  );
  await expect(page.getByRole("region", { name: "Champions actifs" })).toContainText(
    "real-game-winner-v42",
  );
  await expect(
    page.getByRole("region", { name: "Challengers" }).filter({ hasText: "Aucun challenger" }),
  ).toContainText("Aucun challenger");
});
