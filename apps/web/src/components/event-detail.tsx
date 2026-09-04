"use client";

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
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
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
import type { ReactNode } from "react";

import {
  describeOpportunity,
  formatDateTime,
  formatDecimal,
  formatPercent,
  formatSignedPercent,
  formatTimeUntil,
  freshnessLabels,
  isAdmissible,
} from "./opportunity-presenters";

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La ressource événement n’est pas disponible");
  return (await response.json()) as T;
}

function DetailCard({
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

export function OddsChart({ snapshots }: Readonly<{ snapshots: readonly OddsSnapshot[] }>) {
  const points = [...snapshots].sort((left, right) =>
    left.capturedAt.localeCompare(right.capturedAt),
  );
  if (points.length === 0) {
    return <p className="text-sm text-ink-secondary">Aucune cote observée pour cet événement.</p>;
  }

  const values = points.map((point) => Number(point.decimalOdds));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(maximum - minimum, 0.1);
  const chartPoints = values
    .map((value, index) => {
      const x = points.length === 1 ? 50 : (index / (points.length - 1)) * 100;
      const y = points.length === 1 ? 50 : 86 - ((value - minimum) / spread) * 72;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const first = values.at(0) ?? 0;
  const latest = values.at(-1) ?? first;
  const movement = latest - first;
  const summary = `${points.length.toString()} snapshot${points.length === 1 ? "" : "s"}. Cote de ${formatDecimal(first)} à ${formatDecimal(latest)}, minimum ${formatDecimal(minimum)}, maximum ${formatDecimal(maximum)}.`;

  return (
    <figure className="grid gap-3">
      <div className="h-48 overflow-hidden rounded-xl border border-border-subtle bg-surface-muted p-4">
        <svg
          aria-labelledby="odds-chart-title odds-chart-description"
          className="h-full w-full overflow-visible"
          preserveAspectRatio="none"
          role="img"
          viewBox="0 0 100 100"
        >
          <title id="odds-chart-title">Évolution de la cote observée</title>
          <desc id="odds-chart-description">{summary}</desc>
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
              <circle
                className="fill-accent stroke-surface-raised"
                cx={cx}
                cy={cy}
                key={`${point}-${index.toString()}`}
                r="2.2"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-secondary">
        <span>{summary}</span>
        <span className="font-semibold text-ink-primary">
          {movement === 0
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
      <ul aria-label="Marchés supportés" className="grid gap-2">
        {markets.map((market) => (
          <li
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface-muted px-4 py-3 text-sm"
            key={market.marketId}
          >
            <span>
              <strong>Vainqueur du match</strong> · {market.selectionLabel}
            </span>
            <Badge className="border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              <CheckCircle2 aria-hidden="true" className="mr-1 size-3.5" />
              Supporté · {market.status}
            </Badge>
          </li>
        ))}
      </ul>
      <p className="flex gap-2 rounded-lg border border-border-subtle px-4 py-3 text-xs leading-5 text-ink-secondary">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        Marchés de carte, totaux et handicaps non supportés : ils restent désactivés tant que leur
        capability gate n’est pas validé.
      </p>
    </div>
  );
}

export function EventDetail({ eventId }: Readonly<{ eventId: string }>) {
  const encodedEventId = encodeURIComponent(eventId);
  const eventQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseEvent>(`/api/v1/events/${encodedEventId}`, signal),
    queryKey: ["event", eventId],
  });
  const marketsQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<PageResponseMarket>(
        `/api/v1/events/${encodedEventId}/markets?offset=0&limit=100`,
        signal,
      ),
    queryKey: ["event-markets", eventId],
  });
  const oddsQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<PageResponseOddsSnapshot>(
        `/api/v1/events/${encodedEventId}/odds-history?offset=0&limit=100`,
        signal,
      ),
    queryKey: ["event-odds", eventId],
  });
  const opportunitiesQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<PageResponseOpportunity>("/api/v1/opportunities?offset=0&limit=100", signal),
    queryKey: ["opportunities", "event-detail"],
  });

  const isPending =
    eventQuery.isPending ||
    marketsQuery.isPending ||
    oddsQuery.isPending ||
    opportunitiesQuery.isPending;
  const isFetching =
    eventQuery.isFetching ||
    marketsQuery.isFetching ||
    oddsQuery.isFetching ||
    opportunitiesQuery.isFetching;
  const isError =
    eventQuery.isError || marketsQuery.isError || oddsQuery.isError || opportunitiesQuery.isError;
  const event = eventQuery.data?.data;
  const referenceTime = eventQuery.data?.meta.computedAt ?? new Date(0).toISOString();
  const signals =
    opportunitiesQuery.data?.data.filter((item) => item.event.eventId === eventId) ?? [];
  const signal: Opportunity | undefined = signals.at(0);
  const markets = marketsQuery.data?.data ?? [];
  const snapshots = oddsQuery.data?.data ?? [];
  const timeline: readonly (readonly [string, string])[] = signal
    ? [
        ["Cutoff de prédiction", signal.model.predictionCutoff],
        ["Prédiction calculée", signal.model.createdAt],
        ["Cote capturée", signal.book.capturedAt],
        ["Début annoncé", signal.event.startsAt],
      ]
    : [];

  return (
    <div className="grid min-w-0 gap-7">
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
        loadingFallback={<RemoteLoadingState label="Chargement de l’événement" rows={8} />}
      >
        {isError ? (
          <RemoteRecoverableErrorState
            description="La fiche complète n’a pas pu être assemblée."
            onRetry={() => {
              void Promise.all([
                eventQuery.refetch(),
                marketsQuery.refetch(),
                oddsQuery.refetch(),
                opportunitiesQuery.refetch(),
              ]);
            }}
          />
        ) : event ? (
          <div className="grid min-w-0 gap-6">
            <header className="grid gap-5 rounded-xl border border-border-subtle bg-surface-raised p-5 shadow-panel sm:p-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
                    {event.competition}
                  </p>
                  <h1 className="mt-2 text-title text-balance font-semibold tracking-tight">
                    {event.teamA} <span className="text-ink-secondary">vs</span> {event.teamB}
                  </h1>
                  <p className="mt-3 text-sm text-ink-secondary">
                    {formatDateTime(event.startsAt)} · Best of {event.bestOf.toString()} ·{" "}
                    {formatTimeUntil(event.startsAt, referenceTime)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge className="border-border-strong bg-surface-muted text-ink-primary">
                    {event.status === "scheduled" ? "Planifié" : event.status}
                  </Badge>
                  {signal ? (
                    <Badge className="border-accent bg-accent-soft text-ink-primary">
                      {freshnessLabels[signal.meta.freshness]}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Participants", `${event.teamA} · ${event.teamB}`],
                  ["Format", `Best of ${event.bestOf.toString()}`],
                  ["Marchés actifs", markets.length.toString()],
                  ["Snapshots de cote", snapshots.length.toString()],
                ].map(([label, value]) => (
                  <div className="rounded-lg bg-surface-muted px-4 py-3" key={label}>
                    <p className="text-xs text-ink-secondary">{label}</p>
                    <p className="mt-1 text-sm font-semibold">{value}</p>
                  </div>
                ))}
              </div>
            </header>

            <div className="grid min-w-0 gap-6 xl:grid-cols-[1.35fr_0.65fr]">
              <div className="grid min-w-0 gap-6">
                <DetailCard icon={<Activity className="size-4.5" />} title="Courbe des cotes">
                  <OddsChart snapshots={snapshots} />
                </DetailCard>

                <DetailCard icon={<ShieldCheck className="size-4.5" />} title="Prix et incertitude">
                  {signal ? (
                    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                      {[
                        [
                          "P. marché sans marge",
                          signal.book.noVigProbability
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
                        <div className="rounded-lg border border-border-subtle p-3" key={label}>
                          <dt className="text-xs text-ink-secondary">{label}</dt>
                          <dd className="mt-1 text-sm font-semibold">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="text-sm text-ink-secondary">
                      Aucun prix modèle pour cet événement.
                    </p>
                  )}
                </DetailCard>

                <DetailCard icon={<Database className="size-4.5" />} title="Marchés et capacité">
                  <MarketList markets={markets} />
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
                        {event.teamA} · {event.teamB}
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
                  <p className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs leading-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
                    <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                    Rosters individuels non fournis dans ce snapshot. Ils ne sont ni supposés ni
                    reconstruits.
                  </p>
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
                    <dl className="grid gap-3 break-all text-sm">
                      <div>
                        <dt className="text-xs text-ink-secondary">Version modèle</dt>
                        <dd className="mt-1 font-semibold">{signal.model.modelVersion}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Feature snapshot</dt>
                        <dd className="mt-1 font-mono text-xs">{signal.model.featureSnapshotId}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Snapshot de cote</dt>
                        <dd className="mt-1 font-mono text-xs">{signal.book.oddsSnapshotId}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-ink-secondary">Snapshot Oracle’s Elixir</dt>
                        <dd className="mt-1 font-semibold">
                          {signal.meta.dataMode === "mock"
                            ? "Non utilisé — mode mock"
                            : signal.book.provenanceReference}
                        </dd>
                      </div>
                    </dl>
                  ) : null}
                </DetailCard>
              </aside>
            </div>

            <DetailCard icon={<CalendarClock className="size-4.5" />} title="Timeline du signal">
              {signal ? (
                <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {timeline.map(([label, value], index) => (
                    <li className="relative rounded-lg border border-border-subtle p-4" key={label}>
                      <span className="text-xs font-semibold text-accent-strong">
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
              className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border-subtle bg-surface-raised p-5 shadow-panel sm:p-6"
            >
              <div>
                <h2 className="font-semibold">Paper trading uniquement</h2>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-ink-secondary">
                  {signal ? describeOpportunity(signal) : "Aucun signal disponible."} Aucune mise
                  réelle ni connexion bookmaker.
                </p>
              </div>
              {signal && isAdmissible(signal, referenceTime) ? (
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline">
                    <Link href={`/opportunities/${encodeURIComponent(signal.signalId)}`}>
                      Voir le signal
                    </Link>
                  </Button>
                  <Button asChild>
                    <Link href={`/paper-trading?signalId=${encodeURIComponent(signal.signalId)}`}>
                      Créer un paper bet
                    </Link>
                  </Button>
                </div>
              ) : (
                <Button disabled>Paper bet non admissible</Button>
              )}
            </section>
          </div>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
