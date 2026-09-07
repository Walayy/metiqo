import { expect, test } from "@playwright/test";
import { activate, typeAt } from "./helpers/keyboard.js";

for (const size of ["desktop", "mobile"] as const) {
  test(`authenticates the Owner by ${size} keyboard through the proxy and invalidates logout`, async ({
    page,
    context,
  }, testInfo) => {
    test.skip(process.env.E2E_AUTH_MODE !== "owner", "Exercice Owner avec PostgreSQL requis");
    if (size === "mobile") await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Connexion Owner" })).toBeVisible();
    expect((await page.request.get("/api/backend/api/v1/opportunities")).status()).toBe(401);
    await typeAt(page, page.getByLabel("Identifiant", { exact: true }), "owner");
    await typeAt(page, page.getByLabel("Mot de passe", { exact: true }), "wrong-fixture-password");
    await activate(page, page.getByRole("button", { name: "Se connecter", exact: true }));
    await expect(
      page.getByRole("alert").filter({ hasText: "Identifiants incorrects" }),
    ).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("owner-login.png"), fullPage: true });
    await typeAt(
      page,
      page.getByLabel("Mot de passe", { exact: true }),
      "fixture-only-owner-passphrase",
    );
    await activate(page, page.getByRole("button", { name: "Se connecter", exact: true }));
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
    await activate(page, page.getByRole("button", { name: "Déconnexion", exact: true }));
    await expect(page.getByRole("heading", { level: 1, name: "Connexion Owner" })).toBeVisible();
    expect((await page.request.get("/api/backend/api/v1/opportunities")).status()).toBe(401);
  });
}
