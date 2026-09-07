import { expect, test } from "@playwright/test";

test("enforces CSP without blocking navigation, theme or admin mutations", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") violations.push(message.text());
  });
  page.on("pageerror", (error) => violations.push(error.message));
  const response = await page.goto("/");
  const policy = response?.headers()["content-security-policy"] ?? "";
  expect(policy).toContain("'strict-dynamic'");
  expect(policy).not.toContain("'unsafe-eval'");
  const scriptDirective = policy.split(";").find((value) => value.includes("script-src")) ?? "";
  expect(scriptDirective).not.toContain("'unsafe-inline'");
  const nonce = /'nonce-([^']+)'/.exec(scriptDirective)?.[1];
  expect(nonce?.length).toBeGreaterThanOrEqual(43);
  expect(response?.headers()["x-frame-options"]).toBe("DENY");
  await expect(
    page.getByRole("heading", { level: 1, name: "Opportunités", exact: true }),
  ).toBeVisible();
  const scriptNonces = await page
    .locator("script:not([src])")
    .evaluateAll((scripts) => scripts.map((element) => (element as HTMLScriptElement).nonce));
  expect(scriptNonces.length).toBeGreaterThan(0);
  expect(scriptNonces.every((value) => value === nonce)).toBe(true);
  await page.getByRole("button", { name: "Changer le thème" }).click();
  await page.getByRole("menuitem", { name: "Sombre" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "Administration", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Administration", exact: true }),
  ).toBeVisible();
  const second = await page.request.get("/", { headers: { "x-nonce": "attacker-value" } });
  expect(second.headers()["content-security-policy"]).not.toContain(nonce ?? "missing");
  expect(second.headers()["content-security-policy"]).not.toContain("attacker-value");
  const origin = new URL(page.url()).origin;
  const forged = await page.request.post("/api/backend/api/v1/admin/oracles-elixir/sync", {
    headers: {
      Origin: "https://attacker.test",
      "X-Metiquo-CSRF": "1",
      "Idempotency-Key": "forged",
    },
  });
  expect(forged.status()).toBe(403);
  const missing = await page.request.post("/api/backend/api/v1/admin/oracles-elixir/sync", {
    headers: { Origin: origin, "Idempotency-Key": "missing-csrf" },
  });
  expect(missing.status()).toBe(403);
  const allowed = await page.request.post("/api/backend/api/v1/admin/oracles-elixir/sync", {
    headers: { Origin: origin, "X-Metiquo-CSRF": "1", "Idempotency-Key": "allowed-csrf" },
  });
  expect(allowed.status()).toBe(200);
  const oversized = await page.request.post("/api/backend/api/v1/auth/login", {
    headers: { Origin: origin, "X-Metiquo-CSRF": "1" },
    data: "x".repeat(65537),
  });
  expect(oversized.status()).toBe(413);
  expect(violations).toEqual([]);
});
