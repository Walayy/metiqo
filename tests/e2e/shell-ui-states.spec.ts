import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type {
  ItemResponseEvent,
  PageResponseEvent,
} from "../../packages/contracts/src/generated/types.gen.js";

test("closes mobile navigation when resizing to desktop and keeps focus in visible content", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Ouvrir la navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 844 });
  await expect(page.getByRole("dialog", { name: "Navigation", exact: true })).toBeHidden();
  await expect(page.locator("main")).toBeFocused();
  await page.getByRole("link", { name: "Événements", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Événements", level: 1 })).toBeVisible();
});

test("places focus in the destination after choosing a mobile navigation link", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Ouvrir la navigation" }).click();
  await page
    .getByRole("dialog", { name: "Navigation", exact: true })
    .getByRole("link", { name: "Événements", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Événements", level: 1 })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Navigation", exact: true })).toBeHidden();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Boolean(document.querySelector("main")?.contains(document.activeElement)),
      ),
    )
    .toBe(true);
});

for (const width of [390, 1440]) {
  test(`preserves content geometry when opening overlays at ${width.toString()}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Opportunités" })).toBeVisible();
    const main = page.locator("main");
    const before = await main.boundingBox();
    if (!before) throw new Error("Main content missing");
    if (width < 768) await page.getByRole("button", { name: /^Filtres \(/ }).click();
    const grade = page.getByRole("combobox", { name: "Grade", exact: true });
    await grade.click();
    await expect(page.getByRole("listbox")).toBeVisible();
    expect((await main.boundingBox())?.width).toBe(before.width);
    await page.keyboard.press("Escape");
    await expect(grade).toBeFocused();
    await page.getByRole("button", { name: "Changer le thème" }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    expect((await main.boundingBox())?.width).toBe(before.width);
    await page.keyboard.press("Escape");
    if (width < 1024) {
      await page.getByRole("button", { name: "Ouvrir la navigation" }).click();
      await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
      expect((await main.boundingBox())?.width).toBe(before.width);
    }
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`explains login and logout failures with accessible ${theme} feedback`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript((value) => {
      localStorage.setItem("metiquo-theme", value);
    }, theme);
    let authenticated = false;
    let logoutFails = true;
    const authStatus = () => ({
      mode: "owner",
      authenticated,
      owner: authenticated ? { username: "owner", ownerId: "fixture-owner" } : null,
    });
    await page.route("**/api/backend/api/v1/auth/session", (route) =>
      route.fulfill({ json: authStatus() }),
    );
    await page.route("**/api/backend/api/v1/auth/login", async (route) => {
      const body = route.request().postDataJSON() as { password: string };
      authenticated = body.password === "fixture-accepted";
      await route.fulfill({ status: authenticated ? 200 : 401, json: authStatus() });
    });
    await page.route("**/api/backend/api/v1/auth/logout", async (route) => {
      if (logoutFails) {
        logoutFails = false;
        await route.fulfill({ status: 503, json: { detail: "Fixture" } });
      } else {
        authenticated = false;
        await route.fulfill({ json: authStatus() });
      }
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Connexion Owner" })).toBeVisible();
    await page.getByLabel("Identifiant", { exact: true }).fill("owner");
    const password = page.getByLabel("Mot de passe", { exact: true });
    await password.fill("fixture-rejected");
    await password.press("Enter");
    await expect(
      page.getByRole("alert").filter({ hasText: "Identifiants incorrects" }),
    ).toBeVisible();
    await expect(password).toBeFocused();
    await expect(password).toHaveAttribute("aria-invalid", "true");
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(result.violations).toEqual([]);
    await page.screenshot({
      fullPage: true,
      path: testInfo.outputPath(`login-error-${theme}.png`),
    });
    await password.fill("fixture-accepted");
    await password.press("Enter");
    const logout = page.getByRole("button", { name: "Déconnexion", exact: true });
    await expect(logout).toBeVisible();
    await logout.click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Déconnexion impossible" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Opportunités", level: 1 })).toBeVisible();
    await logout.click();
    await expect(page.getByRole("heading", { name: "Connexion Owner", level: 1 })).toBeVisible();
  });
}

test("contains very long labels and identifiers in a populated mobile explorer", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const longTeam = "Équipe".repeat(40);
  await page.route("**/api/backend/api/v1/events?**", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as PageResponseEvent;
    const data = body.data.map((event, index) =>
      index === 0
        ? {
            ...event,
            teamA: longTeam,
            teamB: "B",
            competition:
              "Compétition internationale avec une désignation exceptionnellement longue ".repeat(
                3,
              ),
          }
        : event,
    );
    await route.fulfill({ json: { ...body, data } });
  });
  await page.goto("/events");
  await expect(page.getByRole("heading", { name: `${longTeam} vs B`, exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({ fullPage: true, path: testInfo.outputPath("long-labels-mobile.png") });
});

test("keeps navigation available after an unexpected rendering failure", async ({
  page,
}, testInfo) => {
  let fail = true;
  await page.route(
    "**/api/backend/api/v1/events/1c6f28ad-4fdb-5a42-ac9e-90a863037d49",
    async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as ItemResponseEvent;
      await route.fulfill({
        json: fail ? { ...body, data: { ...body.data, bestOf: null } } : body,
      });
    },
  );
  await page.goto("/events/1c6f28ad-4fdb-5a42-ac9e-90a863037d49");
  await expect(
    page.getByRole("heading", { name: "Impossible d’afficher cette page", level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toBeVisible();
  await page.screenshot({ fullPage: true, path: testInfo.outputPath("unexpected-error.png") });
  await expect(page.getByRole("link", { name: "Revenir aux opportunités" })).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Aurore 02 vs Bastion 02", level: 1 }),
  ).toBeVisible();
});
