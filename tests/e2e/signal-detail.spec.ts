import { expect, test } from "@playwright/test";

test("explains an admissible signal without causal or guaranteed language", async ({ page }) => {
  await page.goto("/");

  const opportunityRow = page.getByRole("row").filter({ hasText: "Aurore 02" });
  await opportunityRow.getByRole("link", { name: "Ouvrir le signal" }).click();

  await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Aurore 02 vs Bastion 02" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Prix marché et prix modèle" })).toContainText(
    "Prix du modèle indépendant",
  );
  await expect(page.getByRole("region", { name: "Facteurs structurés" })).toContainText(
    "ne sont pas présentés comme des causes",
  );
  await expect(page.getByRole("region", { name: "Risques et incertitude" })).toContainText(
    "Intervalle de probabilité",
  );
  await expect(page.getByRole("region", { name: "Qualité et fraîcheur" })).toContainText(
    "Publiable",
  );
  await expect(page.getByRole("region", { name: "Historique des prix observés" })).toContainText(
    "Probabilité sans marge",
  );
  await expect(page.getByRole("region", { name: "Règlement paper trading" })).toContainText(
    "lol-match-winner-v1",
  );
  await expect(page.getByRole("link", { name: "Créer un paper bet" })).toBeVisible();
  await expect(page.getByText(/garanti|\block\b|\bsûr\b/i)).toHaveCount(0);
});

test("shows abstention reasons and blocks paper trading for a stale signal", async ({ page }) => {
  await page.goto("/?eligibility=all&freshness=stale");

  await page
    .getByRole("row")
    .filter({ hasText: "Aurore 03" })
    .getByRole("link", { name: "Ouvrir le signal" })
    .click();

  await expect(
    page.getByRole("heading", { level: 2, name: "Signal ancien — décision bloquée" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Raisons d’abstention" })).toContainText(
    "ODDS_STALE",
  );
  await expect(page.getByRole("button", { name: "Paper bet bloqué" })).toBeDisabled();
});

test("keeps signal evidence readable on mobile", async ({ page }) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/");
  await page.getByRole("link", { name: "Vue cartes" }).click();
  await page
    .getByRole("region", { name: "Aurore 02 contre Bastion 02" })
    .getByRole("link", { name: "Ouvrir le signal" })
    .click();

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(
    page.getByRole("region", { name: "Historique des snapshots de cote" }),
  ).toBeVisible();
});
