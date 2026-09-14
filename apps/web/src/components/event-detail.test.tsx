import type { Event, OddsSnapshot } from "@metiquo/contracts/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { EventDetail, OddsChart } from "./event-detail";

const at = "2026-09-08T12:00:00Z";
const meta = { asOf: at, computedAt: at, dataMode: "mock", freshness: "fresh", appVersion: "test" };
const event: Event = {
  eventId: "event",
  bestOf: 3,
  competition: "Ligue test",
  gameTitle: "lol",
  observedAt: at,
  startsAt: "2026-09-09T12:00:00Z",
  status: "scheduled",
  teamA: "Équipe A",
  teamAId: "a",
  teamB: "Équipe B",
  teamBId: "b",
};

const clients: QueryClient[] = [];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <EventDetail eventId="event" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  clients.forEach((client) => {
    client.clear();
  });
  clients.length = 0;
  vi.unstubAllGlobals();
});

it("retains the event and retries only its unavailable odds history", async () => {
  let failOdds = true;
  const fetch = vi.fn((input: string) => {
    if (input.includes("odds-history") && failOdds)
      return Promise.resolve(new Response("{}", { status: 503 }));
    const data = input.endsWith("/events/event") ? event : [];
    return Promise.resolve(
      Response.json({ data, meta, page: { offset: 0, limit: 100, total: 0 } }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  mount();
  expect(await screen.findByRole("heading", { name: "Équipe A vs Équipe B" })).toBeVisible();
  const chart = screen.getByRole("region", { name: "Courbe des cotes" });
  expect(
    await within(chart).findByText("L’historique des cotes n’a pas pu être chargé."),
  ).toBeVisible();
  expect(screen.getByText("Aucun marché disponible pour cet événement.")).toBeVisible();
  failOdds = false;
  fireEvent.click(within(chart).getByRole("button", { name: "Réessayer" }));
  expect(await within(chart).findByText("Aucune cote observée pour cet événement.")).toBeVisible();
  expect(fetch.mock.calls.filter(([input]) => input.endsWith("/events/event"))).toHaveLength(1);
});

it("keeps the event visible when access to a secondary resource is denied", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve(
        input.includes("/markets?")
          ? new Response("{}", { status: 403 })
          : Response.json({
              data: input.endsWith("/events/event") ? event : [],
              meta,
              page: { offset: 0, limit: 100, total: 0 },
            }),
      ),
    ),
  );
  mount();
  expect(await screen.findByRole("heading", { name: "Équipe A vs Équipe B" })).toBeVisible();
  const markets = screen.getByRole("region", { name: "Marchés et capacité" });
  expect(await within(markets).findByRole("heading", { name: "Accès refusé" })).toBeVisible();
  expect(within(markets).queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
});

it("explains a successful response without an event instead of rendering an empty page", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve(
        Response.json({
          data: input.endsWith("/events/event") ? null : [],
          meta,
          page: { offset: 0, limit: 100, total: 0 },
        }),
      ),
    ),
  );
  mount();
  expect(await screen.findByRole("heading", { name: "Événement indisponible" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Retour aux événements" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeVisible();
});

it("places observations by elapsed time and labels the displayed date range", () => {
  const snapshots: OddsSnapshot[] = [0, 1, 10].map((minute, index) => ({
    ageSeconds: 0,
    capturedAt: `2026-09-08T12:${String(minute).padStart(2, "0")}:00Z`,
    decimalOdds: String(2 + index * 0.5),
    eventId: "event",
    marketId: "market",
    marketStatus: "open",
    noVigProbability: "0.5",
    oddsSnapshotId: String(index),
    provenanceReference: "fixture",
    provider: "mock",
    providerStatus: "operational",
    rawImpliedProbability: "0.5",
    selection: "TEAM_A",
  }));
  const { container, rerender } = render(<OddsChart snapshots={snapshots} />);
  const coordinates = container
    .querySelector("polyline")
    ?.getAttribute("points")
    ?.split(" ")
    .map((point) => Number(point.split(",")[0]));
  expect(coordinates).toEqual([3, 12.4, 97]);
  expect(screen.getByText(/Cote de 2,00 à 3,00/, { selector: "figcaption span" })).toBeVisible();
  expect(screen.getAllByText(/2026/)).toHaveLength(2);
  rerender(<OddsChart snapshots={snapshots.slice(0, 1)} />);
  expect(screen.getByText("Comparaison indisponible · une seule observation")).toBeVisible();
  expect(screen.queryByText("→ Stable")).not.toBeInTheDocument();
});
