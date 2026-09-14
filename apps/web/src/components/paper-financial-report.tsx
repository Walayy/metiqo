"use client";

import { canReadPrevious, readBackend } from "../lib/backend";
import { QueryRecovery } from "./query-recovery";

import type { ItemResponsePaperMetricsDto } from "@metiquo/contracts/types";
import {
  Button,
  Metric,
  MetricGrid,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
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
      const response = await readBackend("/api/backend/api/v1/paper-bets/metrics?currency=EUR", {
        signal,
      });
      if (!response.ok) throw new Error("Rapport financier indisponible");
      return (await response.json()) as ItemResponsePaperMetricsDto;
    },
    refetchInterval: 30_000,
  });
  if (report.isError && !canReadPrevious(report))
    return (
      <section
        aria-label="Rapport financier"
        id="paper-report"
        tabIndex={-1}
        aria-busy={report.isFetching}
        className="grid min-w-0 gap-4"
      >
        <h2 className="ui-section-title">Métriques financières · EUR</h2>
        <RemoteRecoverableErrorState
          title="Rapport financier indisponible"
          description={report.error.message}
          onRetry={() => void report.refetch()}
          retryDisabled={report.isFetching}
        />
      </section>
    );
  const value = report.data?.data;
  if (report.isPending || !value?.reportId || !report.data) {
    return (
      <section
        aria-label="Rapport financier"
        id="paper-report"
        tabIndex={-1}
        aria-busy={report.isFetching}
        className="grid min-w-0 gap-4"
      >
        <QueryRecovery queries={[report]} />
        <h2 className="ui-section-title">Métriques financières · EUR</h2>
        {report.isPending ? (
          <RemoteLoadingState label="Chargement du rapport financier" minHeight="9rem" rows={3} />
        ) : (
          <RemoteEmptyState
            title="Aucun rapport financier"
            description="Aucun rapport calculé dans ce mode. ROI et CLV indisponibles. Les décisions enregistrées restent consultables dans l’historique."
            action={
              <Button asChild variant="outline" size="small">
                <a href="#paper-history">Consulter l’historique</a>
              </Button>
            }
          />
        )}
      </section>
    );
  }
  return (
    <section
      aria-label="Rapport financier"
      id="paper-report"
      tabIndex={-1}
      aria-busy={report.isFetching}
      className="grid min-w-0 gap-4"
    >
      <QueryRecovery queries={[report]} />
      <h2 className="ui-section-title">Métriques financières · EUR</h2>
      <p
        className="min-h-15 text-sm leading-5 text-ink-secondary sm:min-h-10 xl:min-h-5"
        role="status"
      >
        {report.data.meta.dataMode === "mock" ? "SIMULÉ · " : "RÉEL · "}
        {value.bets ?? "—"} paris · {value.signals ?? "—"} signaux · {value.pendingReview ?? "—"} en
        revue · calculé le {formatDateTime(value.computedAt ?? report.data.meta.computedAt)}{" "}
        {report.data.meta.freshness !== "fresh" ? "· rapport à actualiser" : ""}
      </p>
      <MetricGrid>
        {metrics.map(([key, label, format]) => {
          const estimate = value.estimates?.[key];
          const rawNumber = estimate?.value == null ? null : Number(estimate.value);
          const number = rawNumber !== null && Number.isFinite(rawNumber) ? rawNumber : null;
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
            <Metric
              key={key}
              aria-label={label}
              role="region"
              className="border-t border-border-subtle"
              emphasis="statistic"
              label={label}
              value={
                <span
                  className={
                    number !== null && number < 0 ? "text-red-700 dark:text-red-300" : undefined
                  }
                >
                  {rendered}
                </span>
              }
              detail={
                estimate ? (
                  <span>
                    n = {estimate.sampleSize}
                    {estimate.unavailableReason ? " · échantillon ou preuve insuffisant" : ""}
                  </span>
                ) : (
                  "Échantillon indisponible"
                )
              }
            />
          );
        })}
      </MetricGrid>
      <p className="text-xs leading-5 text-ink-secondary">
        Le CLV est un proxy des prix observés. L’intervalle utilise des blocs de jours UTC ; les
        réévaluations d’entrée ne sont pas des événements indépendants. Les rapports antérieurs
        restent conservés après correction.
      </p>
      <div className="flex min-h-[var(--metiquo-control-height)] items-start text-sm leading-5">
        <Button asChild variant="outline" size="small">
          <a
            download={`rapport-paper-${value.reportId}.json`}
            href={`/api/backend/api/v1/paper-reports/${encodeURIComponent(value.reportId)}`}
          >
            Télécharger le rapport complet et son audit
          </a>
        </Button>
      </div>
    </section>
  );
}
