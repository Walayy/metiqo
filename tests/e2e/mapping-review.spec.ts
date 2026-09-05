import { expect, test } from "@playwright/test";

test("keeps an ambiguous raw event blocked and previews each candidate", async ({ page }) => {
  await page.goto("/admin");

  const queue = page.getByRole("region", { name: "File de mapping" });
  await expect(queue).toContainText("1 ambiguïté en attente");
  await expect(queue.getByRole("alert")).toContainText("Publication bloquée");
  await expect(queue).toContainText("mock-event-ambiguous_mapping");
  await expect(queue).toContainText("Participants proches");
  await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText(
    "Aurore 05 — Bastion 05",
  );
  await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText(
    "aucun signal historique ne sera réécrit",
  );

  await queue.getByRole("radio", { name: /Aurore 05 Academy/ }).check();
  await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText(
    "Aurore 05 Academy",
  );
});

test("creates a dated alias and records an explicit approval", async ({ page }) => {
  const mutations: { path: string; payload: Record<string, unknown> }[] = [];
  await page.route("**/api/backend/api/v1/admin/**", async (route) => {
    const request = route.request();
    if (request.method() !== "POST") {
      await route.continue();
      return;
    }
    const idempotencyKey = request.url().includes("/admin/aliases")
      ? "e2e-mapping-alias-v1"
      : "e2e-mapping-approval-v1";
    mutations.push({
      path: new URL(request.url()).pathname,
      payload: request.postDataJSON() as Record<string, unknown>,
    });
    await route.continue({
      headers: { ...request.headers(), "idempotency-key": idempotencyKey },
    });
  });
  await page.goto("/admin");

  const queue = page.getByRole("region", { name: "File de mapping" });
  await queue.getByLabel("Alias brut").fill("Aurore 05 historique");
  await queue.getByRole("button", { name: "Créer l’alias daté" }).click();
  await expect(queue.getByRole("status").filter({ hasText: "Alias créé et daté" })).toContainText(
    "Aurore 05 historique",
  );

  await queue.getByLabel("Motif obligatoire").fill("Participants et horaire confirmés");
  await queue.getByRole("button", { name: "Approuver le candidat" }).click();
  await expect(queue.getByRole("status").filter({ hasText: "Décision approved" })).toContainText(
    "admin-local",
  );
  const audit = page.getByRole("region", { name: "Journal d’audit" });
  await expect(audit).toContainText("alias.create");
  await expect(audit).toContainText("mapping.approved");
  expect(mutations).toHaveLength(2);
  expect(mutations[0]?.payload).toMatchObject({
    alias: "Aurore 05 historique",
    entityType: "team",
    reviewer: "admin-local",
  });
  expect(mutations[1]?.payload).toMatchObject({
    reason: "Participants et horaire confirmés",
    reviewer: "admin-local",
  });
  expect(mutations[1]?.payload.candidateEventId).toBeTruthy();
  expect(mutations[0]?.payload.canonicalId).not.toBe(mutations[1]?.payload.candidateEventId);
});
