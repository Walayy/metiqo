import { expect, test } from "@playwright/test";

test("keeps an ambiguous raw event blocked and previews each candidate", async ({ page }) => {
  await page.goto("/admin");

  const queue = page.getByRole("region", { name: "File de mapping" });
  await expect(queue).toContainText("1 ambiguïté en attente");
  await expect(queue.getByRole("alert")).toContainText("Publication bloquée");
  await expect(queue).toContainText("mock-event-ambiguous_mapping");
  await expect(queue).toContainText("Participants proches");
  await expect(queue).toContainText("pondération individuelle");
  await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText(
    "Aurore 05 — Bastion 05",
  );

  await queue.getByRole("radio", { name: /Aurore 05 Academy/ }).check();
  await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText(
    "Aurore 05 Academy",
  );
});

test("creates a dated alias and records an explicit approval", async ({ page }) => {
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
});
