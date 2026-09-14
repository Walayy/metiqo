import type { PageResponseObservedOddsQuote } from "@metiquo/contracts/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ObservedOddsDashboard } from "./observed-odds-dashboard";

const quote: PageResponseObservedOddsQuote["data"][number] = {
  oddsSnapshotId: "a860da6e-955b-49a5-8292-f8a9e66f3fcb",
  provider: "stake-observed",
  providerType: "manual_import",
  providerStatus: "operational",
  event: {
    providerEventId: "822193-giantx-natus-vincere",
    gameTitle: "lol",
    competition: "LEC 2026 Summer Playoffs",
    participants: ["GIANTX", "Natus Vincere"],
    startsAt: "2026-09-11T15:00:00Z",
    bestOf: null,
    status: "scheduled",
    collectedAt: "2026-09-08T15:39:40Z",
    sourceReference: "stake-web:822193:20260908T153940Z",
  },
  marketLabel: "Vainqueur du match - Two options",
  period: "SERIES",
  marketStatus: "open",
  selectionLabel: "GIANTX",
  decimalOdds: "2.05",
  capturedAt: "2026-09-08T15:39:40Z",
  ageSeconds: 3600,
  freshness: "stale",
  informationalOnly: true,
};

function response(data: PageResponseObservedOddsQuote["data"], total = data.length) {
  const payload: PageResponseObservedOddsQuote = {
    data,
    page: { offset: 0, limit: 20, total },
    meta: {
      dataMode: "real",
      freshness: "stale",
      asOf: "2026-09-08T15:39:40Z",
      computedAt: "2026-09-08T16:39:40Z",
      appVersion: "0.1.0",
    },
  };
  return new Response(JSON.stringify(payload));
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ObservedOddsDashboard />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("observed odds", () => {
  it("keeps recorded odds, unknown format and stale informational status explicit", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([quote])));
    const client = mount();
    expect(await screen.findByText("2,05")).toBeVisible();
    expect(screen.getByText("Périmée")).toBeVisible();
    expect(screen.getByText("Information uniquement")).toBeVisible();
    expect(screen.getByText(/Format non confirmé/)).toBeVisible();
    expect(screen.getByText(/Cela ne collecte pas de nouvelles cotes sur Stake/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Page suivante" })).toBeDisabled();
    client.clear();
  });

  it("shows an empty state without generating matches", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([])));
    const client = mount();
    expect(await screen.findByText("Aucune cote collectée")).toBeVisible();
    expect(screen.queryByText("GIANTX")).not.toBeInTheDocument();
    client.clear();
  });

  it("retries an unavailable source and then reads the next page", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("{}", { status: 503 }))
      .mockResolvedValueOnce(response([quote], 21))
      .mockResolvedValueOnce(response([]));
    vi.stubGlobal("fetch", fetch);
    const client = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
    expect(await screen.findByText("2,05")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Page suivante" }));
    await waitFor(() => {
      expect(fetch.mock.calls[2]?.[0]).toContain("offset=20");
    });
    expect(await screen.findByRole("button", { name: "Première page" })).toBeVisible();
    client.clear();
  });

  it("can refresh an empty collection when its first observation becomes available", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([quote]));
    vi.stubGlobal("fetch", fetch);
    const client = mount();
    expect(await screen.findByText("Aucune cote collectée")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Actualiser les observations" }));
    expect(await screen.findByText("2,05")).toBeVisible();
    expect(screen.getByText("1 sélection enregistrée")).toBeVisible();
    client.clear();
  });

  it("shows the market period when the same participant appears in several markets", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([{ ...quote, period: "GAME_2" }])));
    const client = mount();
    expect(await screen.findByText(/Vainqueur du match - Two options · Carte 2/)).toBeVisible();
    client.clear();
  });

  it("hides cached observations and totals after access is revoked", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([quote], 21))
      .mockResolvedValueOnce(new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    const client = mount();
    expect(await screen.findByText("2,05")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Actualiser les observations" }));
    expect(await screen.findByText("Accès refusé")).toBeVisible();
    expect(screen.queryByText("2,05")).not.toBeInTheDocument();
    expect(screen.queryByText("21 sélections enregistrées")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Pagination des cotes" }),
    ).not.toBeInTheDocument();
    client.clear();
  });
});
