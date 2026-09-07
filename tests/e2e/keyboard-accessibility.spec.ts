import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { PageResponseOddsSnapshot } from "../../packages/contracts/src/generated/types.gen.js";
import { activate, tabTo, typeAt } from "./helpers/keyboard.js";

const signalId = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";
const eventId = "1c6f28ad-4fdb-5a42-ac9e-90a863037d49";
const paths = [
  "/",
  "/events",
  `/events/${eventId}`,
  `/opportunities/${signalId}`,
  "/models",
  "/data",
  "/admin",
  "/paper-trading",
  "/paper-trading/cef9c5cf-d14f-51dc-a417-91909b3088ba",
];

for (const size of ["desktop", "mobile"] as const) {
  test(`completes the ${size} signal and paper workflow entirely by keyboard`, async ({ page }) => {
    test.setTimeout(60_000);
    if (size === "mobile") await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await activate(page, page.getByRole("link", { name: "Aller au contenu" }));
    const team = page.getByLabel("Équipe", { exact: true });
    await typeAt(page, team, "Aurore 02");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/team=Aurore/);
    await expect(team).toBeFocused();
    await expect(page.getByRole("status", { name: "Résultats des filtres" })).toContainText(
      "1 résultat",
    );
    await activate(page, page.getByRole("link", { name: "Ouvrir le signal" }));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Aurore 02 vs Bastion 02");
    await activate(page, page.getByRole("link", { name: "Créer un paper bet" }));
    const creation = page.getByRole("region", { name: "Créer une décision paper", exact: true });
    await typeAt(page, creation.getByRole("spinbutton", { name: "Mise fictive (EUR)" }), "5");
    await activate(page, creation.getByRole("button", { name: "Créer le paper bet" }));
    await expect(creation.getByRole("status").filter({ hasText: "Paper bet créé" })).toBeVisible();
    const settlement = creation.getByRole("region", { name: "Règlement fictif", exact: true });
    await tabTo(page, settlement.getByRole("combobox", { name: "Statut", exact: true }));
    await page.keyboard.press("Home");
    await page.keyboard.press("ArrowDown");
    await expect(settlement.getByRole("combobox", { name: "Statut", exact: true })).toHaveValue(
      "lost",
    );
    await typeAt(page, settlement.getByLabel("P&L fictif"), "-5");
    await typeAt(
      page,
      settlement.getByLabel("Motif", { exact: true }),
      "Exercice clavier mock QA-003",
    );
    await activate(
      page,
      settlement.getByRole("button", { name: "Enregistrer le règlement fictif" }),
    );
    await expect(creation.getByRole("status").filter({ hasText: "Règlement lost" })).toContainText(
      /-5,00\s*€/,
    );
  });

  test(`reviews mapping and starts a model through ${size} keyboard controls`, async ({ page }) => {
    test.setTimeout(60_000);
    if (size === "mobile") await page.setViewportSize({ width: 390, height: 844 });
    // The mock catalogue has one immutable pending-review fixture. Replay its
    // canonical approval (also used by mapping-review.spec) across viewport runs.
    await page.route("**/api/backend/api/v1/admin/mappings/*/approve", async (route) => {
      await route.continue({
        headers: { ...route.request().headers(), "idempotency-key": "e2e-mapping-approval-v1" },
      });
    });
    await page.goto("/admin");
    await activate(page, page.getByRole("link", { name: "Aller au contenu" }));
    await activate(page, page.getByRole("button", { name: "Lancer la synchronisation mock" }));
    await expect(
      page.getByRole("status").filter({ hasText: "Synchronisation terminée" }),
    ).toBeVisible();
    const queue = page.getByRole("region", { name: "File de mapping" });
    await tabTo(page, queue.getByRole("radio").first());
    await page.keyboard.press("ArrowDown");
    await expect(queue.getByRole("radio").nth(1)).toBeChecked();
    await expect(queue.getByRole("region", { name: "Aperçu d’impact" })).toContainText("Academy");
    await typeAt(page, queue.getByLabel("Alias brut"), `Alias clavier QA003 ${size}`);
    await activate(page, queue.getByRole("button", { name: "Créer l’alias daté" }));
    await expect(queue.getByRole("status").filter({ hasText: "Alias créé et daté" })).toBeVisible();
    await tabTo(page, queue.getByRole("radio").nth(1));
    await page.keyboard.press("ArrowUp");
    await typeAt(page, queue.getByLabel("Motif obligatoire"), "Participants et horaire confirmés");
    await activate(page, queue.getByRole("button", { name: "Approuver le candidat" }));
    await expect(queue.getByRole("status").filter({ hasText: "Décision approved" })).toBeVisible();
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/models");
    await activate(page, page.getByRole("link", { name: "Aller au contenu" }));
    await activate(page, page.getByRole("button", { name: "Entraîner un candidat" }));
    await expect(page.getByRole("status").filter({ hasText: "Action terminée" })).toBeVisible();
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect
      .soft(
        result.violations.map(({ id, nodes }) => ({
          id,
          nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })),
        })),
      )
      .toEqual([]);
    await page.route("**/api/backend/api/v1/admin/models/train", (route) =>
      route.fulfill({
        status: 503,
        json: { detail: "Entraînement indisponible dans ce scénario de test" },
      }),
    );
    await activate(page, page.getByRole("button", { name: "Entraîner un candidat" }));
    await expect(
      page.getByRole("alert").filter({ hasText: "Entraînement indisponible" }),
    ).toBeVisible();
    const failedAction = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(failedAction.violations).toEqual([]);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`has accessible semantics and AA contrast on every ${size} ${theme} critical page`, async ({
      page,
    }, testInfo) => {
      test.setTimeout(150_000);
      if (size === "mobile") await page.setViewportSize({ width: 390, height: 844 });
      await page.addInitScript((value) => {
        localStorage.setItem("metiquo-theme", value);
      }, theme);
      for (const path of paths) {
        await test.step(path, async () => {
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          const result = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
            .analyze();
          await testInfo.attach(`axe-${path.replaceAll("/", "_")}`, {
            contentType: "application/json",
            body: JSON.stringify(result.violations),
          });
          expect
            .soft(
              result.violations.map(({ id, nodes }) => ({
                id,
                nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })),
              })),
              path,
            )
            .toEqual([]);
        });
      }
    });
  }
}

