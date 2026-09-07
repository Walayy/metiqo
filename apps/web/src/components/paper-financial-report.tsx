"use client";

import type { ItemResponsePaperMetricsDto } from "@metiquo/contracts/types";
import { Card, CardContent, RemoteRecoverableErrorState } from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";

import { formatDateTime } from "./opportunity-presenters";

const metrics = [
  ["profit_loss", "P&L net", "money"],
  ["roi", "ROI / yield", "percent"],
  ["turnover", "Mises totales", "money"],
  ["settled_turnover", "Mises réglées hors void", "money"],
  ["clv", "CLV · proxy de prix", "percent"],
  ["hit_rate", "Taux de réussite", "percent"],
  ["hit_rate_mean_odds", "Cote moyenne · gains et pertes", "number"],
  ["max_drawdown", "Baisse maximale du P&L", "money"],
  ["return_volatility", "Volatilité des rendements", "percent"],
  ["open_exposure", "Exposition ouverte", "money"],
  ["max_simultaneous_exposure", "Exposition simultanée maximale", "money"],
  ["void_rate", "Taux de void", "percent"],
  ["announced_ev", "EV annoncée", "percent"],
  ["realized_minus_announced", "Réalisé − EV annoncée", "percent"],
  ["yield_ci_low", "Intervalle à 95 % · borne basse", "percent"],
  ["yield_ci_high", "Intervalle à 95 % · borne haute", "percent"],
] as const;

export function PaperFinancialReport() {
  const report = useQuery({
    queryKey: ["paper-metrics", "EUR"],
    queryFn: async ({ signal }): Promise<ItemResponsePaperMetricsDto> => {
      const response = await fetch("/api/backend/api/v1/paper-bets/metrics?currency=EUR", {
        signal,
      });
      if (!response.ok) throw new Error("Rapport financier indisponible");
      return (await response.json()) as ItemResponsePaperMetricsDto;
    },
    refetchInterval: 30_000,
  });
  if (report.isError)
    return (
      <RemoteRecoverableErrorState
        description={report.error.message}
        onRetry={() => void report.refetch()}
      />
    );
  const value = report.data?.data;
  return (
    <section aria-label="Rapport financier" className="grid min-h-40 gap-4">
      <h2 className="text-xl font-semibold">Métriques financières · EUR</h2>
      {!value?.reportId ? (
        <p className="text-sm text-ink-secondary">
          {report.isPending
            ? "Chargement du rapport…"
            : "Aucun rapport calculé dans ce mode. ROI et CLV indisponibles."}
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-secondary">
            {report.data?.meta.dataMode === "mock" ? "MOCK · " : "RÉEL · "}
            {value.bets} paris · {value.signals} signaux · {value.pendingReview} en revue · calculé
            le {formatDateTime(value.computedAt ?? "")}{" "}
            {report.data?.meta.freshness === "stale" ? "· rapport à actualiser" : ""}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map(([key, label, format]) => {
              const estimate = value.estimates?.[key];
              const number = estimate?.value == null ? null : Number(estimate.value);
              const rendered =
                number == null
                  ? "Indisponible"
                  : new Intl.NumberFormat("fr-FR", {
                      maximumFractionDigits: 2,
                      ...(format === "money"
                        ? { style: "currency", currency: value.currency }
                        : format === "percent"
                          ? { style: "percent" }
                          : {}),
                    }).format(number);
              return (
                <Card key={key} aria-label={label}>
                  <CardContent className="grid gap-2 p-4">
                    <p className="text-sm text-ink-secondary">{label}</p>
                    <p
                      className={`text-xl font-semibold ${number !== null && number < 0 ? "text-red-700 dark:text-red-300" : ""}`}
                    >
                      {rendered}
                    </p>
                    <p className="text-xs text-ink-secondary">
                      n = {estimate?.sampleSize ?? 0}
                      {estimate?.unavailableReason ? " · échantillon ou preuve insuffisant" : ""}
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
          <p className="text-xs leading-5 text-ink-secondary">
            Le CLV est un proxy des prix observés. L’intervalle utilise des blocs de jours UTC ; les
            réévaluations d’entrée ne sont pas des événements indépendants. Les rapports antérieurs
            restent conservés après correction.
          </p>
          <a
            className="w-fit text-sm font-semibold underline"
            href={`/api/backend/api/v1/paper-reports/${value.reportId}`}
          >
            Télécharger le rapport complet et son audit
          </a>
        </>
      )}
    </section>
  );
}
