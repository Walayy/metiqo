import type { StakePublicEvent } from "@metiquo/contracts/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { StakeOddsDashboard } from "./stake-odds-dashboard";

const at = "2026-09-08T16:45:00Z";
const event: StakePublicEvent = {
  capture: {
    event: {
      providerEventId: "822193",
      competition: "LEC 2026 Summer Playoffs",
      participants: ["GIANTX", "Natus Vincere"],
      gameTitle: "lol",
      startsAt: "2026-09-11T15:00:00Z",
      collectedAt: at,
      status: "scheduled",
      bestOf: null,
      sourceReference: "stake-dom-fr-v1",
    },
    sourceUrl:
      "https://stake.bet/fr/sports/league-of-legends/international-1/lec-2026-summer-playoffs-t3/822193-giantx-natus-vincere",
    observedAt: at,
    expectedTabs: ["tab-main", "tab-map-1"],
    visitedTabs: ["tab-main", "tab-map-1"],
    warnings: [],
    markets: [
      {
        label: "Vainqueur du match - Two options",
        tab: "tab-main",
        capturedAt: at,
        expanded: true,
        rawText: "GIANTX 2,05",
        outcomes: [
          {
            label: "GIANTX",
            displayedLabel: "GIANTX",
            oddsText: "2,05",
            decimalOdds: "2.05",
            status: "open",
          },
        ],
      },
      {
        label: "Map 1 Gagnant - Two options",
        tab: "tab-map-1",
        capturedAt: at,
        expanded: true,
        rawText: "Suspendu",
        outcomes: [
          {
            label: "GIANTX",
            displayedLabel: "GIANTX",
            oddsText: "",
            decimalOdds: null,
            status: "suspended",
          },
        ],
      },
    ],
  },
  ageSeconds: 500,
  expiresAt: "2026-09-08T16:46:30Z",
  freshness: "stale",
};

function replies(values: StakePublicEvent[], state = "operational", total = values.length) {
  return vi.fn((url: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          url.endsWith("/status")
            ? {
                data: {
                  enabled: true,
                  state,
                  checkedAt: at,
                  lastSuccessAt: values.length ? at : null,
                  nextAttemptAt: "2026-09-08T16:55:00Z",
                  detail: null,
                  eventCount: values.length,
                },
              }
            : {
                data: values,
                page: { offset: 0, limit: 5, total },
                meta: {
                  dataMode: "real",
                  freshness: "stale",
                  computedAt: at,
                  asOf: at,
                  appVersion: "0.1.0",
                },
              },
        ),
      ),
    ),
  );
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StakeOddsDashboard />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("reports blocked access without manufacturing matches or prices", async () => {
  const fetch = replies([], "blocked");
  vi.stubGlobal("fetch", fetch);
  const client = mount();
  expect(await screen.findByText("Accès bloqué par Stake")).toBeVisible();
  expect(await screen.findByText("Aucun match collecté")).toBeVisible();
  expect(screen.queryByText("GIANTX")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Actualiser l’affichage" }));
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledTimes(4);
  });
  expect(fetch.mock.calls.every((call) => /\/odds\/stake\/(events|status)/.test(call[0]))).toBe(
    true,
  );
  client.clear();
});

it("keeps the collection panel mounted while a slow disabled status resolves", async () => {
  let finish: ((response: Response) => void) | undefined;
  const available = replies([]);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url.endsWith("/status")
        ? new Promise<Response>((resolve) => {
            finish = resolve;
          })
        : available(url),
    ),
  );
  const client = mount();
  const panel = screen.getByRole("region", { name: "État de la collecte Stake" });
  expect(panel).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("status", { name: "Vérification de la collecte" })).toBeVisible();
  expect(screen.queryByText("Collecte désactivée")).not.toBeInTheDocument();
  await screen.findByText("Aucun match collecté");
  finish?.(
    new Response(
      JSON.stringify({
        data: {
          enabled: false,
          state: "disabled",
          checkedAt: null,
          lastSuccessAt: null,
          nextAttemptAt: null,
          detail: null,
          eventCount: 0,
        },
      }),
    ),
  );
  expect(await screen.findByText("Collecte désactivée")).toBeVisible();
  expect(screen.getByRole("region", { name: "État de la collecte Stake" })).toBe(panel);
  expect(panel).toHaveAttribute("aria-busy", "false");
  expect(
    screen.queryByRole("status", { name: "Vérification de la collecte" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/Dernière tentative/)).not.toBeInTheDocument();
  client.clear();
});

