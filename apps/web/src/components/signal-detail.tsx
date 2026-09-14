"use client";

import { QueryFailure, QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend } from "../lib/backend";

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
  ContextPanel,
  TitledCard as SectionCard,
  Metric,
  MetricGrid,
  TechnicalText,
  Table,
  TableBody,
  TableCell,
  TableRow,
  RemoteDataBoundary,
  RemoteLoadingState,
  RemotePageLoadingState,
  RemoteRecoverableErrorState,
  RemoteStaleState,
} from "@metiquo/ui";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
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

import { marketStatusLabels, OddsChart } from "./event-detail";
import { nextPageOffset, PagedResults } from "./paged-results";
import {
  describeOpportunity,
  formatAbstentionReasons,
  formatDateTime,
  formatDecimal,
  formatPercent,
  formatSignedPercent,
  freshnessLabels,
  gradeLabels,
  isAdmissible,
  latestMatchingOddsSnapshot,
  matchingOddsSnapshots,
  newerOddsSnapshot,
} from "./opportunity-presenters";

const ODDS_REFRESH_INTERVAL_MS = 30_000;

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Le signal n’est pas disponible");
  return (await response.json()) as T;
}

function PriceSections({ opportunity }: Readonly<{ opportunity: Opportunity }>) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section
        aria-labelledby="market-price-title"
        className="min-w-0 border-t border-border-subtle pt-3"
      >
        <h3 className="font-semibold" id="market-price-title">
          Prix du marché observé
        </h3>
        <MetricGrid className="mt-3">
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
        </MetricGrid>
      </section>
      <section
        aria-labelledby="model-price-title"
        className="min-w-0 border-t border-border-subtle pt-3"
      >
        <h3 className="font-semibold" id="model-price-title">
          Prix du modèle indépendant
        </h3>
        <MetricGrid className="mt-3">
          <Metric label="Cote juste" value={formatDecimal(opportunity.value.fairOdds)} />
          <Metric label="Probabilité" value={formatPercent(opportunity.model.probability)} />
          <Metric
            label="Intervalle"
            value={`${formatPercent(opportunity.model.probabilityLow)} – ${formatPercent(opportunity.model.probabilityHigh)}`}
          />
          <Metric label="Confiance" value={formatPercent(opportunity.model.confidence)} />
        </MetricGrid>
      </section>
    </div>
  );
}

