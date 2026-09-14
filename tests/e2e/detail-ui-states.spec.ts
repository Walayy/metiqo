import { expect, test, type Page } from "@playwright/test";
import type {
  ContractMetadata,
  Event,
  MappingReview,
  Market,
  OddsSnapshot,
} from "../../packages/contracts/src/generated/types.gen.js";

const eventId = "1c6f28ad-4fdb-5a42-ac9e-90a863037d49";
const signalId = "f31e365e-ab44-53b2-b839-e1b9f2e3625b";
const meta: ContractMetadata = {
  appVersion: "0.1.0",
  asOf: "2026-09-08T12:00:00Z",
  computedAt: "2026-09-08T12:00:00Z",
  dataMode: "mock",
  freshness: "fresh",
};
const eventFixture: Event = {
  eventId,
  bestOf: 3,
  competition: "Compétition de test",
  gameTitle: "lol",
  observedAt: meta.asOf,
  startsAt: "2026-09-09T12:00:00Z",
  status: "scheduled",
  teamA: "Équipe A",
  teamAId: "aaaaaaaa-1111-4111-8111-111111111111",
  teamB: "Équipe B",
  teamBId: "bbbbbbbb-1111-4111-8111-111111111111",
};

function pageResponse(data: readonly unknown[]) {
  return { data, meta, page: { limit: 100, offset: 0, total: data.length } };
}

async function emptyEventResources(page: Page) {
  await page.route(`**/api/backend/api/v1/events/${eventId}/markets?**`, (route) =>
    route.fulfill({ json: pageResponse([]) }),
  );
  await page.route(`**/api/backend/api/v1/events/${eventId}/odds-history?**`, (route) =>
    route.fulfill({ json: pageResponse([]) }),
  );
  await page.route("**/api/backend/api/v1/opportunities?**", (route) =>
    route.fulfill({ json: pageResponse([]) }),
  );
}