it("separates tabs and never displays a price for a suspended outcome", async () => {
  vi.stubGlobal("fetch", replies([event]));
  const client = mount();
  expect(await screen.findByText("2,05")).toBeVisible();
  expect(screen.getByText("Cotes périmées")).toBeVisible();
  expect(screen.getByText(/Format non confirmé/)).toBeVisible();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "tab-map-1" } });
  expect(screen.getByText("Suspendu")).toBeVisible();
  expect(screen.queryByText("2,05")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /page source/ })).toHaveAttribute(
    "href",
    event.capture.sourceUrl,
  );
  client.clear();
});

it("expires a previously fresh price even if the next refresh has not arrived", async () => {
  vi.stubGlobal("fetch", replies([{ ...event, freshness: "fresh" }]));
  const client = mount();
  expect(await screen.findByText("2,05")).toBeVisible();
  await waitFor(
    () => {
      expect(screen.getByText("Cotes périmées")).toBeVisible();
    },
    { timeout: 2500 },
  );
  client.clear();
});

it("explains an unreadable event without rendering an empty market selector", async () => {
  vi.stubGlobal("fetch", replies([{ ...event, capture: { ...event.capture, markets: [] } }]));
  const client = mount();
  expect(await screen.findByText(/Aucun marché lisible pour ce match/)).toBeVisible();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /nouvel onglet/ })).toBeVisible();
  client.clear();
});

it("does not turn a missing open-market price into a zero odd", async () => {
  const value = structuredClone(event);
  value.capture.markets = value.capture.markets.slice(0, 1).map((market) => ({
    ...market,
    outcomes: market.outcomes.map((outcome) => ({ ...outcome, decimalOdds: null })),
  }));
  vi.stubGlobal("fetch", replies([value]));
  const client = mount();
  expect(await screen.findByText("Cote indisponible")).toBeVisible();
  expect(screen.queryByText("0,00")).not.toBeInTheDocument();
  client.clear();
});

it("bounds large market lists and keeps every market reachable without losing the final control", async () => {
  const template = event.capture.markets[0];
  if (!template) throw new Error("The fixture requires a market");
  const value: StakePublicEvent = {
    ...event,
    capture: {
      ...event.capture,
      markets: [
        ...Array.from({ length: 30 }, (_, index) => ({
          ...template,
          label: `${index < 20 ? "Handicap équipes" : "Total manches"} ${String(index + 1)}`,
        })),
        { ...template, tab: "tab-map-1", label: "Handicap équipes carte 1" },
      ],
    },
  };
  const fetch = replies([value]);
  vi.stubGlobal("fetch", fetch);
  const client = mount();
  expect(await screen.findByText("8 marchés affichés sur 30 · Match et série")).toBeVisible();
  expect(screen.queryByText("Handicap équipes 9")).not.toBeInTheDocument();
  const more = screen.getByRole("button", { name: "Afficher plus de marchés" });
  more.focus();
  fireEvent.click(more);
  expect(screen.getByText("16 marchés affichés sur 30 · Match et série")).toBeVisible();
  expect(screen.getByText("Handicap équipes 9")).toBeVisible();
  fireEvent.click(more);
  fireEvent.click(more);
  expect(screen.getByText("30 marchés affichés sur 30 · Match et série")).toBeVisible();
  expect(screen.getByText("Total manches 30")).toBeVisible();
  expect(screen.getByRole("button", { name: "Tous les marchés sont affichés" })).toBe(more);
  expect(more).toHaveFocus();
  expect(more).toHaveAttribute("aria-disabled", "true");
  fireEvent.click(more);
  expect(screen.getByText("30 marchés affichés sur 30 · Match et série")).toBeVisible();

  const search = screen.getByRole("searchbox", { name: /Rechercher un marché pour GIANTX/ });
  fireEvent.change(search, { target: { value: "EQUIPES" } });
  expect(
    screen.getByText("8 marchés affichés sur 20 correspondants à votre recherche"),
  ).toBeVisible();
  expect(screen.queryByText("Total manches 30")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Afficher plus de marchés" }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "tab-map-1" } });
  expect(screen.getByText("1 marché affiché sur 1 correspondant à votre recherche")).toBeVisible();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "tab-main" } });
  expect(
    screen.getByText("8 marchés affichés sur 20 correspondants à votre recherche"),
  ).toBeVisible();
  fireEvent.change(search, { target: { value: "marché introuvable" } });
  expect(screen.getByText(/Aucun marché ne correspond/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Effacer la recherche" }));
  expect(search).toHaveValue("");
  expect(search).toHaveFocus();
  expect(screen.getByText("8 marchés affichés sur 30 · Match et série")).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
  client.clear();
});

