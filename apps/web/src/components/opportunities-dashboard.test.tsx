import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { OpportunitiesDashboard } from "./opportunities-dashboard";

const navigation = vi.hoisted(() => ({ params: new URLSearchParams(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: navigation.replace }),
  useSearchParams: () => navigation.params,
}));

function mount(search = "") {
  navigation.params = new URLSearchParams(search);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <OpportunitiesDashboard />
    </QueryClientProvider>,
  );
  return { client, ...view };
}

beforeEach(() => {
  navigation.replace.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            data: [],
            page: { offset: 0, limit: 100, total: 0 },
            meta: {
              dataMode: "mock",
              freshness: "fresh",
              asOf: "2026-09-09T00:00:00Z",
              computedAt: "2026-09-09T00:00:00Z",
              appVersion: "0.1.0",
            },
          }),
        ),
      ),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("collapses unapplied mobile filters and preserves a draft when toggled", async () => {
  const { client } = mount("display=cards&sort=start-asc&eligibility=all&offset=100");
  const toggle = screen.getByRole("button", { name: "Filtres (0 actifs)" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveAttribute("aria-controls", "opportunity-filter-fields");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const team = screen.getByLabelText("Équipe", { exact: true });
  fireEvent.change(team, { target: { value: "Aurore 10" } });
  fireEvent.click(toggle);
  fireEvent.click(toggle);
  expect(team).toHaveValue("Aurore 10");
  // A typed draft does not masquerade as an applied URL filter.
  expect(toggle).toHaveAccessibleName("Filtres (0 actifs)");
  fireEvent.click(screen.getByRole("button", { name: "Appliquer" }));
  expect(navigation.replace).toHaveBeenCalledWith(
    "/?display=cards&sort=start-asc&eligibility=all&team=Aurore+10",
    { scroll: false },
  );
  await screen.findByText("Aucun signal sur cette page");
  client.clear();
});

it("opens applied shared filters and exposes their count without counting display preferences", async () => {
  const { client } = mount("team=Aurore+02&grade=STRONG_VALUE&display=cards&sort=start-asc");
  const toggle = screen.getByRole("button", { name: "Filtres (2 actifs)" });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByLabelText("Équipe", { exact: true })).toHaveValue("Aurore 02");
  expect(screen.getByText(/2 filtres appliqués/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Effacer" })).toHaveAttribute(
    "href",
    "/?display=cards&sort=start-asc",
  );
  await waitFor(() => {
    expect(
      within(screen.getByRole("region", { name: "Résumé du dashboard" })).getByRole("region", {
        name: "Opportunités admissibles",
      }),
    ).toHaveTextContent("0 signaux évalués");
  });
  expect(screen.getByRole("region", { name: "Dernière mise à jour" })).toHaveTextContent(
    "Aucun snapshot",
  );
  expect(screen.getByRole("region", { name: "Santé des sources" })).toHaveTextContent(
    "Aucune source déclarée",
  );
  client.clear();
});

it("does not count unsupported or whitespace-only URL criteria as active filters", async () => {
  const { client } = mount("team=%20%20&grade=UNKNOWN&freshness=UNKNOWN");
  expect(screen.getByRole("button", { name: "Filtres (0 actifs)" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await screen.findByText("Aucun signal disponible");
  client.clear();
});