test("keeps the mobile navigation focus contained and restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const open = page.getByRole("button", { name: "Ouvrir la navigation" });
  await activate(page, open);
  const dialog = page.getByRole("dialog", { name: "Navigation" });
  await expect(dialog.getByRole("button", { name: "Fermer la navigation" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("link", { name: "Paramètres" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(open).toBeFocused();
  await activate(page, open);
  await activate(page, dialog.getByRole("link", { name: "Événements" }));
  await expect(page).toHaveURL(/\/events$/);
  await expect(dialog).toBeHidden();
  await activate(
    page,
    page
      .getByRole("region", { name: "Aurore 02 contre Bastion 02" })
      .getByRole("link", { name: "Ouvrir la fiche" }),
  );
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Aurore 02 vs Bastion 02");
  await expect(page.locator("figcaption")).toContainText(/snapshot.*Cote de/i);
  await activate(page, page.getByRole("link", { name: "Voir le signal" }));
  await expect(page).toHaveURL(new RegExp(`/opportunities/${signalId}$`));
});

test("changes appearance with menu keys and returns focus to its trigger", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Changer le thème" });
  await activate(page, trigger);
  await page.keyboard.press("Home");
  await expect(page.getByRole("menuitem", { name: "Système" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Clair" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Sombre" })).toBeFocused();
  expect(
    await page
      .getByRole("menuitem", { name: "Sombre" })
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).outlineWidth)),
  ).toBeGreaterThanOrEqual(2);
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(trigger).toBeFocused();
});

test("restores filter fields when clearing and revisiting a shared URL", async ({ page }) => {
  await page.goto("/?team=Aurore+02&grade=STRONG_VALUE");
  await expect(page.getByLabel("Équipe", { exact: true })).toHaveValue("Aurore 02");
  await activate(page, page.getByRole("link", { name: "Effacer", exact: true }));
  await expect(page.getByLabel("Équipe", { exact: true })).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "Grade", exact: true })).toHaveValue("");
  await page.goBack();
  await expect(page.getByLabel("Équipe", { exact: true })).toHaveValue("Aurore 02");
  await expect(page.getByRole("combobox", { name: "Grade", exact: true })).toHaveValue(
    "STRONG_VALUE",
  );
});

test("announces new odds politely while preserving the original signal price", async ({ page }) => {
  await page.clock.install();
  let reads = 0;
  await page.route(
    "**/api/backend/api/v1/events/eb4277aa-673e-5874-aa76-d1e292bd9d11/odds-history?**",
    async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as PageResponseOddsSnapshot;
      reads += 1;
      if (reads > 1) {
        const latest = body.data.toSorted((a, b) => b.capturedAt.localeCompare(a.capturedAt))[0];
        if (!latest) throw new Error("Fixture de cote absente");
        body.data.push({
          ...latest,
          oddsSnapshotId: "ab012345-0123-4123-8123-0123456789ab",
          decimalOdds: "3.50",
          capturedAt: new Date(Date.parse(latest.capturedAt) + 60_000).toISOString(),
        });
      }
      await route.fulfill({ response, json: body });
    },
  );
  await page.goto("/");
  const odds = page.getByRole("status", { name: "Cote observée pour Aurore 10 contre Bastion 10" });
  await expect(odds).toHaveAttribute("aria-live", "polite");
  await expect(odds).toHaveAttribute("aria-atomic", "true");
  await expect(odds).toContainText("3,60");
  await page.clock.fastForward(30_001);
  await expect(odds).toContainText("3,50");
  await expect(odds).toContainText("4,20");
});
