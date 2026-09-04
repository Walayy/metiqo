"use client";

import type {
  ItemResponseOpportunity,
  ItemResponseOpportunityExplanation,
  OddsSnapshot,
  Opportunity,
  PageResponseOddsSnapshot,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
  RemoteStaleState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  CircleAlert,
  Database,
  Scale,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { OddsChart } from "./event-detail";
import {
  describeOpportunity,
  formatDateTime,
  formatDecimal,
  formatPercent,
  formatSignedPercent,
  freshnessLabels,
  gradeLabels,
  isAdmissible,
} from "./opportunity-presenters";

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Le signal n’est pas disponible");
  return (await response.json()) as T;
}

function SectionCard({
  children,
  icon,
  title,
}: Readonly<{ children: ReactNode; icon: ReactNode; title: string }>) {
  return (
    <Card aria-label={title}>
      <CardContent className="grid gap-4 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="grid size-9 place-items-center rounded-lg bg-surface-muted text-ink-secondary"
          >
            {icon}
          </span>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: Readonly<{ label: string; value: ReactNode }>) {
  return (
    <div className="rounded-lg border border-border-subtle p-3">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className="mt-1 text-sm font-semibold">{value}</dd>
    </div>
  );
}

function PriceSections({ opportunity }: Readonly<{ opportunity: Opportunity }>) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section aria-labelledby="market-price-title" className="rounded-xl bg-surface-muted p-4">
        <h3 className="font-semibold" id="market-price-title">
          Prix du marché observé
        </h3>
        <dl className="mt-4 grid grid-cols-2 gap-3">
          <Metric label="Cote décimale" value={formatDecimal(opportunity.book.decimalOdds)} />
          <Metric
            label="Probabilité brute"
            value={formatPercent(opportunity.book.rawImpliedProbability)}
          />
          <Metric
            label="Probabilité sans marge"
            value={
              opportunity.book.noVigProbability === null
                ? "Non calculée"
                : formatPercent(opportunity.book.noVigProbability)
            }
          />
          <Metric label="Capture" value={formatDateTime(opportunity.book.capturedAt)} />
        </dl>
      </section>
      <section aria-labelledby="model-price-title" className="rounded-xl bg-surface-muted p-4">
        <h3 className="font-semibold" id="model-price-title">
          Prix du modèle indépendant
        </h3>
        <dl className="mt-4 grid grid-cols-2 gap-3">
          <Metric label="Cote juste" value={formatDecimal(opportunity.value.fairOdds)} />
          <Metric label="Probabilité" value={formatPercent(opportunity.model.probability)} />
          <Metric
            label="Intervalle"
            value={`${formatPercent(opportunity.model.probabilityLow)} – ${formatPercent(opportunity.model.probabilityHigh)}`}
          />
          <Metric label="Confiance" value={formatPercent(opportunity.model.confidence)} />
        </dl>
      </section>
    </div>
  );
}