it.each([
  ["failed", "Observation indisponible"],
  ["quarantined", "Observation en quarantaine"],
] as const)("preserves the %s observation state after its expiry", async (freshness, label) => {
  vi.stubGlobal("fetch", replies([{ ...event, freshness }]));
  const client = mount();
  expect(await screen.findByText(label)).toBeVisible();
  expect(screen.queryByText("Collecte dégradée")).not.toBeInTheDocument();
  client.clear();
});

it("offers a way to include past matches from an empty upcoming list", async () => {
  const fetch = replies([]);
  vi.stubGlobal("fetch", fetch);
  const client = mount();
  fireEvent.click(await screen.findByRole("button", { name: "Inclure les matchs déjà commencés" }));
  await waitFor(() => {
    expect(fetch.mock.calls.at(-1)?.[0]).toBe(
      "/api/backend/api/v1/odds/stake/events?offset=0&limit=5",
    );
  });
  expect(screen.getByRole("checkbox", { name: "Inclure les matchs déjà commencés" })).toBeChecked();
  client.clear();
});

it("returns to the first page when the list shrinks", async () => {
  const firstPage = replies([event], "operational", 6);
  const emptyPage = replies([]);
  const fetch = vi.fn((url: string) =>
    url.includes("offset=5") ? emptyPage(url) : firstPage(url),
  );
  vi.stubGlobal("fetch", fetch);
  const client = mount();
  fireEvent.click(await screen.findByRole("button", { name: "Suivants" }));
  expect(await screen.findByText("Aucun match sur cette page")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Première page" }));
  expect(await screen.findByText("2,05")).toBeVisible();
  expect(screen.getByRole("button", { name: "Précédents" })).toBeDisabled();
  client.clear();
});

it("does not label the previous filter results as the newly requested scope", async () => {
  const available = replies([event]);
  let finish: ((value: Response) => void) | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url.endsWith("/status") || url.includes("startsFrom=")
        ? available(url)
        : new Promise<Response>((resolve) => {
            finish = resolve;
          }),
    ),
  );
  const client = mount();
  expect(await screen.findByText("2,05")).toBeVisible();
  fireEvent.click(screen.getByRole("checkbox", { name: "Inclure les matchs déjà commencés" }));
  await waitFor(() => {
    expect(finish).toBeDefined();
  });
  expect(screen.queryByText("2,05")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Actualiser l’affichage" })).toBeDisabled();
  finish?.(await available("/api/backend/api/v1/odds/stake/events"));
  expect(await screen.findByText("2,05")).toBeVisible();
  expect(screen.getByText("1 match enregistré")).toBeVisible();
  client.clear();
});

it("hides cached collection details and result totals after access is revoked", async () => {
  let revoked = false;
  const available = replies([event], "operational", 6);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      revoked ? Promise.resolve(new Response("{}", { status: 403 })) : available(url),
    ),
  );
  const client = mount();
  expect(await screen.findByText("Collecte active")).toBeVisible();
  expect(await screen.findByText("2,05")).toBeVisible();
  revoked = true;
  fireEvent.click(screen.getByRole("button", { name: "Actualiser l’affichage" }));
  await waitFor(() => {
    expect(screen.queryByText("Collecte active")).not.toBeInTheDocument();
    expect(screen.queryByText("2,05")).not.toBeInTheDocument();
  });
  expect(screen.getByText("Accès refusé")).toBeVisible();
  expect(
    screen.queryByRole("navigation", { name: "Pagination des matchs Stake" }),
  ).not.toBeInTheDocument();
  client.clear();
});
