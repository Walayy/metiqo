import { expect, test } from "@playwright/test";

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
