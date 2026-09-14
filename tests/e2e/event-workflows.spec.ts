import { expect, test } from "@playwright/test";
import type {
  ItemResponseOpportunity,
  PageResponseOpportunity,
} from "../../packages/contracts/src/generated/types.gen.js";
import { chooseSelectOption } from "./helpers/select.js";

const signalId = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";

test("applies server event filters and restores them after browser back", async ({ page }) => {
  await page.goto("/events");
  await page.getByLabel("Équipe", { exact: true }).fill("Aurore 02");
  await chooseSelectOption(
    page,
    page.getByRole("combobox", { name: "Statut", exact: true }),
    "Planifié",
  );
  await page.getByRole("button", { name: "Appliquer", exact: true }).click();
  await expect(page).toHaveURL(/team=Aurore(?:\+|%20)02&status=scheduled/);
  const card = page.getByRole("region", { name: "Aurore 02 contre Bastion 02", exact: true });
  await expect(card).toBeVisible();
  await card.getByRole("link", { name: "Ouvrir la fiche", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Aurore 02");
  await page.goBack();
  await expect(page.getByLabel("Équipe", { exact: true })).toHaveValue("Aurore 02");
  await expect(page.getByRole("combobox", { name: "Statut", exact: true })).toHaveText("Planifié");
});

test("chooses an admissible event signal and lets the reader inspect other signals", async ({
  page,
}) => {
  const response = await page.request.get(`/api/backend/api/v1/opportunities/${signalId}`);
  expect(response.ok()).toBe(true);
  const payload = (await response.json()) as ItemResponseOpportunity;
  const selected = payload.data;
  const blocked = {
    ...selected,
    signalId: "99999999-9999-4999-8999-999999999999",
    quality: { ...selected.quality, publishable: false },
    value: { ...selected.value, conservativeExpectedValue: "0.99", grade: "BLOCKED" as const },
  };
  await page.route("**/api/backend/api/v1/opportunities?**", (route) =>
    route.fulfill({
      json: {
        data: [blocked, selected],
        meta: payload.meta,
        page: { offset: 0, limit: 100, total: 2 },
      } satisfies PageResponseOpportunity,
    }),
  );
  await page.goto(`/events/${selected.event.eventId}`);
  const chooser = page.getByRole("combobox", { name: "Signal analysé", exact: true });
  await expect(page.getByRole("link", { name: "Créer un paper bet", exact: true })).toHaveAttribute(
    "href",
    `/paper-trading?signalId=${signalId}`,
  );
  await chooser.click();
  await page.getByRole("option", { name: /Bloqué/ }).click();
  await expect(
    page.getByRole("button", { name: "Paper bet non admissible", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("link", { name: "Voir le signal", exact: true })).toHaveAttribute(
    "href",
    `/opportunities/${blocked.signalId}`,
  );
});

test("retains signal prices when the odds history fails and recovers it locally", async ({
  page,
}) => {
  let failHistory = true;
  await page.route("**/api/backend/api/v1/events/*/odds-history?**", async (route) => {
    if (failHistory)
      await route.fulfill({ status: 503, json: { detail: "Synthetic history failure" } });
    else await route.continue();
  });
  await page.goto(`/opportunities/${signalId}`);
  const prices = page.getByRole("region", { name: "Prix marché et prix modèle", exact: true });
  await expect(prices).toBeVisible();
  const history = page.getByRole("region", { name: "Historique des prix observés", exact: true });
  await expect(history).toContainText("L’historique des cotes n’a pas pu être chargé");
  failHistory = false;
  await history.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(history.getByRole("table")).toBeVisible();
  await expect(prices).toBeVisible();
});
