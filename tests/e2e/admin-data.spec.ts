import { expect, test } from "@playwright/test";
import type { SystemStatusResponse } from "../../packages/contracts/src/generated/types.gen.js";

test("shows source degradation, snapshots, schema gaps and blocking anomalies", async ({
  page,
}) => {
  await page.goto("/data");

  await expect(page.getByRole("heading", { level: 1, name: "Santé des données" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Catalogue des sources" })).toContainText(
    "Erreur récupérable",
  );
  const snapshot = page.getByRole("region", { name: "Snapshot et couverture" });
  await expect(snapshot).toContainText("Dernière tentative");
  await expect(snapshot).toContainText("Dernier succès");
  await expect(snapshot).toContainText("Lignes validées");
  await expect(snapshot).toContainText("Hash actif");
  await expect(snapshot).toContainText("Plage de dates métier");
  await expect(snapshot).toContainText("Schéma");
  const capabilities = page.getByRole("region", { name: "Capacités par snapshot" });
  await expect(capabilities).toContainText("market.match_winner");
  await expect(capabilities).toContainText("pending");
  await expect(capabilities).toContainText("model: attente");
  await expect(capabilities).toContainText("odds: attente");
  await expect(page.getByRole("region", { name: "Anomalies bloquantes" })).toContainText(
    "EVENT_MAPPING_AMBIGUOUS",
  );
  await expect(page.getByRole("region", { name: "Quarantaine" })).toContainText("Aucun snapshot");
});

test("runs one controlled sync and exposes its audited result", async ({ page }) => {
  await page.goto("/admin");

  await expect(page.getByRole("heading", { level: 1, name: "Administration" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Jobs" })).toContainText("odds-sync");
  await page.getByRole("button", { name: "Lancer la synchronisation mock" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Synchronisation terminée" }),
  ).toContainText("12 lignes");
  await expect(page.getByRole("region", { name: "Journal d’audit" })).toContainText("mock.sync");
});

test("shows measured operations with readable data during a source failure", async ({
  page,
}, testInfo) => {
  const response: SystemStatusResponse = {
    status: "degraded",
    apiVersion: "0.1.0",
    dataMode: "real",
    generatedAt: "2026-09-08T03:00:00Z",
    dependencies: { database: { status: "available" } },
    operations: {
      readsAvailable: true,
      source: { status: "degraded", reasonCode: "SOURCE_TIMEOUT", asOf: "2026-09-08T02:00:00Z" },
      model: { status: "stale", trainingCutoff: "2026-07-08T02:00:00Z" },
      mappingBacklog: 3,
      jobCounts: { running: 1, queued: 2, failed: 1 },
      backups: { status: "not_configured" },
      metrics: {
        measuredJobCount: 2,
        meanJobDurationSeconds: 2.5,
        jobFailures: 1,
        processedRows: 12,
        anomalies: 4,
        blockingAnomalies: 2,
        signals: { VALUE: 1, BLOCKED: 2 },
        api: { requestCount: 8, failureCount: 1, meanLatencyMs: 3.4 },
      },
    },
  };
  let reads = 0;
  await page.route("**/api/backend/api/v1/system/status", async (route) => {
    reads += 1;
    await route.fulfill({ json: response });
  });
  await page.goto("/admin");
  const panel = page.getByRole("region", { name: "État opérationnel" });
  await expect(panel).toContainText("Snapshot validé disponible en lecture");
  await expect(panel).toContainText("SOURCE_TIMEOUT");
  await expect(panel).toContainText("2 anomalies bloquantes");
  await expect(panel).toContainText("Non configurées");
  await expect(panel).toContainText("2.50 s");
  await expect(panel).toContainText("8 requêtes");
  await page.waitForLoadState("networkidle");
  expect(reads).toBe(1);
  await panel.getByRole("button", { name: "Actualiser l’état" }).click();
  await expect.poll(() => reads).toBe(2);
  await panel.screenshot({ path: testInfo.outputPath("operational-status.png") });
});

test("distinguishes blocking catalogue errors from recoverable quality errors", async ({
  page,
}) => {
  await page.route("**/api/backend/api/v1/admin/data-sources**", async (route) => {
    await route.fulfill({ body: "{}", contentType: "application/json", status: 503 });
  });
  await page.route("**/api/backend/api/v1/admin/quality-issues**", async (route) => {
    await route.fulfill({ body: "{}", contentType: "application/json", status: 503 });
  });
  await page.goto("/data");

  await expect(page.getByRole("alert").filter({ hasText: "Catalogue indisponible" })).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "Actualisation impossible" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toBeVisible();
});
