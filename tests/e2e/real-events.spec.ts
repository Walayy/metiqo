import { expect, test } from "@playwright/test";

test("renders the real canonical event contract with the unchanged explorer", async ({ page }) => {
  await page.route("**/api/backend/api/v1/events**", async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        data: [
          {
            bestOf: 3,
            competition: "Ligue historique",
            eventId: "11111111-1111-4111-8111-111111111111",
            gameTitle: "league_of_legends",
            observedAt: "2026-09-05T12:00:00Z",
            startsAt: "2026-09-04T18:00:00Z",
            status: "finished",
            teamA: "Aurore réelle",
            teamAId: "22222222-2222-4222-8222-222222222222",
            teamB: "Bastion réel",
            teamBId: "33333333-3333-4333-8333-333333333333",
          },
        ],
        meta: {
          appVersion: "0.1.0",
          asOf: "2026-09-05T12:00:00Z",
          computedAt: "2026-09-05T12:00:00Z",
          dataMode: "real",
          freshness: "fresh",
        },
        page: { limit: 100, offset: 0, total: 1 },
      }),
      contentType: "application/json",
    });
  });

  await page.goto("/events");

  await expect(page.getByRole("heading", { level: 1, name: "Événements" })).toBeVisible();
  await expect(page.getByText("Données real")).toBeVisible();
  const event = page.getByRole("region", { name: "Aurore réelle contre Bastion réel" });
  await expect(event).toContainText("Ligue historique");
  await expect(event).toContainText("Best of 3");
  await expect(event).toContainText("Terminé");
  await expect(event.getByRole("link", { name: "Ouvrir la fiche" })).toHaveAttribute(
    "href",
    "/events/11111111-1111-4111-8111-111111111111",
  );
});
