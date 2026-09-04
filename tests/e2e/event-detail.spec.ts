import { expect, test } from "@playwright/test";

test("opens a complete event sheet with an accessible odds summary", async ({ page }) => {
  await page.goto("/events");

  await expect(page.getByRole("heading", { level: 1, name: "Événements" })).toBeVisible();
  const eventCard = page.getByRole("region", { name: "Aurore 02 contre Bastion 02" });
  await expect(eventCard).toContainText("Best of 3");
  await eventCard.getByRole("link", { name: "Ouvrir la fiche" }).click();

  await expect(page).toHaveURL(/\/events\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Aurore 02 vs Bastion 02" }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: "Évolution de la cote observée" })).toBeVisible();
  await expect(page.locator("figcaption").getByText(/snapshot.*Cote de/i)).toBeVisible();
  await expect(page.getByRole("region", { name: "Prix et incertitude" })).toContainText(
    "Intervalle modèle",
  );
  await expect(page.getByRole("region", { name: "Marchés et capacité" })).toContainText(
    "non supportés",
  );
  await expect(page.getByRole("region", { name: "Participants et roster attendu" })).toContainText(
    "Rosters individuels non fournis",
  );
  await expect(page.getByRole("region", { name: "Provenance" })).toContainText(
    "Non utilisé — mode mock",
  );
  await expect(page.getByRole("link", { name: "Créer un paper bet" })).toBeVisible();
  await expect(page.getByText(/mise réelle/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /miser|pari réel/i })).toHaveCount(0);
});

test("keeps the event sheet readable on mobile", async ({ page }) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/events");

  await page
    .getByRole("region", { name: "Aurore 10 contre Bastion 10" })
    .getByRole("link", { name: "Ouvrir la fiche" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(page.getByRole("region", { name: "Timeline du signal" })).toBeVisible();
});