function SnapshotHistory({
  latestSnapshotId,
  signalSnapshotId,
  snapshots,
}: Readonly<{
  latestSnapshotId: string | undefined;
  signalSnapshotId: string;
  snapshots: readonly OddsSnapshot[];
}>) {
  const ordered = [...snapshots].sort((left, right) =>
    left.capturedAt.localeCompare(right.capturedAt),
  );

  if (ordered.length === 0) {
    return <p className="text-sm text-ink-secondary">Aucune cote observée pour cette sélection.</p>;
  }

  return (
    <div className="grid min-w-0 gap-5">
      <OddsChart snapshots={ordered} />
      <Table
        aria-label="Historique des snapshots de cote"
        columns={[
          { label: "Repère", variant: "status", weight: 1.8 },
          { label: "Capturé à", variant: "date" },
          { label: "Cote", variant: "number" },
          { label: "Probabilité sans marge", variant: "number", weight: 1.4 },
          { label: "Statut marché", variant: "status" },
          { label: "Fournisseur", variant: "text" },
        ]}
      >
        <TableBody>
          {ordered.map((snapshot) => (
            <TableRow key={snapshot.oddsSnapshotId}>
              <TableCell label="Repère" variant="status">
                {snapshot.oddsSnapshotId === signalSnapshotId ? (
                  <Badge className="border-border-subtle bg-accent-soft text-ink-primary">
                    Snapshot du signal
                  </Badge>
                ) : snapshot.oddsSnapshotId === latestSnapshotId ? (
                  <Badge className="border-border-strong bg-surface-muted text-ink-primary">
                    Dernière cote
                  </Badge>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell label="Capturé à" variant="date">
                {formatDateTime(snapshot.capturedAt)}
              </TableCell>
              <TableCell label="Cote" variant="number">
                {formatDecimal(snapshot.decimalOdds)}
              </TableCell>
              <TableCell label="Probabilité sans marge" variant="number">
                {snapshot.noVigProbability === null
                  ? "Non calculée"
                  : formatPercent(snapshot.noVigProbability)}
              </TableCell>
              <TableCell label="Statut marché" variant="status">
                {marketStatusLabels[snapshot.marketStatus]}
              </TableCell>
              <TableCell label="Fournisseur">{snapshot.provider}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function SignalDetail({ signalId }: Readonly<{ signalId: string }>) {
  const encodedSignalId = encodeURIComponent(signalId);
  const opportunityQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseOpportunity>(`/api/v1/opportunities/${encodedSignalId}`, signal),
    queryKey: ["opportunity", signalId],
    staleTime: Infinity,
  });
  const explanationQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseOpportunityExplanation>(
        `/api/v1/opportunities/${encodedSignalId}/explanation`,
        signal,
      ),
    queryKey: ["opportunity-explanation", signalId],
    staleTime: Infinity,
  });
  const opportunity = opportunityQuery.data?.data;
  const eventId = opportunity ? opportunity.event.eventId : undefined;
  const historyQuery = useInfiniteQuery({
    enabled: eventId !== undefined,
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    placeholderData: keepPreviousData,
    queryFn: ({ signal, pageParam }) => {
      if (eventId === undefined) throw new Error("Événement du signal absent");
      return fetchResource<PageResponseOddsSnapshot>(
        `/api/v1/events/${encodeURIComponent(eventId)}/odds-history?offset=${String(pageParam)}&limit=100`,
        signal,
      );
    },
    queryKey: ["signal-odds-history", eventId],
    refetchInterval: ODDS_REFRESH_INTERVAL_MS,
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseOddsSnapshot,
  });

  const isPending = opportunityQuery.isPending;
  const isFetching =
    opportunityQuery.isFetching || explanationQuery.isFetching || historyQuery.isFetching;
  const referenceTime = opportunityQuery.data?.meta.computedAt ?? new Date(0).toISOString();
  const explanation = canReadPrevious(explanationQuery) ? explanationQuery.data?.data : undefined;
  const snapshots = canReadPrevious(historyQuery) ? (historyQuery.data?.data ?? []) : [];
  const matchingSnapshots = opportunity ? matchingOddsSnapshots(opportunity, snapshots) : [];
  const latestSnapshot = opportunity
    ? latestMatchingOddsSnapshot(opportunity, snapshots)
    : undefined;
  const updatedSnapshot = opportunity ? newerOddsSnapshot(opportunity, snapshots) : undefined;

  return (
    <div className="ui-page-stack">
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
        loadingFallback={<RemotePageLoadingState label="Chargement du signal" />}
      >
        <QueryRecovery queries={[opportunityQuery]} />
        {opportunityQuery.isError && !canReadPrevious(opportunityQuery) ? (
          <QueryFailure
            description="Le détail du signal n’a pas pu être assemblé."
            missingDescription="Ce signal n’est pas disponible dans le catalogue courant."
            missingTitle="Signal introuvable"
            queries={[opportunityQuery]}
          />
        ) : opportunity ? (
          <div className="grid min-w-0 gap-6">
            <header className="grid min-w-0 gap-5">
              <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="ui-eyebrow">Signal de pricing · {opportunity.event.competition}</p>
                  <h1 className="ui-page-title">
                    {opportunity.event.teamA} <span className="text-ink-secondary">vs</span>{" "}
                    {opportunity.event.teamB}
                  </h1>
                  <p className="mt-2 text-sm text-ink-secondary">
                    {opportunity.market.selectionLabel} · Vainqueur du match ·{" "}
                    {formatDateTime(opportunity.event.startsAt)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge className="border-border-subtle bg-accent-soft text-ink-primary">
                    {gradeLabels[opportunity.value.grade]}
                  </Badge>
                  <Badge className="border-border-strong bg-surface-muted text-ink-primary">
                    {freshnessLabels[opportunity.meta.freshness]}
                  </Badge>
                </div>
              </div>
              <MetricGrid className="border-y border-border-subtle py-3">
                <Metric label="Edge" value={formatSignedPercent(opportunity.value.edge)} />
                <Metric
                  label="EV prudente"
                  value={formatSignedPercent(opportunity.value.conservativeExpectedValue)}
                />
                <Metric
                  label="EV centrale"
                  value={formatSignedPercent(opportunity.value.expectedValue)}
                />
                <Metric
                  label="Version modèle"
                  value={<TechnicalText>{opportunity.model.modelVersion}</TechnicalText>}
                />
              </MetricGrid>
            </header>

            {opportunity.meta.freshness !== "fresh" ||
            opportunity.quality.sourceFreshness !== "fresh" ? (
              <RemoteStaleState
                description="Le signal reste consultable pour audit, mais aucune décision paper ne doit être prise sur ce snapshot."
                title="Signal ancien — décision bloquée"
              />
            ) : null}

            {updatedSnapshot ? (
              <ContextPanel aria-label="Cote mise à jour" role="status" tone="warning">
                <p className="font-semibold">Cote mise à jour</p>
                <p className="mt-1 text-sm leading-6">
                  Ce signal reste lié à la cote {formatDecimal(opportunity.book.decimalOdds)}{" "}
                  capturée le {formatDateTime(opportunity.book.capturedAt)}. La dernière cote
                  observée est {formatDecimal(updatedSnapshot.decimalOdds)}. Toute nouvelle décision
                  est portée par un nouveau signal ; cette fiche historique n’est jamais réécrite.
                </p>
              </ContextPanel>
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
                <MetricGrid>
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
                </MetricGrid>
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
                <MetricGrid>
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
                </MetricGrid>
                <p className="text-sm leading-6 text-ink-secondary">
                  {describeOpportunity(opportunity, referenceTime)}
                </p>
              </SectionCard>

              <SectionCard icon={<CircleAlert className="size-4.5" />} title="Raisons d’abstention">
                <QueryRecovery queries={[explanationQuery]} />
                {explanationQuery.isPending ? (
                  <RemoteLoadingState
                    label="Chargement de l’explication"
                    minHeight="5rem"
                    rows={2}
                  />
                ) : explanationQuery.isError && !canReadPrevious(explanationQuery) ? (
                  <QueryFailure
                    description="L’explication complémentaire n’a pas pu être chargée. Les raisons enregistrées dans le signal restent consultables."
                    missingDescription="L’explication complémentaire n’est pas disponible."
                    missingTitle="Explication indisponible"
                    queries={[explanationQuery]}
                  />
                ) : null}
                {opportunity.quality.abstentionReasons?.length ? (
                  <ul className="grid gap-2">
                    {formatAbstentionReasons(opportunity.quality.abstentionReasons).map(
                      (reason) => (
                        <li
                          className="rounded-lg border border-border-subtle bg-surface-muted px-3 py-2 text-sm"
                          key={reason}
                        >
                          {reason}
                        </li>
                      ),
                    )}
                  </ul>
                ) : (
                  <p className="text-sm text-ink-secondary">Aucune raison d’abstention.</p>
                )}
                <p className="text-xs text-ink-secondary">
                  <TechnicalText>
                    Référence d’explication : {explanation?.reference ?? "Non disponible"}
                  </TechnicalText>
                </p>
              </SectionCard>
            </div>

            <SectionCard
              icon={<Database className="size-4.5" />}
              title="Historique des prix observés"
            >
              <RemoteDataBoundary
                isLoading={historyQuery.isPending}
                loadingFallback={
                  <RemoteLoadingState
                    label="Chargement de l’historique des cotes"
                    minHeight="12rem"
                    rows={4}
                  />
                }
              >
                <QueryRecovery queries={[historyQuery]} />
                {historyQuery.isError && !canReadPrevious(historyQuery) ? (
                  <QueryFailure
                    description="L’historique des cotes n’a pas pu être chargé. La cote d’origine reste disponible dans le signal."
                    missingDescription="L’historique des cotes est indisponible."
                    missingTitle="Historique indisponible"
                    queries={[historyQuery]}
                  />
                ) : (
                  <>
                    <SnapshotHistory
                      latestSnapshotId={latestSnapshot?.oddsSnapshotId}
                      signalSnapshotId={opportunity.book.oddsSnapshotId}
                      snapshots={matchingSnapshots}
                    />
                    <PagedResults label="d’observations" query={historyQuery} />
                  </>
                )}
              </RemoteDataBoundary>
              <p className="text-xs leading-5 text-ink-secondary">
                Actualisation automatique toutes les 30 secondes. Le snapshot du signal reste
                consultable pendant le rafraîchissement.
              </p>
            </SectionCard>

            <SectionCard
              icon={<BookOpenCheck className="size-4.5" />}
              title="Règlement paper trading"
            >
              <MetricGrid>
                <Metric label="Marché" value="Vainqueur du match" />
                <Metric label="Sélection" value={opportunity.market.selectionLabel} />
                <Metric
                  label="Version des règles"
                  value={opportunity.market.settlementRulesVersion ?? "Non versionnée — bloqué"}
                />
              </MetricGrid>
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
              {!isAdmissible(opportunity, referenceTime) ? (
                <p className="text-sm text-ink-secondary">
                  {describeOpportunity(opportunity, referenceTime)}
                </p>
              ) : null}
            </SectionCard>
          </div>
        ) : (
          <RemoteRecoverableErrorState
            title="Signal indisponible"
            description="Aucune fiche n’a été renvoyée pour ce signal. Réessayez pour la récupérer."
            onRetry={() => void opportunityQuery.refetch()}
            retryDisabled={opportunityQuery.isFetching}
          />
        )}
      </RemoteDataBoundary>
    </div>
  );
}