function SnapshotHistory({ snapshots }: Readonly<{ snapshots: readonly OddsSnapshot[] }>) {
  const ordered = [...snapshots].sort((left, right) =>
    left.capturedAt.localeCompare(right.capturedAt),
  );

  return (
    <div className="grid min-w-0 gap-5">
      <OddsChart snapshots={ordered} />
      <div
        aria-label="Historique des snapshots de cote"
        className="max-w-full overflow-x-auto rounded-lg border border-border-subtle"
        role="region"
        tabIndex={0}
      >
        <table className="w-full min-w-[42rem] border-collapse text-left text-xs">
          <thead className="bg-surface-muted text-ink-secondary">
            <tr>
              {["Capturé à", "Cote", "Probabilité sans marge", "Statut marché", "Fournisseur"].map(
                (label) => (
                  <th className="px-3 py-3 font-semibold" key={label} scope="col">
                    {label}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {ordered.map((snapshot) => (
              <tr key={snapshot.oddsSnapshotId}>
                <td className="whitespace-nowrap px-3 py-3">
                  {formatDateTime(snapshot.capturedAt)}
                </td>
                <td className="px-3 py-3 font-semibold">{formatDecimal(snapshot.decimalOdds)}</td>
                <td className="px-3 py-3">
                  {snapshot.noVigProbability === null
                    ? "Non calculée"
                    : formatPercent(snapshot.noVigProbability)}
                </td>
                <td className="px-3 py-3">{snapshot.marketStatus}</td>
                <td className="px-3 py-3">{snapshot.provider}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SignalDetail({ signalId }: Readonly<{ signalId: string }>) {
  const encodedSignalId = encodeURIComponent(signalId);
  const opportunityQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseOpportunity>(`/api/v1/opportunities/${encodedSignalId}`, signal),
    queryKey: ["opportunity", signalId],
  });
  const explanationQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseOpportunityExplanation>(
        `/api/v1/opportunities/${encodedSignalId}/explanation`,
        signal,
      ),
    queryKey: ["opportunity-explanation", signalId],
  });
  const eventId = opportunityQuery.data?.data.event.eventId;
  const historyQuery = useQuery({
    enabled: eventId !== undefined,
    queryFn: ({ signal }) => {
      if (eventId === undefined) throw new Error("Événement du signal absent");
      return fetchResource<PageResponseOddsSnapshot>(
        `/api/v1/events/${encodeURIComponent(eventId)}/odds-history?offset=0&limit=100`,
        signal,
      );
    },
    queryKey: ["signal-odds-history", eventId],
  });

  const isPending =
    opportunityQuery.isPending || explanationQuery.isPending || historyQuery.isPending;
  const isFetching =
    opportunityQuery.isFetching || explanationQuery.isFetching || historyQuery.isFetching;
  const isError = opportunityQuery.isError || explanationQuery.isError || historyQuery.isError;
  const opportunity = opportunityQuery.data?.data;
  const referenceTime = opportunityQuery.data?.meta.computedAt ?? new Date(0).toISOString();
  const explanation = explanationQuery.data?.data;
  const snapshots = historyQuery.data?.data ?? [];

  return (
    <div className="grid min-w-0 gap-7">
      <div>
        <Button asChild size="small" variant="ghost">
          <Link href="/">
            <ArrowLeft aria-hidden="true" className="size-4" />
            Retour aux opportunités
          </Link>
        </Button>
      </div>

      <RemoteDataBoundary
        className="min-w-0"
        isLoading={isPending}
        isRefetching={isFetching && !isPending}
        loadingFallback={<RemoteLoadingState label="Chargement du signal" rows={8} />}
      >
        {isError ? (
          <RemoteRecoverableErrorState
            description="Le détail du signal n’a pas pu être assemblé."
            onRetry={() => {
              void Promise.all([
                opportunityQuery.refetch(),
                explanationQuery.refetch(),
                historyQuery.refetch(),
              ]);
            }}
          />
        ) : opportunity ? (
          <div className="grid min-w-0 gap-6">
            <header className="grid gap-4 rounded-xl border border-border-subtle bg-surface-raised p-5 shadow-panel sm:p-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
                    Signal de pricing · {opportunity.event.competition}
                  </p>
                  <h1 className="mt-2 text-title text-balance font-semibold tracking-tight">
                    {opportunity.event.teamA} <span className="text-ink-secondary">vs</span>{" "}
                    {opportunity.event.teamB}
                  </h1>
                  <p className="mt-2 text-sm text-ink-secondary">
                    {opportunity.market.selectionLabel} · Vainqueur du match ·{" "}
                    {formatDateTime(opportunity.event.startsAt)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge className="border-accent bg-accent-soft text-ink-primary">
                    {gradeLabels[opportunity.value.grade]}
                  </Badge>
                  <Badge className="border-border-strong bg-surface-muted text-ink-primary">
                    {freshnessLabels[opportunity.meta.freshness]}
                  </Badge>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric label="Edge" value={formatSignedPercent(opportunity.value.edge)} />
                <Metric
                  label="EV prudente"
                  value={formatSignedPercent(opportunity.value.conservativeExpectedValue)}
                />
                <Metric
                  label="EV centrale"
                  value={formatSignedPercent(opportunity.value.expectedValue)}
                />
                <Metric label="Version modèle" value={opportunity.model.modelVersion} />
              </dl>
            </header>

            {opportunity.meta.freshness === "stale" ? (
              <RemoteStaleState
                description="Le signal reste consultable pour audit, mais aucune décision paper ne doit être prise sur ce snapshot."
                title="Signal ancien — décision bloquée"
              />
            ) : null}

            <SectionCard icon={<Scale className="size-4.5" />} title="Prix marché et prix modèle">
              <PriceSections opportunity={opportunity} />
              <p className="text-xs leading-5 text-ink-secondary">
                La comparaison décrit un écart de prix sous incertitude ; elle ne constitue pas une
                promesse de résultat.
              </p>
            </SectionCard>

            <div className="grid gap-6 xl:grid-cols-2">
              <SectionCard icon={<Activity className="size-4.5" />} title="Facteurs structurés">
                <dl className="grid grid-cols-2 gap-3">
                  <Metric
                    label="Confiance du mapping"
                    value={formatPercent(opportunity.quality.mappingConfidence)}
                  />
                  <Metric
                    label="Couverture des données"
                    value={formatPercent(opportunity.quality.dataCoverage)}
                  />
                  <Metric
                    label="Confiance du modèle"
                    value={formatPercent(opportunity.model.confidence)}
                  />
                  <Metric
                    label="Distance hors distribution"
                    value={formatDecimal(opportunity.model.outOfDistributionDistance)}
                  />
                </dl>
                <p className="text-xs leading-5 text-ink-secondary">
                  Ces facteurs sont des indicateurs associés au calcul. Ils ne sont pas présentés
                  comme des causes du résultat sportif.
                </p>
              </SectionCard>

              <SectionCard
                icon={<ShieldAlert className="size-4.5" />}
                title="Risques et incertitude"
              >
                <div className="rounded-lg border border-border-subtle bg-surface-muted p-4">
                  <p className="text-xs text-ink-secondary">Intervalle de probabilité</p>
                  <p className="mt-1 text-lg font-semibold">
                    {formatPercent(opportunity.model.probabilityLow)} –{" "}
                    {formatPercent(opportunity.model.probabilityHigh)}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Réductions de confiance</h3>
                  {opportunity.model.confidenceReductionReasons?.length ? (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-secondary">
                      {opportunity.model.confidenceReductionReasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-sm text-ink-secondary">Aucune raison déclarée.</p>
                  )}
                </div>
              </SectionCard>
            </div>

            <div className="grid gap-6 xl:grid-cols-2">
              <SectionCard
                icon={<CheckCircle2 className="size-4.5" />}
                title="Qualité et fraîcheur"
              >
                <dl className="grid grid-cols-2 gap-3">
                  <Metric
                    label="Décision"
                    value={opportunity.quality.publishable ? "Publiable" : "Bloquée"}
                  />
                  <Metric
                    label="Fraîcheur source"
                    value={freshnessLabels[opportunity.quality.sourceFreshness]}
                  />
                  <Metric label="Statut modèle" value={opportunity.quality.modelStatus} />
                  <Metric
                    label="Cote informative seulement"
                    value={opportunity.book.informationalOnly ? "Oui" : "Non"}
                  />
                </dl>
                <p className="text-sm leading-6 text-ink-secondary">
                  {describeOpportunity(opportunity)}
                </p>
              </SectionCard>

              <SectionCard icon={<CircleAlert className="size-4.5" />} title="Raisons d’abstention">
                {explanation?.reasons.length ? (
                  <ul className="grid gap-2">
                    {explanation.reasons.map((reason) => (
                      <li
                        className="rounded-lg border border-border-subtle bg-surface-muted px-3 py-2 text-sm"
                        key={reason}
                      >
                        {reason}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-ink-secondary">Aucune raison d’abstention.</p>
                )}
                <p className="break-all text-xs text-ink-secondary">
                  Référence d’explication : {explanation?.reference ?? "Non disponible"}
                </p>
              </SectionCard>
            </div>

            <SectionCard
              icon={<Database className="size-4.5" />}
              title="Historique des prix observés"
            >
              <SnapshotHistory snapshots={snapshots} />
            </SectionCard>

            <SectionCard
              icon={<BookOpenCheck className="size-4.5" />}
              title="Règlement paper trading"
            >
              <dl className="grid gap-3 sm:grid-cols-3">
                <Metric label="Marché" value="Vainqueur du match" />
                <Metric label="Sélection" value={opportunity.market.selectionLabel} />
                <Metric
                  label="Version des règles"
                  value={opportunity.market.settlementRulesVersion ?? "Non versionnée — bloqué"}
                />
              </dl>
              <p className="text-xs leading-5 text-ink-secondary">
                Le règlement conserve la prédiction et le snapshot de cote d’origine. Aucun pari
                réel n’est exécuté.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link href={`/events/${encodeURIComponent(opportunity.event.eventId)}`}>
                    Voir l’événement
                  </Link>
                </Button>
                {isAdmissible(opportunity, referenceTime) ? (
                  <Button asChild>
                    <Link href={`/paper-trading?signalId=${encodedSignalId}`}>
                      Créer un paper bet
                    </Link>
                  </Button>
                ) : (
                  <Button disabled>Paper bet bloqué</Button>
                )}
              </div>
            </SectionCard>
          </div>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
