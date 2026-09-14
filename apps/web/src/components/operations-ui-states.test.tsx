import type {
  BacktestSummary,
  IngestionRunSummary,
  MappingReview,
  ModelSummary,
  ProviderHealth,
} from "@metiquo/contracts/types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminOperationsDashboard, DataHealthDashboard } from "./data-health-dashboard";
import { MappingReviewQueue } from "./mapping-review-queue";
import { ModelsDashboard } from "./models-dashboard";
import { ReleaseCompliancePanel } from "./release-compliance-panel";

const instant = "2026-09-08T10:00:00Z";
const meta = {
  dataMode: "mock",
  freshness: "fresh",
  asOf: instant,
  computedAt: instant,
  appVersion: "0.1.0",
};
const clients: QueryClient[] = [];

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status });
}

function page(data: unknown[], total = data.length) {
  return { data, meta, page: { total, offset: 0, limit: 100 } };
}

function mount(content: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  render(<QueryClientProvider client={client}>{content}</QueryClientProvider>);
  return client;
}

const model: ModelSummary = {
  algorithm: "logistic",
  artifactHash: "artifact",
  baselineMetrics: { log_loss: "0.7" },
  codeCommit: "commit",
  createdAt: instant,
  datasetHash: "dataset",
  featureVersion: "features-v1",
  gameTitle: "lol",
  marketType: "MATCH_WINNER",
  metrics: { log_loss: "0.6", brier: "0.2" },
  modelVersion: "champion-v1",
  modelVersionId: "model-1",
  status: "champion",
  trainCutoff: instant,
};
const backtest: BacktestSummary = {
  backtestId: "backtest-1",
  baselineMetrics: { log_loss: "0.7" },
  completedAt: instant,
  startsAt: instant,
  endsAt: instant,
  finalTestUntouched: true,
  kind: "statistical",
  metrics: { log_loss: "0.6", brier: "0.2" },
  modelVersionId: "model-1",
  sampleCount: 600,
};
const review: MappingReview = {
  mappingReviewId: "review-1",
  provider: "provider-test",
  providerEventId: "external-match",
  rawCompetition: "Ligue",
  rawParticipants: ["Équipe A", "Équipe B"],
  createdAt: instant,
  status: "pending",
  candidates: [
    {
      eventId: "canonical-1",
      label: "Équipe A — Équipe B",
      confidence: "0.8",
      reasons: ["Même horaire"],
      teamAId: "team-a",
      teamA: "Équipe A",
      teamBId: "team-b",
      teamB: "Équipe B",
    },
  ],
};

afterEach(() => {
  cleanup();
  for (const client of clients.splice(0)) client.clear();
  vi.unstubAllGlobals();
});

