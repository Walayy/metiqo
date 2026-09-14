"use client";

import type { PageResponseObservedOddsQuote } from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemotePageLoadingState,
} from "@metiquo/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { canReadPrevious, readBackend } from "../lib/backend";
import { formatDateTime } from "./opportunity-presenters";
import { QueryFailure, QueryRecovery } from "./query-recovery";

const freshnessLabels = {
  fresh: "Récente",
  stale: "Périmée",
  degraded: "Source dégradée",
  failed: "Indisponible",
  quarantined: "En quarantaine",
};
const marketLabels = {
  open: "Ouvert",
  suspended: "Suspendu",
  closed: "Fermé",
  settled: "Réglé",
  void: "Annulé",
};

async function fetchQuotes(offset: number, signal: AbortSignal) {
  const response = await readBackend(
    `/api/backend/api/v1/odds/quotes?offset=${String(offset)}&limit=20`,
    {
      headers: { accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) throw new Error("Les cotes ne sont pas disponibles");
  return (await response.json()) as PageResponseObservedOddsQuote;
}

export function ObservedOddsDashboard() {
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["observed-odds", offset],
    queryFn: ({ signal }) => fetchQuotes(offset, signal),
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
  });

  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-2">
        <h2 className="ui-section-title">Relevés de vainqueurs</h2>
        <p className="text-body text-ink-secondary">
          Dernier prix enregistré pour chaque sélection. Les observations sont relues toutes les 15
          secondes ; cette actualisation ne déclenche pas de collecte.
        </p>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-secondary" role="status">
          {query.data && canReadPrevious(query)
            ? `${String(query.data.page.total)} sélection${query.data.page.total === 1 ? "" : "s"} enregistrée${query.data.page.total === 1 ? "" : "s"}`
            : "Observations enregistrées"}
        </p>
        <div className="flex flex-wrap gap-2">
          {offset > 0 ? (
            <Button
              variant="outline"
              disabled={query.isFetching}
              onClick={() => {
                setOffset(0);
              }}
            >
              Première page
            </Button>
          ) : null}
          <Button
            variant="outline"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {query.isFetching && !query.isPending
              ? "Actualisation…"
              : "Actualiser les observations"}
          </Button>
        </div>
      </div>
      <RemoteDataBoundary
        isLoading={query.isPending}
        isRefetching={query.isFetching && !query.isPending}
        loadingFallback={<RemotePageLoadingState label="Chargement des cotes" rows={4} />}
      >
        <QueryRecovery queries={[query]} />
        {query.isError && !canReadPrevious(query) ? (
          <QueryFailure
            description="Les observations ne répondent pas pour le moment."
            missingTitle="Observations indisponibles"
            missingDescription="Cette page de relevés n’est plus disponible."
            queries={[query]}
          />
        ) : query.data?.data.length === 0 ? (
          <RemoteEmptyState
            title={offset > 0 ? "Aucune cote sur cette page" : "Aucune cote collectée"}
            description={
              offset > 0
                ? "Les résultats ont changé. Revenez à la première page pour consulter les observations disponibles."
                : query.data.meta.dataMode === "mock"
                  ? "Le mode mock est actif. Les relevés réels sont consultables en mode réel."
                  : "Aucun relevé de vainqueur n’a encore été enregistré. L’onglet Marchés Stake présente l’état de la collecte."
            }
          />
        ) : query.data ? (
          <section className="grid gap-4" aria-label="Cotes observées">
            {query.data.data.some((quote) => quote.providerType === "manual_import") ? (
              <p className="ui-inline-notice">
                Relevés manuels : actualiser cet écran relit les données enregistrées. Cela ne
                collecte pas de nouvelles cotes sur Stake.
              </p>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-2">
              {query.data.data.map((quote) => (
                <Card
                  key={quote.oddsSnapshotId}
                  aria-label={`${quote.event.participants.join(" contre ")} — ${quote.selectionLabel} — ${quote.period}`}
                >
                  <CardContent className="grid min-w-0 gap-3">
                    <p className="ui-eyebrow">
                      {quote.provider} · {quote.event.competition}
                    </p>
                    <h3 className="break-words text-lg font-semibold">
                      {quote.event.participants.join(" vs ")}
                    </h3>
                    <p className="text-sm text-ink-secondary">
                      {formatDateTime(quote.event.startsAt)} ·{" "}
                      {quote.event.bestOf === null
                        ? "Format non confirmé"
                        : `Best of ${String(quote.event.bestOf)}`}
                    </p>
                    <p className="break-words">
                      {quote.marketLabel} ·{" "}
                      {quote.period === "SERIES"
                        ? "Série"
                        : `Carte ${quote.period.replace("GAME_", "")}`}
                    </p>
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <span className="min-w-0 break-words font-semibold">
                        {quote.selectionLabel}
                      </span>
                      <span className="shrink-0 text-2xl font-bold tabular-nums">
                        <span className="sr-only">Cote enregistrée : </span>
                        {Number(quote.decimalOdds).toLocaleString("fr-FR", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 8,
                        })}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge>{freshnessLabels[quote.freshness]}</Badge>
                      <Badge>{marketLabels[quote.marketStatus]}</Badge>
                      {quote.informationalOnly ? <Badge>Information uniquement</Badge> : null}
                    </div>
                    <p className="text-xs text-ink-secondary">
                      Observée le {formatDateTime(quote.capturedAt)} · âge au dernier contrôle :{" "}
                      {quote.ageSeconds} s
                    </p>
                    {quote.informationalOnly ? (
                      <p className="text-sm text-ink-secondary">
                        Horodatage source ou règles non vérifiés ; exclue des signaux validés.
                      </p>
                    ) : null}
                    <p className="break-all text-xs text-ink-secondary">
                      Référence : {quote.event.sourceReference}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
            <nav className="flex flex-wrap items-center gap-3" aria-label="Pagination des cotes">
              <Button
                variant="outline"
                disabled={offset === 0 || query.isFetching}
                onClick={() => {
                  setOffset(Math.max(0, offset - 20));
                }}
              >
                Page précédente
              </Button>
              <span className="text-sm" role="status">
                Page {Math.floor(offset / 20) + 1} sur{" "}
                {Math.max(1, Math.ceil(query.data.page.total / 20))}
              </span>
              <Button
                variant="outline"
                disabled={
                  offset + query.data.data.length >= query.data.page.total || query.isFetching
                }
                onClick={() => {
                  setOffset(offset + 20);
                }}
              >
                Page suivante
              </Button>
            </nav>
          </section>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