for (const resource of [
  {
    collection: "events",
    id: eventId,
    missing: "Événement introuvable",
    back: "Retour aux événements",
  },
  {
    collection: "opportunities",
    id: signalId,
    missing: "Signal introuvable",
    back: "Retour aux opportunités",
  },
]) {
  for (const status of [404, 403]) {
    test(`explains ${status.toString()} on ${resource.collection} and retains a way back`, async ({
      page,
    }) => {
      await emptyEventResources(page);
      await page.route(`**/api/backend/api/v1/opportunities/${signalId}/explanation`, (route) =>
        route.fulfill({
          json: { data: { signalId, reference: "fixture", reasons: [], publishable: false }, meta },
        }),
      );
      await page.route(`**/api/backend/api/v1/${resource.collection}/${resource.id}`, (route) =>
        route.fulfill({ status, json: { detail: "Synthetic unavailable resource" } }),
      );

      await page.goto(`/${resource.collection}/${resource.id}`);
      await expect(
        page.getByRole("heading", {
          name: status === 403 ? "Accès refusé" : resource.missing,
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.getByRole("link", { name: resource.back, exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Réessayer", exact: true })).toHaveCount(0);
    });
  }
}

test("describes missing event markets, odds and provenance without empty panels", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await emptyEventResources(page);
  await page.route(`**/api/backend/api/v1/events/${eventId}`, (route) =>
    route.fulfill({ json: { data: eventFixture, meta } }),
  );
  await page.goto(`/events/${eventId}`);

  await expect(
    page.getByRole("heading", { name: "Équipe A vs Équipe B", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Marchés et capacité", exact: true }),
  ).toContainText("Aucun marché disponible");
  await expect(page.getByRole("region", { name: "Courbe des cotes", exact: true })).toContainText(
    "Aucune cote observée",
  );
  await expect(page.getByRole("region", { name: "Provenance", exact: true })).toContainText(
    "Aucune provenance de signal disponible",
  );
  await expect(
    page.getByRole("button", { name: "Paper bet non admissible", exact: true }),
  ).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

function review(reference: string, withCandidates = true): MappingReview {
  return {
    mappingReviewId: `review-${reference}`,
    provider: "fixture-provider",
    providerEventId: reference,
    rawCompetition: "Ligue de test",
    rawParticipants: [`${reference} A`, `${reference} B`],
    createdAt: meta.asOf,
    status: "pending",
    affectedSnapshotCount: 2,
    candidates: withCandidates
      ? [0, 1].map((index) => ({
          eventId: `${reference}-candidate-${index.toString()}`,
          confidence: "0.80",
          label: `${reference} candidat ${index.toString()}`,
          reasons: ["Participants et date à vérifier"],
          teamAId: `${reference}-team-a`,
          teamBId: `${reference}-team-b`,
        }))
      : [],
  };
}

test("explains a mapping without candidates and preserves a justified rejection", async ({
  page,
}) => {
  await page.route("**/api/backend/api/v1/admin/mappings/pending?**", (route) =>
    route.fulfill({ json: pageResponse([review("empty", false)]) }),
  );
  await page.goto("/admin");
  const card = page.getByRole("region", { name: "Mapping empty", exact: true });
  await expect(card).toContainText("Aucun candidat disponible");
  await expect(card.getByRole("radio")).toHaveCount(0);
  await expect(
    card.getByRole("button", { name: "Approuver le candidat", exact: true }),
  ).toBeDisabled();
  await expect(
    card.getByRole("button", { name: "Créer l’alias daté", exact: true }),
  ).toBeDisabled();
  await expect(
    card.getByRole("button", { name: "Rejeter le mapping", exact: true }),
  ).toBeDisabled();
  await card
    .getByLabel("Motif obligatoire")
    .fill("Aucun rapprochement canonique possible.\nÀ examiner après la prochaine collecte.");
  await expect(card.getByRole("button", { name: "Rejeter le mapping", exact: true })).toBeEnabled();
});

test("keeps candidate radio selections independent between simultaneous mapping reviews", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/backend/api/v1/admin/mappings/pending?**", (route) =>
    route.fulfill({ json: pageResponse([review("first"), review("second")]) }),
  );
  await page.goto("/admin");
  const first = page.getByRole("region", { name: "Mapping first", exact: true });
  const second = page.getByRole("region", { name: "Mapping second", exact: true });
  await expect(first.getByRole("radio").nth(0)).not.toBeChecked();
  await expect(first.getByRole("radio").nth(1)).not.toBeChecked();
  await expect(second.getByRole("radio").nth(0)).not.toBeChecked();
  await expect(second.getByRole("radio").nth(1)).not.toBeChecked();
  await first.getByRole("radio").nth(0).check();
  await second.getByRole("radio").nth(0).check();
  await expect(first.getByRole("radio").nth(0)).toBeChecked();
  await expect(second.getByRole("radio").nth(0)).toBeChecked();
  await first.getByRole("radio").nth(0).focus();
  await page.keyboard.press("ArrowDown");
  await expect(first.getByRole("radio").nth(1)).toBeChecked();
  await expect(second.getByRole("radio").nth(0)).toBeChecked();
  await second.getByRole("radio").nth(1).check();
  await expect(first.getByRole("radio").nth(1)).toBeChecked();
  await expect(second.getByRole("radio").nth(1)).toBeChecked();
  await expect(first.getByRole("radio").nth(0)).not.toBeChecked();
  await expect(second.getByRole("radio").nth(0)).not.toBeChecked();
  await expect(first.getByRole("region", { name: "Aperçu d’impact", exact: true })).toContainText(
    "first candidat 1",
  );
  await expect(second.getByRole("region", { name: "Aperçu d’impact", exact: true })).toContainText(
    "second candidat 1",
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test("appends event markets and odds while preserving the chart after a failed next page", async ({
  page,
}) => {
  const markets: Market[] = ["A", "B"].map((team) => ({
    eventId,
    marketId: `market-${team}`,
    period: "SERIES",
    selection: team === "A" ? "TEAM_A" : "TEAM_B",
    selectionLabel: `Équipe ${team}`,
    status: "open",
    type: "MATCH_WINNER",
  }));
  const odds: OddsSnapshot[] = ["2.00", "2.50"].map((decimalOdds, index) => ({
    ageSeconds: 0,
    capturedAt: `2026-09-08T12:0${String(index)}:00Z`,
    decimalOdds,
    eventId,
    marketId: "market-A",
    marketStatus: "open",
    noVigProbability: "0.5",
    oddsSnapshotId: `snapshot-${String(index)}`,
    provenanceReference: "fixture",
    provider: "mock-provider",
    providerStatus: "operational",
    rawImpliedProbability: "0.5",
    selection: "TEAM_A",
  }));
  let failNextOdds = true;
  await emptyEventResources(page);
  await page.route(`**/api/backend/api/v1/events/${eventId}`, (route) =>
    route.fulfill({ json: { data: eventFixture, meta } }),
  );
  for (const [resource, values] of [
    ["markets", markets],
    ["odds-history", odds],
  ] as const) {
    await page.route(`**/api/backend/api/v1/events/${eventId}/${resource}?**`, (route) => {
      const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
      return route.fulfill(
        resource === "odds-history" && offset === 1 && failNextOdds
          ? { status: 503, json: { detail: "Synthetic next-page failure" } }
          : {
              json: {
                data: values.slice(offset, offset + 1),
                meta,
                page: { offset, total: 2, limit: 100 },
              },
            },
      );
    });
  }
  await page.goto(`/events/${eventId}`);
  const chart = page.getByRole("region", { name: "Courbe des cotes", exact: true });
  await expect(chart.locator("figcaption")).toContainText("1 snapshot");
  await chart.locator("figure").evaluate((element) => {
    element.setAttribute("data-chart-identity", "original");
  });
  await page.getByRole("button", { name: "Afficher plus de marchés", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Marchés et capacité", exact: true }),
  ).toContainText("Équipe B");
  await chart.getByRole("button", { name: "Afficher plus d’observations", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Suite des résultats indisponible", exact: true }),
  ).toBeVisible();
  await expect(chart.locator("figure")).toHaveAttribute("data-chart-identity", "original");
  failNextOdds = false;
  await page.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(chart.locator("figcaption")).toContainText("2 snapshots");
  await expect(chart.locator("figcaption")).toContainText("2,50");
  await expect(
    chart.getByRole("button", { name: "Afficher plus d’observations", exact: true }),
  ).toHaveCount(0);
});

test("loads remaining mappings without skipping the next review after a resolved decision", async ({
  page,
}) => {
  let resolved = false;
  let reads = 0;
  const first = review("resolved-first");
  await page.route("**/api/backend/api/v1/admin/mappings/pending?**", (route) => {
    reads += 1;
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    expect(offset).toBe(0);
    return route.fulfill({
      json: {
        data: [resolved ? review("remaining-second") : first],
        meta,
        page: { offset, total: resolved ? 1 : 2, limit: 100 },
      },
    });
  });
  await page.route(
    "**/api/backend/api/v1/admin/mappings/review-resolved-first/approve",
    (route) => {
      resolved = true;
      return route.fulfill({
        json: {
          data: {
            ...first,
            status: "approved",
            reviewer: "admin-local",
            decisionReason: "Correspondance confirmée",
            reviewedAt: meta.asOf,
          },
          meta,
        },
      });
    },
  );
  await page.goto("/admin");
  const queue = page.getByRole("region", { name: "File de mapping", exact: true });
  await queue.getByRole("radio").first().check();
  await queue.getByLabel("Motif obligatoire").fill("Correspondance confirmée");
  await queue.getByRole("button", { name: "Approuver le candidat", exact: true }).click();
  await expect(queue.getByRole("status").filter({ hasText: "Décision approved" })).toBeVisible();
  await queue.getByRole("button", { name: "Afficher plus de mappings", exact: true }).click();
  await expect(
    queue.getByRole("region", { name: "Mapping remaining-second", exact: true }),
  ).toBeVisible();
  expect(reads).toBe(2);
});
