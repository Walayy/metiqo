import { expect, test } from "@playwright/test";

test("authenticates the Owner through the browser proxy and invalidates logout", async ({
  page,
  context,
}, testInfo) => {
  test.skip(process.env.E2E_AUTH_MODE !== "owner", "Exercice Owner avec PostgreSQL requis");
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Connexion Owner" })).toBeVisible();
  expect((await page.request.get("/api/backend/api/v1/opportunities")).status()).toBe(401);
  await page.getByLabel("Identifiant", { exact: true }).fill("owner");
  await page.getByLabel("Mot de passe", { exact: true }).fill("wrong-fixture-password");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Identifiants incorrects" }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("owner-login.png"), fullPage: true });
  await page.getByLabel("Mot de passe", { exact: true }).fill("fixture-only-owner-passphrase");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await expect(page.getByRole("button", { name: "Déconnexion", exact: true })).toBeVisible();
  const forgedLogout = await page.request.post("/api/backend/api/v1/auth/logout", {
    headers: { Origin: "https://attacker.test", "X-Metiquo-CSRF": "1" },
  });
  expect(forgedLogout.status()).toBe(403);
  await expect(
    page.getByRole("heading", { level: 1, name: "Opportunités", exact: true }),
  ).toBeVisible();
  const cookie = (await context.cookies()).find((entry) => entry.name === "metiquo_owner");
  expect(cookie?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("metiquo_owner");
  expect((await page.request.get("/api/backend/api/v1/opportunities")).status()).toBe(200);
  await page.getByRole("button", { name: "Déconnexion", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Connexion Owner" })).toBeVisible();
  expect((await page.request.get("/api/backend/api/v1/opportunities")).status()).toBe(401);
});