describe("independent model and validation states", () => {
  it("keeps the model registry available while backtests fail and retries only their endpoint", async () => {
    let failed = true;
    const reads: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) => {
        reads.push(input);
        return Promise.resolve(
          input.includes("/backtests")
            ? failed
              ? json({}, 503)
              : json(page([backtest]))
            : json(page([model])),
        );
      }),
    );
    mount(<ModelsDashboard />);
    expect(await screen.findByRole("region", { name: "Modèle champion-v1" })).toBeVisible();
    const panel = screen.getByRole("region", { name: "Performance temporelle et segments" });
    expect(await within(panel).findByText("Backtests indisponibles")).toBeVisible();
    expect(
      within(screen.getByRole("region", { name: "Backtests" })).getByText("N/D"),
    ).toBeVisible();
    failed = false;
    fireEvent.click(within(panel).getByRole("button", { name: "Réessayer" }));
    expect(
      await within(panel).findByRole("region", { name: "Performance temporelle des backtests" }),
    ).toBeVisible();
    expect(reads.filter((url) => url.includes("/models?"))).toHaveLength(1);
  });

  it.each(["empty", "failed"] as const)(
    "keeps backtest evidence accessible when the registry is %s",
    async (state) => {
      vi.stubGlobal(
        "fetch",
        vi.fn((input: string) =>
          Promise.resolve(
            input.includes("/backtests")
              ? json(page([backtest]))
              : state === "empty"
                ? json(page([]))
                : json({}, 503),
          ),
        ),
      );
      mount(<ModelsDashboard />);
      expect(
        await screen.findByRole("region", { name: "Performance temporelle des backtests" }),
      ).toBeVisible();
      expect(screen.getByRole("cell", { name: "model-1" })).toBeVisible();
    },
  );

  it("shows a failed promotion next to its candidate without making training appear active", async () => {
    const candidate = {
      ...model,
      modelVersion: "candidate-v2",
      modelVersionId: "model-2",
      status: "candidate",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string, init?: RequestInit) =>
        Promise.resolve(
          init?.method === "POST"
            ? json({ detail: "Validation insuffisante pour cette version." }, 409)
            : json(page(input.includes("/models?") ? [model, candidate] : [backtest])),
        ),
      ),
    );
    mount(<ModelsDashboard />);
    const card = await screen.findByRole("region", { name: "Modèle candidate-v2" });
    fireEvent.click(within(card).getByRole("button", { name: "Promouvoir" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Validation insuffisante");
    expect(screen.getByRole("button", { name: "Entraîner un candidat" })).toHaveAttribute(
      "aria-busy",
      "false",
    );
    expect(
      screen.queryByText("Capacité contractuelle active : MATCH_WINNER."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Vérifier les capacités par snapshot" }),
    ).toHaveAttribute("href", "/data");
  });
});

