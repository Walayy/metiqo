import type { ItemResponsePaperMetricsDto } from "@metiquo/contracts/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { PaperFinancialReport } from "./paper-financial-report";

const emptyReport: ItemResponsePaperMetricsDto = {
  data: { currency: "EUR", reportId: null, methodVersion: "paper-finance-test" },
  meta: {
    asOf: "2026-09-08T12:00:00Z",
    computedAt: "2026-09-08T12:00:00Z",
    dataMode: "mock",
    freshness: "fresh",
    appVersion: "test",
  },
};
const clients: QueryClient[] = [];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <PaperFinancialReport />
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

it("replaces an absent report with one helpful empty state without sixteen empty metrics", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(emptyReport)));
  mount();
  expect(await screen.findByRole("heading", { name: "Aucun rapport financier" })).toBeVisible();
  const report = screen.getByRole("region", { name: "Rapport financier" });
  expect(within(report).queryByText("Échantillon indisponible")).not.toBeInTheDocument();
  expect(within(report).queryByRole("region", { name: "P&L net" })).not.toBeInTheDocument();
  expect(within(report).getByRole("link", { name: "Consulter l’historique" })).toHaveAttribute(
    "href",
    "#paper-history",
  );
});

it("keeps all report metrics including unavailable estimates and a downloadable audit", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json({
        ...emptyReport,
        data: {
          currency: "EUR",
          reportId: "report-id",
          bets: 1,
          estimates: {
            profit_loss: { value: "-10", sampleSize: 1 },
            roi: { value: null, sampleSize: 1, unavailableReason: "INSUFFICIENT_DATA" },
          },
        },
      }),
    ),
  );
  mount();
  const net = await screen.findByRole("region", { name: "P&L net" });
  expect(net).toHaveTextContent(/-10,00\s*€/);
  const report = screen.getByRole("region", { name: "Rapport financier" });
  expect(within(report).getAllByRole("region")).toHaveLength(16);
  expect(within(report).getByRole("region", { name: "ROI / yield" })).toHaveTextContent(
    "Indisponible",
  );
  expect(
    within(report).getByRole("link", { name: "Télécharger le rapport complet et son audit" }),
  ).toHaveAttribute("download", "rapport-paper-report-id.json");
});
