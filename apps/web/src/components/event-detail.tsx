"use client";

import { QueryFailure, QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend } from "../lib/backend";

import type {
  ItemResponseEvent,
  Market,
  OddsSnapshot,
  Opportunity,
  PageResponseMarket,
  PageResponseOddsSnapshot,
  PageResponseOpportunity,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  TitledCard as DetailCard,
  ContextPanel,
  InlineValues,
  Metric,
  MetricGrid,
  Select,
  RemoteDataBoundary,
  RemoteLoadingState,
  RemotePageLoadingState,
  RemoteRecoverableErrorState,
  TechnicalText,
} from "@metiquo/ui";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Database,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { nextPageOffset, PagedResults } from "./paged-results";

import {
  describeOpportunity,
  formatDateTime,
  formatDecimal,
  formatPercent,
  formatSignedPercent,
  formatTimeUntil,
  freshnessLabels,
  gradeLabels,
  isAdmissible,
  sortOpportunities,
} from "./opportunity-presenters";

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La ressource événement n’est pas disponible");
  return (await response.json()) as T;
}

export const marketStatusLabels: Readonly<Record<Market["status"], string>> = {
  open: "Ouvert",
  suspended: "Suspendu",
  settled: "Réglé",
  void: "Annulé",
};

export function OddsChart({ snapshots }: Readonly<{ snapshots: readonly OddsSnapshot[] }>) {
  const chartId = useId();
  const points = [...snapshots].sort(
    (left, right) => Date.parse(left.capturedAt) - Date.parse(right.capturedAt),
  );
  if (points.length === 0) {
    return <p className="text-sm text-ink-secondary">Aucune cote observée pour cet événement.</p>;
  }

  const values = points.map((point) => Number(point.decimalOdds));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(maximum - minimum, 0.1);
  const firstTime = Date.parse(points[0]?.capturedAt ?? "");
  const lastTime = Date.parse(points.at(-1)?.capturedAt ?? "");
  const duration = lastTime - firstTime;
  const chartPoints = values
    .map((value, index) => {
      const time = Date.parse(points[index]?.capturedAt ?? "");
      const x = duration > 0 ? 3 + ((time - firstTime) / duration) * 94 : 50;
      const y = maximum === minimum ? 50 : 86 - ((value - minimum) / spread) * 72;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const first = values.at(0) ?? 0;
  const latest = values.at(-1) ?? first;
  const movement = latest - first;
  const summary = `${points.length.toString()} snapshot${points.length === 1 ? "" : "s"}. Cote de ${formatDecimal(first)} à ${formatDecimal(latest)}, minimum ${formatDecimal(minimum)}, maximum ${formatDecimal(maximum)}.`;

  return (
    <figure className="grid gap-3">
      <div className="h-48 overflow-hidden py-3">
        <svg
          aria-describedby={`${chartId}-description`}
          aria-labelledby={`${chartId}-title`}
          className="h-full w-full overflow-visible"
          preserveAspectRatio="none"
          role="img"
          viewBox="0 0 100 100"
        >
          <title id={`${chartId}-title`}>Évolution de la cote observée</title>
          <desc id={`${chartId}-description`}>{summary}</desc>
          {[14, 50, 86].map((y) => (
            <line
              className="stroke-border-subtle"
              key={y}
              strokeWidth="0.6"
              vectorEffect="non-scaling-stroke"
              x1="0"
              x2="100"
              y1={y}
              y2={y}
            />
          ))}
          <polyline
            className="fill-none stroke-accent"
            points={chartPoints}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="3"
            vectorEffect="non-scaling-stroke"
          />
          {chartPoints.split(" ").map((point, index) => {
            const [cx = "0", cy = "0"] = point.split(",");
            return (
              <line
                className="stroke-accent"
                key={`${point}-${index.toString()}`}
                strokeLinecap="round"
                strokeWidth="6"
                vectorEffect="non-scaling-stroke"
                x1={cx}
                x2={cx}
                y1={cy}
                y2={cy}
              />
            );
          })}
        </svg>
      </div>
      <div className="flex flex-wrap justify-between gap-2 text-xs text-ink-secondary">
        <span>{formatDateTime(points[0]?.capturedAt ?? "")}</span>
        {points.length > 1 ? <span>{formatDateTime(points.at(-1)?.capturedAt ?? "")}</span> : null}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-secondary">
        <span>{summary}</span>
        <span className="font-semibold text-ink-primary">
          {points.length === 1
            ? "Comparaison indisponible · une seule observation"
            : movement === 0
              ? "→ Stable"
              : movement > 0
                ? `↑ Hausse ${formatDecimal(movement)}`
                : `↓ Baisse ${formatDecimal(Math.abs(movement))}`}
        </span>
      </figcaption>
    </figure>
  );
}

function MarketList({ markets }: Readonly<{ markets: readonly Market[] }>) {
  return (
    <div className="grid gap-3">
      <ul aria-label="Marchés supportés" className="grid divide-y divide-border-subtle">
        {markets.map((market) => (
          <li
            className="flex flex-wrap items-start justify-between gap-2 py-3 text-sm"
            key={market.marketId}
          >
            <span className="grid gap-1">
              <strong className="font-medium">{market.selectionLabel}</strong>
              <span className="text-xs text-ink-secondary">Vainqueur du match</span>
            </span>
            <Badge>
              <CheckCircle2 aria-hidden="true" className="mr-1 size-3.5" />
              Supporté · {marketStatusLabels[market.status]}
            </Badge>
          </li>
        ))}
      </ul>
      {markets.length === 0 ? (
        <p className="text-sm text-ink-secondary">Aucun marché disponible pour cet événement.</p>
      ) : null}
      <ContextPanel className="flex items-start gap-2">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        <p>
          Seul le vainqueur du match est disponible. Les marchés de carte, totaux et handicaps
          seront accessibles après validation de leurs données et règles de règlement.
        </p>
      </ContextPanel>
    </div>
  );
}

export function EventDetail({ eventId }: Readonly<{ eventId: string }>) {
  const [selectedSignalId, setSelectedSignalId] = useState("");
  const encodedEventId = encodeURIComponent(eventId);
  const eventQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseEvent>(`/api/v1/events/${encodedEventId}`, signal),
    queryKey: ["event", eventId],
  });
  const marketsQuery = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    queryFn: ({ signal, pageParam }) =>
      fetchResource<PageResponseMarket>(
        `/api/v1/events/${encodedEventId}/markets?offset=${String(pageParam)}&limit=100`,
        signal,
      ),
    queryKey: ["event-markets", eventId],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseMarket,
  });
  const oddsQuery = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    queryFn: ({ signal, pageParam }) =>
      fetchResource<PageResponseOddsSnapshot>(
        `/api/v1/events/${encodedEventId}/odds-history?offset=${String(pageParam)}&limit=100`,
        signal,
      ),
    queryKey: ["event-odds", eventId],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseOddsSnapshot,
  });
  const opportunitiesQuery = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    queryFn: ({ signal, pageParam }) =>
      fetchResource<PageResponseOpportunity>(
        `/api/v1/opportunities?eventId=${encodedEventId}&offset=${String(pageParam)}&limit=100`,
        signal,
      ),
    queryKey: ["opportunities", "event-detail", eventId, "pages"],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseOpportunity,
  });

  const isPending = eventQuery.isPending;
  const isFetching =
    eventQuery.isFetching ||
    marketsQuery.isFetching ||
    oddsQuery.isFetching ||
    opportunitiesQuery.isFetching;
  const event = eventQuery.data?.data;
  const referenceTime = eventQuery.data?.meta.computedAt ?? new Date(0).toISOString();
  const signals = sortOpportunities(
    canReadPrevious(opportunitiesQuery)
      ? (opportunitiesQuery.data?.data.filter((item) => item.event.eventId === eventId) ?? [])
      : [],
    "conservative-ev-desc",
  );
  const signal: Opportunity | undefined =
    signals.find((item) => item.signalId === selectedSignalId) ??
    signals.find((item) => isAdmissible(item, referenceTime)) ??
    signals.at(0);
  const markets = canReadPrevious(marketsQuery) ? (marketsQuery.data?.data ?? []) : [];
  const snapshots = canReadPrevious(oddsQuery) ? (oddsQuery.data?.data ?? []) : [];
  const chartReference = signal?.book ?? snapshots[0];
  const chartSnapshots = snapshots.filter(
    (snapshot) =>
      snapshot.marketId === chartReference?.marketId &&
      snapshot.selection === chartReference.selection,
  );
  const chartMarket = markets.find((market) => market.marketId === chartReference?.marketId);
  const timeline: readonly (readonly [string, string])[] = signal
    ? [
        ["Cutoff de prédiction", signal.model.predictionCutoff],
        ["Prédiction calculée", signal.model.createdAt],
        ["Cote capturée", signal.book.capturedAt],
        ["Début annoncé", signal.event.startsAt],
      ]
    : [];

  return (
    <div className="ui-page-stack">
      <div>
        <Button asChild size="small" variant="ghost">
          <Link href="/events">
            <ArrowLeft aria-hidden="true" className="size-4" />
            Retour aux événements
          </Link>
        </Button>
      </div>

      <RemoteDataBoundary
        className="min-w-0"
        isLoading={isPending}
        isRefetching={isFetching && !isPending}
        loadingFallback={<RemotePageLoadingState label="Chargement de l’événement" />}
      >
        <QueryRecovery queries={[eventQuery]} />
        {eventQuery.isError && !canReadPrevious(eventQuery) ? (
          <QueryFailure
            description="La fiche complète n’a pas pu être assemblée."
            missingDescription="Cet événement n’est pas disponible dans le catalogue courant."
            missingTitle="Événement introuvable"
            queries={[eventQuery]}
          />
        ) : event ? (
          <div className="grid min-w-0 gap-6">
            <header className="grid min-w-0 gap-5">
              <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-ink-secondary">{event.competition}</p>
                  <h1 className="ui-page-title">
                    {event.teamA} <span className="text-ink-secondary">vs</span> {event.teamB}
                  </h1>
                  <p className="mt-3 text-sm text-ink-secondary">
                    {formatDateTime(event.startsAt)} · Best of {event.bestOf.toString()} ·{" "}
                    {event.status === "scheduled"
                      ? formatTimeUntil(event.startsAt, referenceTime)
                      : { live: "En direct", finished: "Terminé", cancelled: "Annulé" }[
                          event.status
                        ]}
                  </p>
                </div>
                <div className="flex min-h-6 flex-wrap gap-2 sm:min-w-40 sm:justify-end">
                  <Badge className="border-border-strong bg-surface-muted text-ink-primary">
                    {
                      {
                        scheduled: "Planifié",
                        live: "En direct",
                        finished: "Terminé",
                        cancelled: "Annulé",
                      }[event.status]
                    }
                  </Badge>
                  {signal ? (
                    <Badge className="border-border-subtle bg-accent-soft text-ink-primary">
                      {freshnessLabels[signal.meta.freshness]}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <MetricGrid className="border-y border-border-subtle py-3">
                <Metric
                  label="Participants"
                  value={<InlineValues items={[event.teamA, event.teamB]} />}
                />
                <Metric label="Format" value={`Best of ${event.bestOf.toString()}`} />
                <Metric
                  label="Marchés actifs"
                  value={
                    marketsQuery.isPending
                      ? "Chargement…"
                      : !canReadPrevious(marketsQuery)
                        ? "Indisponible"
                        : markets.filter((market) => market.status === "open").length.toString()
                  }
                />
                <Metric
                  label="Observations chargées"
                  value={
                    oddsQuery.isPending
                      ? "Chargement…"
                      : !canReadPrevious(oddsQuery)
                        ? "Indisponible"
                        : snapshots.length.toString()
                  }
                />
              </MetricGrid>
            </header>

            <QueryRecovery queries={[opportunitiesQuery]} />
            {opportunitiesQuery.isError && !canReadPrevious(opportunitiesQuery) ? (
              <QueryFailure
                description="Les signaux associés ne répondent pas. L’événement, les marchés et les cotes restent consultables."
                missingDescription="Les signaux associés ne sont pas disponibles."
                missingTitle="Signaux indisponibles"
                queries={[opportunitiesQuery]}
              />
            ) : opportunitiesQuery.isPending || signals.length > 0 ? (
              <section
                aria-label="Signal analysé"
                aria-busy={opportunitiesQuery.isPending}
                className="grid gap-3"
              >
                <label className="ui-field max-w-2xl" htmlFor="event-signal-selection">
                  Signal analysé
                  <Select
                    id="event-signal-selection"
                    value={signal?.signalId ?? ""}
                    onValueChange={setSelectedSignalId}
                    disabled={opportunitiesQuery.isPending}
                  >
                    {opportunitiesQuery.isPending ? (
                      <option value="">Chargement des signaux…</option>
                    ) : (
                      signals.map((item) => (
                        <option key={item.signalId} value={item.signalId}>
                          {item.market.selectionLabel} · {gradeLabels[item.value.grade]} · cote{" "}
                          {formatDecimal(item.book.decimalOdds)} ·{" "}
                          {formatDateTime(item.book.capturedAt)}
                        </option>
                      ))
                    )}
                  </Select>
                </label>
                <p className="text-xs text-ink-secondary">
                  Les prix, facteurs, provenance et actions ci-dessous concernent ce signal.
                </p>
                <PagedResults label="de signaux" query={opportunitiesQuery} />
              </section>
            ) : null}

            <div className="grid min-w-0 gap-6 xl:grid-cols-[1.35fr_0.65fr]">
              <div className="grid min-w-0 gap-6">
                <DetailCard icon={<Activity className="size-4.5" />} title="Courbe des cotes">
                  <RemoteDataBoundary
                    isLoading={oddsQuery.isPending}
                    loadingFallback={
                      <RemoteLoadingState label="Chargement des cotes" minHeight="12rem" rows={4} />
                    }
                  >
                    <QueryRecovery queries={[oddsQuery]} />
                    {oddsQuery.isError && !canReadPrevious(oddsQuery) ? (
                      <QueryFailure
                        description="L’historique des cotes n’a pas pu être chargé."
                        missingDescription="L’historique des cotes est indisponible."
                        missingTitle="Historique indisponible"
                        queries={[oddsQuery]}
                      />
                    ) : (
                      <>
                        {chartReference ? (
                          <p className="text-sm text-ink-secondary">
                            Sélection : {chartMarket?.selectionLabel ?? chartReference.selection}
                          </p>
                        ) : null}
                        <OddsChart snapshots={chartSnapshots} />
                        <PagedResults label="d’observations" query={oddsQuery} />
                      </>
                    )}
                  </RemoteDataBoundary>
                </DetailCard>

                <DetailCard icon={<ShieldCheck className="size-4.5" />} title="Prix et incertitude">
                  {signal ? (
                    <MetricGrid>
                      {[
                        [
                          "P. marché sans marge",
                          signal.book.noVigProbability !== null
                            ? formatPercent(signal.book.noVigProbability)
                            : "Non calculée",
                        ],
                        ["P. modèle", formatPercent(signal.model.probability)],
                        [
                          "Intervalle modèle",
                          `${formatPercent(signal.model.probabilityLow)} – ${formatPercent(signal.model.probabilityHigh)}`,
                        ],
                        ["Cote observée", formatDecimal(signal.book.decimalOdds)],
                        ["Cote juste", formatDecimal(signal.value.fairOdds)],
                        [
                          "EV prudente",
                          formatSignedPercent(signal.value.conservativeExpectedValue),
                        ],
                      ].map(([label, value]) => (
                        <Metric key={label} label={label} value={value} />
                      ))}
                    </MetricGrid>
                  ) : (
                    <p className="text-sm text-ink-secondary">
                      Aucun prix modèle pour cet événement.
                    </p>
                  )}
                </DetailCard>

                <DetailCard icon={<Database className="size-4.5" />} title="Marchés et capacité">
                  <RemoteDataBoundary
                    isLoading={marketsQuery.isPending}
                    loadingFallback={
                      <RemoteLoadingState
                        label="Chargement des marchés"
                        minHeight="8rem"
                        rows={3}
                      />
                    }
                  >
                    <QueryRecovery queries={[marketsQuery]} />
                    {marketsQuery.isError && !canReadPrevious(marketsQuery) ? (
                      <QueryFailure
                        description="Les marchés n’ont pas pu être chargés."
                        missingDescription="Les marchés sont indisponibles."
                        missingTitle="Marchés indisponibles"
                        queries={[marketsQuery]}
                      />
                    ) : (
                      <>
                        <MarketList markets={markets} />
                        <PagedResults label="de marchés" query={marketsQuery} />
                      </>
                    )}
                  </RemoteDataBoundary>
                </DetailCard>
              </div>

              <aside aria-label="Contexte de décision" className="grid content-start gap-6">
                <DetailCard
                  icon={<Users className="size-4.5" />}
                  title="Participants et roster attendu"
                >
                  <dl className="grid gap-3 text-sm">
                    <div>
                      <dt className="text-xs text-ink-secondary">Participants canoniques</dt>
                      <dd className="mt-1 font-semibold">
                        <InlineValues items={[event.teamA, event.teamB]} />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-ink-secondary">Confiance du mapping</dt>
                      <dd className="mt-1 font-semibold">
                        {signal
                          ? formatPercent(signal.quality.mappingConfidence)
                          : "Non disponible"}
                      </dd>
                    </div>
                  </dl>
                  <ContextPanel className="flex gap-2" tone="warning">
                    <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                    <p>
                      Rosters individuels non fournis dans ce snapshot. Ils ne sont ni supposés ni
                      reconstruits.
                    </p>
                  </ContextPanel>
                </DetailCard>

                <DetailCard icon={<Activity className="size-4.5" />} title="Facteurs de décision">
                  {signal ? (
                    <dl className="grid gap-3 text-sm">
                      <div>
                        <dt className="text-xs text-ink-secondary">Couverture des données</dt>
                        <dd className="mt-1 font-semibold">
                          {formatPercent(signal.model.dataCoverage)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Distance hors distribution</dt>
                        <dd className="mt-1 font-semibold">
                          {formatDecimal(signal.model.outOfDistributionDistance)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">
                          Données manquantes / réduction de confiance
                        </dt>
                        <dd className="mt-1 font-semibold">
                          {(signal.model.confidenceReductionReasons ?? []).length
                            ? (signal.model.confidenceReductionReasons ?? []).join(" · ")
                            : "Aucune raison déclarée"}
                        </dd>
                      </div>
                    </dl>
                  ) : (
                    <p className="text-sm text-ink-secondary">Facteurs indisponibles.</p>
                  )}
                  <p className="text-xs leading-5 text-ink-secondary">
                    Ces indicateurs décrivent la décision ; ils ne démontrent pas de causalité.
                  </p>
                </DetailCard>

                <DetailCard icon={<Database className="size-4.5" />} title="Provenance">
                  {signal ? (
                    <dl className="grid min-w-0 gap-3 text-sm">
                      <div>
                        <dt className="text-xs text-ink-secondary">Version modèle</dt>
                        <dd className="mt-1">
                          <TechnicalText>{signal.model.modelVersion}</TechnicalText>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Feature snapshot</dt>
                        <dd className="mt-1">
                          <TechnicalText>{signal.model.featureSnapshotId}</TechnicalText>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Snapshot de cote</dt>
                        <dd className="mt-1">
                          <TechnicalText>{signal.book.oddsSnapshotId}</TechnicalText>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Snapshot Oracle’s Elixir</dt>
                        <dd className="mt-1 text-xs text-ink-secondary">
                          {signal.meta.dataMode === "mock" ? (
                            "Non utilisé — mode mock"
                          ) : (
                            <TechnicalText>{signal.book.provenanceReference}</TechnicalText>
                          )}
                        </dd>
                      </div>
                    </dl>
                  ) : (
                    <p className="text-sm text-ink-secondary">
                      Aucune provenance de signal disponible pour cet événement.
                    </p>
                  )}
                </DetailCard>
              </aside>
            </div>

            <DetailCard icon={<CalendarClock className="size-4.5" />} title="Timeline du signal">
              {signal ? (
                <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {timeline.map(([label, value], index) => (
                    <li className="min-w-0 border-t border-border-subtle py-3" key={label}>
                      <span className="text-xs font-medium text-ink-secondary">
                        Étape {(index + 1).toString()}
                      </span>
                      <p className="mt-2 text-sm font-semibold">{label}</p>
                      <time className="mt-1 block text-xs text-ink-secondary" dateTime={value}>
                        {formatDateTime(value)}
                      </time>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-ink-secondary">Aucun signal à retracer.</p>
              )}
            </DetailCard>

            <section
              aria-label="Action paper trading"
              className="flex flex-wrap items-center justify-between gap-4 border-t border-border-subtle pt-5"
            >
              <div>
                <h2 className="font-semibold">Paper trading uniquement</h2>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-ink-secondary">
                  {signal ? describeOpportunity(signal, referenceTime) : "Aucun signal disponible."}{" "}
                  Aucune mise réelle ni connexion bookmaker.
                </p>
              </div>
              {signal ? (
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline">
                    <Link href={`/opportunities/${encodeURIComponent(signal.signalId)}`}>
                      Voir le signal
                    </Link>
                  </Button>
                  {isAdmissible(signal, referenceTime) ? (
                    <Button asChild>
                      <Link href={`/paper-trading?signalId=${encodeURIComponent(signal.signalId)}`}>
                        Créer un paper bet
                      </Link>
                    </Button>
                  ) : (
                    <Button disabled>Paper bet non admissible</Button>
                  )}
                </div>
              ) : (
                <Button disabled>Paper bet non admissible</Button>
              )}
            </section>
          </div>
        ) : (
          <RemoteRecoverableErrorState
            title="Événement indisponible"
            description="Aucune fiche n’a été renvoyée pour cet événement. Réessayez pour la récupérer."
            onRetry={() => void eventQuery.refetch()}
            retryDisabled={eventQuery.isFetching}
          />
        )}
      </RemoteDataBoundary>
    </div>
  );
}