describe("explicit mapping decisions", () => {
  it("requires a chosen candidate, creates the alias for the inverted team, and focuses the decision receipt", async () => {
    const firstCandidate = review.candidates[0];
    if (!firstCandidate) throw new Error("The fixture requires a candidate");
    const inverted: MappingReview = {
      ...review,
      candidates: [{ ...firstCandidate, selectionsInverted: true, teamAId: null }],
    };
    const writes: { url: string; body: Record<string, unknown> }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string, init?: RequestInit) => {
        if (init?.method !== "POST") return Promise.resolve(json(page([inverted])));
        if (typeof init.body !== "string") throw new Error("Expected a JSON request body");
        const body = JSON.parse(init.body) as Record<string, unknown>;
        writes.push({ url: input, body });
        return Promise.resolve(
          json({
            data: input.endsWith("/aliases")
              ? {
                  aliasId: "alias-1",
                  alias: body.alias,
                  canonicalId: body.canonicalId,
                  createdAt: instant,
                }
              : {
                  ...inverted,
                  selectedEventId: "canonical-1",
                  status: "approved",
                  reviewer: "admin-local",
                  reviewedAt: instant,
                  decisionReason: body.reason,
                },
            meta,
          }),
        );
      }),
    );
    mount(<MappingReviewQueue />);
    const candidate = await screen.findByRole("radio");
    expect(candidate).not.toBeChecked();
    fireEvent.change(screen.getByLabelText("Motif obligatoire"), {
      target: { value: "Horaire et équipes vérifiés" },
    });
    expect(screen.getByRole("button", { name: "Approuver le candidat" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Créer l’alias daté" })).toBeDisabled();
    fireEvent.click(candidate);
    expect(screen.getByText("Les observations existantes", { exact: false })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Créer l’alias daté" }));
    expect(await screen.findByText("Alias créé et daté")).toBeVisible();
    expect(writes[0]?.body.canonicalId).toBe("team-b");
    fireEvent.click(screen.getByRole("button", { name: "Approuver le candidat" }));
    const receipt = await screen.findByText("Décision approved");
    await waitFor(() => expect(receipt.closest("[tabindex='-1']")).toHaveFocus());
    expect(screen.queryByRole("button", { name: "Créer l’alias daté" })).not.toBeInTheDocument();
    expect(screen.getByText("Alias créé et daté")).toBeVisible();
    expect(writes[1]?.body.candidateEventId).toBe("canonical-1");
  });

  it("allows a reasoned rejection when no candidate exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(() => Promise.resolve(json(page([{ ...review, candidates: [] }])))),
    );
    mount(<MappingReviewQueue />);
    const reason = await screen.findByLabelText("Motif obligatoire");
    fireEvent.change(reason, { target: { value: "Aucune correspondance" } });
    expect(screen.getByRole("button", { name: "Rejeter le mapping" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Approuver le candidat" })).toBeDisabled();
  });
});

describe("honest operational measurements", () => {
  it("keeps missing measurements and season years distinct from zero or the ingestion date", async () => {
    const source: ProviderHealth = {
      providerCode: "provider-test",
      checkedAt: instant,
      status: "operational",
    };
    const run: IngestionRunSummary = {
      runId: "run-1",
      source: "provider-test",
      startedAt: instant,
      completedAt: instant,
      rowCount: 12,
      status: "succeeded",
      dataMode: "mock",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) =>
        Promise.resolve(
          json(
            page(
              input.includes("data-sources")
                ? [source]
                : input.includes("ingestion-runs")
                  ? [run]
                  : [],
            ),
          ),
        ),
      ),
    );
    mount(<DataHealthDashboard />);
    const catalogue = screen.getByRole("region", { name: "Catalogue des sources" });
    expect(await within(catalogue).findByText("Non mesurés")).toBeVisible();
    expect(within(catalogue).getByText("Non mesurée")).toBeVisible();
    const snapshot = screen.getByRole("region", { name: "Snapshot et couverture" });
    const seasons = within(snapshot).getByText("Saisons renseignées").closest("dl");
    expect(seasons).toHaveTextContent("Non exposée");
    expect(seasons).not.toHaveTextContent("2026");
    expect(snapshot).not.toHaveTextContent("aucun changement déclaré");
  });

  it("does not declare the whole quarantine empty from a partial page", async () => {
    const issue = {
      issueId: "issue-1",
      code: "MAPPING",
      detail: "À vérifier",
      source: "provider-test",
      observedAt: instant,
      severity: "warning",
      status: "open",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) =>
        Promise.resolve(json(input.includes("quality-issues") ? page([issue], 101) : page([]))),
      ),
    );
    mount(<DataHealthDashboard />);
    expect(
      await screen.findByText("Aucun snapshot en quarantaine parmi les anomalies chargées."),
    ).toBeVisible();
    expect(
      screen.queryByText("Aucun snapshot n’est actuellement en quarantaine."),
    ).not.toBeInTheDocument();
  });

  it("does not present an ingestion failure as successful completion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string, init?: RequestInit) =>
        Promise.resolve(
          json(
            init?.method === "POST"
              ? {
                  data: {
                    runId: "failed-run",
                    source: "provider-test",
                    startedAt: instant,
                    completedAt: instant,
                    rowCount: 0,
                    status: "failed",
                    dataMode: "mock",
                  },
                  meta,
                }
              : input.includes("system/status")
                ? { dataMode: "mock", generatedAt: instant, status: "ok", operations: null }
                : page([]),
          ),
        ),
      ),
    );
    mount(<AdminOperationsDashboard />);
    const button = await screen.findByRole("button", { name: "Lancer la synchronisation mock" });
    fireEvent.click(button);
    expect(await screen.findByText("Synchronisation non validée")).toBeVisible();
    expect(screen.queryByText("Synchronisation terminée")).not.toBeInTheDocument();
  });
});

describe("publication conditions", () => {
  it("explains gate codes and withdraws a cached authorization if its verification fails", async () => {
    let failed = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          failed
            ? json({}, 503)
            : json({
                audience: "personal",
                gates: { "RIOT-PRODUCT": "GO" },
                publicReleaseAllowed: true,
              }),
        ),
      ),
    );
    mount(<ReleaseCompliancePanel />);
    expect(await screen.findByText("RIOT-PRODUCT : GO")).toBeVisible();
    expect(screen.getByText(/GO : condition validée/)).toBeVisible();
    failed = true;
    fireEvent.click(screen.getByRole("button", { name: "Vérifier les conditions" }));
    expect(await screen.findByText("Publication bloquée : état indisponible")).toBeVisible();
    expect(screen.queryByText("RIOT-PRODUCT : GO")).not.toBeInTheDocument();
  });
});
