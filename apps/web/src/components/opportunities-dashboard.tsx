"use client";

import type {
  FreshnessStatus,
  ListOpportunitiesApiV1OpportunitiesGetData,
  OddsSnapshot,
  Opportunity,
  PageResponseOddsSnapshot,
  PageResponseOpportunity,
  PageResponseProviderHealth,
  ProviderHealth,
  ValueGrade,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
  RemoteStaleState,
} from "@metiquo/ui";
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  CircleAlert,
  Clock3,
  LayoutGrid,
  Search,
  TableProperties,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode, SubmitEventHandler } from "react";
import { useMemo } from "react";

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
  type OpportunitySort,
} from "./opportunity-presenters";

const API_PROXY_BASE_URL = "/api/backend";

type Eligibility = "admissible" | "all";
type DisplayMode = "table" | "cards";
type OpportunityQuery = NonNullable<ListOpportunitiesApiV1OpportunitiesGetData["query"]>;

async function fetchContract<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_PROXY_BASE_URL}${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error("La requête métier a échoué");
  }
  return (await response.json()) as T;
}

function opportunityPath(query: OpportunityQuery) {
  const searchParameters = new URLSearchParams({
    limit: (query.limit ?? 100).toString(),
    offset: (query.offset ?? 0).toString(),
  });
  if (query.competition) searchParameters.set("competition", query.competition);
  if (query.team) searchParameters.set("team", query.team);
  if (query.grade) searchParameters.set("grade", query.grade);
  if (query.freshness) searchParameters.set("freshness", query.freshness);
  return `/api/v1/opportunities?${searchParameters.toString()}`;
}

function parseGrade(value: string | null): ValueGrade | undefined {
  switch (value) {
    case "BLOCKED":
    case "NO_EDGE":
    case "STRONG_VALUE":
    case "VALUE":
    case "WATCH":
      return value;
    default:
      return undefined;
  }
}

function parseFreshness(value: string | null): FreshnessStatus | undefined {
  switch (value) {
    case "degraded":
    case "failed":
    case "fresh":
    case "quarantined":
    case "stale":
      return value;
    default:
      return undefined;
  }
}

function searchHref(current: URLSearchParams, updates: Readonly<Record<string, string | null>>) {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  }
  const query = next.toString();
  return query ? `/?${query}` : "/";
}

function buildOpportunityQuery(searchParameters: URLSearchParams): OpportunityQuery {
  const query: OpportunityQuery = { limit: 100, offset: 0 };
  const competition = searchParameters.get("competition")?.trim();
  const team = searchParameters.get("team")?.trim();
  const grade = parseGrade(searchParameters.get("grade"));
  const freshness = parseFreshness(searchParameters.get("freshness"));

  if (competition) query.competition = competition;
  if (team) query.team = team;
  if (grade) query.grade = grade;
  if (freshness) query.freshness = freshness;
  return query;
}

function MetricCard({
  detail,
  icon,
  label,
  value,
}: Readonly<{ detail: string; icon: ReactNode; label: string; value: ReactNode }>) {
  return (
    <Card aria-label={label} className="overflow-hidden">
      <CardContent className="grid min-h-36 grid-cols-[1fr_auto] gap-4 p-5">
        <div className="grid content-between gap-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-secondary">
            {label}
          </p>
          <div>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            <p className="mt-1 text-xs leading-5 text-ink-secondary">{detail}</p>
          </div>
        </div>
        <span
          aria-hidden="true"
          className="grid size-10 place-items-center rounded-lg bg-surface-muted text-ink-secondary"
        >
          {icon}
        </span>
      </CardContent>
    </Card>
  );
}

function providerSummary(providers: readonly ProviderHealth[] | undefined) {
  if (!providers) {
    return { detail: "Vérification en cours", label: "Vérification", tone: "text-ink-secondary" };
  }
  if (providers.some((provider) => provider.status === "unavailable")) {
    return {
      detail: "Au moins une source indisponible",
      label: "Indisponible",
      tone: "text-red-700 dark:text-red-300",
    };
  }
  if (providers.some((provider) => provider.status === "degraded")) {
    return {
      detail: "Dernier snapshot valide conservé",
      label: "Dégradée",
      tone: "text-amber-700 dark:text-amber-300",
    };
  }
  return {
    detail: "Toutes les sources répondent",
    label: "Opérationnelle",
    tone: "text-emerald-700 dark:text-emerald-300",
  };
}

function GradeBadge({ grade }: Readonly<{ grade: ValueGrade }>) {
  const tone = {
    BLOCKED:
      "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
    NO_EDGE: "border-border-subtle bg-surface-muted text-ink-secondary",
    STRONG_VALUE:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
    VALUE:
      "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-200",
    WATCH:
      "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
  } satisfies Record<ValueGrade, string>;

  return <Badge className={tone[grade]}>{gradeLabels[grade]}</Badge>;
}

function FreshnessBadge({ freshness }: Readonly<{ freshness: FreshnessStatus }>) {
  const fresh = freshness === "fresh";
  return (
    <Badge
      className={
        fresh
          ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
          : "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
      }
    >
      {fresh ? (
        <CheckCircle2 aria-hidden="true" className="mr-1 size-3.5" />
      ) : (
        <CircleAlert aria-hidden="true" className="mr-1 size-3.5" />
      )}
      {freshnessLabels[freshness]}
    </Badge>
  );
}

function SignedMetric({ value }: Readonly<{ value: string }>) {
  const numericValue = Number(value);
  const positive = numericValue > 0;
  const negative = numericValue < 0;
  const Icon = positive ? ArrowUp : negative ? ArrowDown : ArrowRight;

  return (
    <span
      className={
        positive
          ? "inline-flex items-center gap-1 font-semibold text-emerald-700 dark:text-emerald-300"
          : negative
            ? "inline-flex items-center gap-1 font-semibold text-red-700 dark:text-red-300"
            : "inline-flex items-center gap-1 font-semibold text-ink-secondary"
      }
    >
      <Icon aria-hidden="true" className="size-3.5" />
      <span className="sr-only">{positive ? "Positif" : negative ? "Négatif" : "Neutre"} : </span>
      {formatSignedPercent(value)}
    </span>
  );
}

function oddsMovement(history: readonly OddsSnapshot[] | undefined) {
  if (!history) {
    return { label: "Vérification…", tone: "text-ink-secondary" };
  }
  const first = history.at(0);
  const latest = history.at(-1);
  if (!first || !latest) {
    return { label: "Indisponible", tone: "text-ink-secondary" };
  }
  const difference = Number(latest.decimalOdds) - Number(first.decimalOdds);
  if (Math.abs(difference) < 0.005) {
    return { label: "→ Stable", tone: "text-ink-secondary" };
  }
  if (difference > 0) {
    return {
      label: `↑ Hausse ${formatDecimal(Math.abs(difference))}`,
      tone: "text-emerald-700 dark:text-emerald-300",
    };
  }
  return {
    label: `↓ Baisse ${formatDecimal(Math.abs(difference))}`,
    tone: "text-red-700 dark:text-red-300",
  };
}

type OpportunityViewProperties = Readonly<{
  history: readonly OddsSnapshot[] | undefined;
  opportunity: Opportunity;
  referenceTime: string;
}>;

function OddsCell({
  history,
  opportunity,
}: Pick<OpportunityViewProperties, "history" | "opportunity">) {
  const latestOdds = history?.at(-1)?.decimalOdds ?? opportunity.book.decimalOdds;
  const movement = oddsMovement(history);

  return (
    <div className="grid gap-1">
      <span className="font-semibold tabular-nums">{formatDecimal(latestOdds)}</span>
      <span className={`text-[0.7rem] font-medium ${movement.tone}`}>{movement.label}</span>
    </div>
  );
}

function Explanation({ opportunity }: Readonly<{ opportunity: Opportunity }>) {
  return (
    <details className="group max-w-64 text-xs">
      <summary className="cursor-pointer rounded font-semibold text-accent-strong outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
        Explication
      </summary>
      <p className="mt-2 leading-5 text-ink-secondary">{describeOpportunity(opportunity)}</p>
    </details>
  );
}

function OpportunityTable({
  histories,
  opportunities,
  referenceTime,
}: Readonly<{
  histories: readonly (readonly OddsSnapshot[] | undefined)[];
  opportunities: readonly Opportunity[];
  referenceTime: string;
}>) {
  return (
    <div
      aria-label="Tableau des opportunités, défilement horizontal disponible"
      className="min-w-0 max-w-full overflow-x-auto rounded-xl border border-border-subtle bg-surface-raised shadow-panel outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      role="region"
      tabIndex={0}
    >
      <table className="w-full min-w-[92rem] border-collapse text-left text-xs">
        <caption className="sr-only">
          Opportunités classées selon l’EV prudente et leurs données de décision
        </caption>
        <thead className="border-b border-border-subtle bg-surface-muted text-ink-secondary">
          <tr>
            {[
              "Début",
              "Ligue",
              "Match",
              "Marché",
              "Sélection",
              "Cote",
              "Cote juste",
              "P. marché sans marge",
              "P. modèle",
              "Edge",
              "EV prudente",
              "Confiance",
              "Fraîcheur",
              "Détail",
            ].map((label) => (
              <th className="whitespace-nowrap px-3 py-3 font-semibold" key={label} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {opportunities.map((opportunity, index) => (
            <tr
              className="align-top transition-colors hover:bg-surface-muted/70"
              key={opportunity.signalId}
            >
              <td className="whitespace-nowrap px-3 py-4">
                <span className="block font-semibold">
                  {formatDateTime(opportunity.event.startsAt)}
                </span>
                <span className="mt-1 block text-ink-secondary">
                  {formatTimeUntil(opportunity.event.startsAt, referenceTime)}
                </span>
              </td>
              <td className="whitespace-nowrap px-3 py-4 text-ink-secondary">
                {opportunity.event.competition}
              </td>
              <td className="min-w-44 px-3 py-4 font-semibold">
                <Link
                  className="rounded underline decoration-border-strong underline-offset-4 outline-none hover:decoration-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  href={`/events/${encodeURIComponent(opportunity.event.eventId)}`}
                >
                  {opportunity.event.teamA}
                  <span className="mx-1.5 text-ink-secondary">vs</span>
                  {opportunity.event.teamB}
                </Link>
              </td>
              <td className="whitespace-nowrap px-3 py-4 text-ink-secondary">Vainqueur · Série</td>
              <td className="whitespace-nowrap px-3 py-4 font-medium">
                {opportunity.market.selectionLabel}
              </td>
              <td className="px-3 py-4">
                <OddsCell history={histories[index]} opportunity={opportunity} />
              </td>
              <td className="px-3 py-4 font-medium tabular-nums">
                {formatDecimal(opportunity.value.fairOdds)}
              </td>
              <td className="px-3 py-4 tabular-nums">
                {opportunity.book.noVigProbability === null
                  ? "Non calculée"
                  : formatPercent(opportunity.book.noVigProbability)}
              </td>
              <td className="px-3 py-4 tabular-nums">
                {formatPercent(opportunity.model.probability)}
              </td>
              <td className="px-3 py-4">
                <SignedMetric value={opportunity.value.edge} />
              </td>
              <td className="px-3 py-4">
                <div className="grid gap-2">
                  <SignedMetric value={opportunity.value.conservativeExpectedValue} />
                  <GradeBadge grade={opportunity.value.grade} />
                </div>
              </td>
              <td className="px-3 py-4 font-medium tabular-nums">
                {formatPercent(opportunity.model.confidence)}
              </td>
              <td className="px-3 py-4">
                <FreshnessBadge freshness={opportunity.meta.freshness} />
              </td>
              <td className="px-3 py-4">
                <div className="grid gap-3">
                  <Button asChild size="small" variant="outline">
                    <Link href={`/opportunities/${encodeURIComponent(opportunity.signalId)}`}>
                      Ouvrir le signal
                    </Link>
                  </Button>
                  <Explanation opportunity={opportunity} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DataPoint({ label, value }: Readonly<{ label: string; value: ReactNode }>) {
  return (
    <div className="grid gap-1">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className="m-0 text-sm font-semibold">{value}</dd>
    </div>
  );
}

function OpportunityCards({
  histories,
  opportunities,
  referenceTime,
}: Readonly<{
  histories: readonly (readonly OddsSnapshot[] | undefined)[];
  opportunities: readonly Opportunity[];
  referenceTime: string;
}>) {
  return (
    <div className="grid gap-4 xl:grid-cols-2" data-testid="opportunity-card-view">
      {opportunities.map((opportunity, index) => (
        <Card
          aria-label={`${opportunity.event.teamA} contre ${opportunity.event.teamB}`}
          key={opportunity.signalId}
        >
          <CardContent className="grid gap-5 p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-secondary">
                  {opportunity.event.competition}
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">
                  <Link
                    className="rounded underline decoration-border-strong underline-offset-4 outline-none hover:decoration-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                    href={`/events/${encodeURIComponent(opportunity.event.eventId)}`}
                  >
                    {opportunity.event.teamA} <span className="text-ink-secondary">vs</span>{" "}
                    {opportunity.event.teamB}
                  </Link>
                </h2>
                <p className="mt-1 text-xs text-ink-secondary">
                  {formatDateTime(opportunity.event.startsAt)} ·{" "}
                  {formatTimeUntil(opportunity.event.startsAt, referenceTime)}
                </p>
              </div>
              <GradeBadge grade={opportunity.value.grade} />
            </div>
            <dl className="grid grid-cols-2 gap-x-5 gap-y-4 border-y border-border-subtle py-4 sm:grid-cols-4">
              <DataPoint
                label="Cote"
                value={<OddsCell history={histories[index]} opportunity={opportunity} />}
              />
              <DataPoint label="Cote juste" value={formatDecimal(opportunity.value.fairOdds)} />
              <DataPoint
                label="P. marché sans marge"
                value={
                  opportunity.book.noVigProbability === null
                    ? "Non calculée"
                    : formatPercent(opportunity.book.noVigProbability)
                }
              />
              <DataPoint label="P. modèle" value={formatPercent(opportunity.model.probability)} />
              <DataPoint label="Edge" value={<SignedMetric value={opportunity.value.edge} />} />
              <DataPoint
                label="EV prudente"
                value={<SignedMetric value={opportunity.value.conservativeExpectedValue} />}
              />
              <DataPoint label="Confiance" value={formatPercent(opportunity.model.confidence)} />
              <DataPoint
                label="Fraîcheur"
                value={<FreshnessBadge freshness={opportunity.meta.freshness} />}
              />
            </dl>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-ink-secondary">
                Vainqueur du match · {opportunity.market.selectionLabel}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Button asChild size="small" variant="outline">
                  <Link href={`/opportunities/${encodeURIComponent(opportunity.signalId)}`}>
                    Ouvrir le signal
                  </Link>
                </Button>
                <Explanation opportunity={opportunity} />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function DashboardLoadingState() {
  return (
    <div className="grid gap-6">
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <RemoteLoadingState className="min-h-36" key={index} minHeight="9rem" rows={2} />
        ))}
      </div>
      <RemoteLoadingState minHeight="28rem" rows={8} />
    </div>
  );
}

export function OpportunitiesDashboard() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParameters = useSearchParams();
  const currentSearchParameters = useMemo(
    () => new URLSearchParams(searchParameters.toString()),
    [searchParameters],
  );
  const eligibility: Eligibility =
    searchParameters.get("eligibility") === "all" ? "all" : "admissible";
  const display: DisplayMode = searchParameters.get("display") === "cards" ? "cards" : "table";
  const sort: OpportunitySort =
    searchParameters.get("sort") === "start-asc" ? "start-asc" : "conservative-ev-desc";
  const query = useMemo(
    () => buildOpportunityQuery(currentSearchParameters),
    [currentSearchParameters],
  );

  const opportunitiesQuery = useQuery({
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => fetchContract<PageResponseOpportunity>(opportunityPath(query), signal),
    queryKey: ["opportunities", query],
  });
  const providersQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchContract<PageResponseProviderHealth>(
        "/api/v1/admin/data-sources?offset=0&limit=20",
        signal,
      ),
    queryKey: ["data-sources"],
  });

  const response = opportunitiesQuery.data;
  const referenceTime = response?.meta.computedAt ?? new Date(0).toISOString();
  const admissibleCount =
    response?.data.filter((opportunity) => isAdmissible(opportunity, referenceTime)).length ?? 0;
  const visibleOpportunities = useMemo(() => {
    if (!response) return [];
    const eligible =
      eligibility === "admissible"
        ? response.data.filter((opportunity) => isAdmissible(opportunity, referenceTime))
        : response.data;
    return sortOpportunities(eligible, sort);
  }, [eligibility, referenceTime, response, sort]);

  const historyQueries = useQueries({
    queries: visibleOpportunities.map((opportunity) => ({
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchContract<PageResponseOddsSnapshot>(
          `/api/v1/events/${encodeURIComponent(opportunity.event.eventId)}/odds-history?offset=0&limit=100`,
          signal,
        ),
      queryKey: ["odds-history", opportunity.event.eventId],
    })),
  });
  const histories = historyQueries.map((historyQuery) => historyQuery.data?.data);
  const historyRefreshing = historyQueries.some(
    (historyQuery) => historyQuery.isFetching && !historyQuery.isPending,
  );
  const sourceSummary = providerSummary(providersQuery.data?.data);
  const latestUpdate = response?.data.reduce<string | undefined>((latest, opportunity) => {
    if (!latest || opportunity.book.capturedAt > latest) return opportunity.book.capturedAt;
    return latest;
  }, undefined);
  const hasStaleData = visibleOpportunities.some(
    (opportunity) => opportunity.meta.freshness !== "fresh",
  );

  const applyFilters: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const next = new URLSearchParams(currentSearchParameters);
    for (const key of ["competition", "team", "grade", "freshness"] as const) {
      const entry = formData.get(key);
      const value = typeof entry === "string" ? entry.trim() : "";
      if (value) next.set(key, value);
      else next.delete(key);
    }
    const queryString = next.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  };

  return (
    <div className="grid min-w-0 gap-7">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div className="grid max-w-3xl gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
            Décisions pré-match
          </p>
          <h1 className="text-title text-balance font-semibold tracking-tight">Opportunités</h1>
          <p className="text-body max-w-2xl text-ink-secondary">
            Comparez le prix du marché au modèle avec une lecture prudente de l’incertitude. Analyse
            et paper trading uniquement.
          </p>
        </div>
        <Badge className="border-accent bg-accent-soft text-ink-primary">
          {sort === "start-asc" ? "Tri par heure de début" : "Tri par EV prudente"}
        </Badge>
      </header>

      <Card aria-labelledby="filters-title">
        <CardContent className="grid gap-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="font-semibold" id="filters-title">
                Filtres rapides
              </h2>
              <p className="mt-1 text-xs text-ink-secondary">
                Les critères actifs sont conservés dans l’URL pour partager cette vue.
              </p>
            </div>
            <div aria-label="Périmètre des signaux" className="flex gap-2" role="group">
              <Button
                asChild
                size="small"
                variant={eligibility === "admissible" ? "primary" : "outline"}
              >
                <Link
                  href={searchHref(currentSearchParameters, { eligibility: null })}
                  scroll={false}
                >
                  Admissibles
                </Link>
              </Button>
              <Button asChild size="small" variant={eligibility === "all" ? "primary" : "outline"}>
                <Link
                  href={searchHref(currentSearchParameters, { eligibility: "all" })}
                  scroll={false}
                >
                  Tous les signaux
                </Link>
              </Button>
            </div>
          </div>

          <form
            className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_0.9fr_0.9fr_auto_auto] xl:items-end"
            key={searchParameters.toString()}
            onSubmit={applyFilters}
          >
            <label className="grid gap-1.5 text-xs font-semibold" htmlFor="competition-filter">
              Ligue
              <input
                className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 text-sm font-normal outline-none placeholder:text-ink-secondary/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                defaultValue={searchParameters.get("competition") ?? ""}
                id="competition-filter"
                name="competition"
                placeholder="Ex. Ligue Démo 02"
              />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold" htmlFor="team-filter">
              Équipe
              <input
                className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 text-sm font-normal outline-none placeholder:text-ink-secondary/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                defaultValue={searchParameters.get("team") ?? ""}
                id="team-filter"
                name="team"
                placeholder="Ex. Aurore"
              />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold" htmlFor="grade-filter">
              Grade
              <select
                className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 text-sm font-normal outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                defaultValue={searchParameters.get("grade") ?? ""}
                id="grade-filter"
                name="grade"
              >
                <option value="">Tous</option>
                {Object.entries(gradeLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-xs font-semibold" htmlFor="freshness-filter">
              Fraîcheur
              <select
                className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 text-sm font-normal outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                defaultValue={searchParameters.get("freshness") ?? ""}
                id="freshness-filter"
                name="freshness"
              >
                <option value="">Toutes</option>
                {Object.entries(freshnessLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <Button className="w-full" type="submit">
              <Search aria-hidden="true" className="size-4" />
              Appliquer
            </Button>
            <Button asChild className="w-full" variant="ghost">
              <Link href="/" scroll={false}>
                Effacer
              </Link>
            </Button>
          </form>
        </CardContent>
      </Card>

      <RemoteDataBoundary
        className="min-w-0"
        isLoading={opportunitiesQuery.isPending}
        isRefetching={
          (opportunitiesQuery.isFetching && !opportunitiesQuery.isPending) || historyRefreshing
        }
        loadingFallback={<DashboardLoadingState />}
      >
        {opportunitiesQuery.isError ? (
          <RemoteRecoverableErrorState
            description="Les opportunités n’ont pas pu être chargées. Aucun détail technique sensible n’est affiché."
            onRetry={() => {
              void opportunitiesQuery.refetch();
            }}
          />
        ) : response ? (
          <div className="grid min-w-0 gap-6">
            <section aria-label="Résumé du dashboard" className="grid gap-4 md:grid-cols-3">
              <MetricCard
                detail={sourceSummary.detail}
                icon={
                  sourceSummary.label === "Opérationnelle" ? (
                    <CheckCircle2 className="size-5" />
                  ) : (
                    <CircleAlert className="size-5" />
                  )
                }
                label="Santé des sources"
                value={<span className={sourceSummary.tone}>{sourceSummary.label}</span>}
              />
              <MetricCard
                detail={`${response.page.total.toString()} signal${response.page.total === 1 ? " évalué" : "s évalués"}`}
                icon={<TableProperties className="size-5" />}
                label="Opportunités admissibles"
                value={admissibleCount}
              />
              <MetricCard
                detail={
                  latestUpdate ? `Snapshot ${formatDateTime(latestUpdate)}` : "Aucun snapshot"
                }
                icon={<Clock3 className="size-5" />}
                label="Dernière mise à jour"
                value={
                  latestUpdate
                    ? formatTimeUntil(latestUpdate, referenceTime).replace(
                        "Déjà commencé",
                        "À l’instant",
                      )
                    : "—"
                }
              />
            </section>

            {hasStaleData ? (
              <RemoteStaleState
                description="Le dernier snapshot valide reste visible, mais ces signaux ne sont pas admissibles tant que leur fraîcheur n’est pas rétablie."
                title="Données anciennes — décision bloquée"
              />
            ) : null}

            <section aria-labelledby="results-title" className="grid min-w-0 gap-4">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold tracking-tight" id="results-title">
                    {eligibility === "admissible" ? "Opportunités admissibles" : "Tous les signaux"}
                  </h2>
                  <p className="mt-1 text-xs text-ink-secondary">
                    {`${visibleOpportunities.length.toString()} résultat${visibleOpportunities.length === 1 ? "" : "s"}`}
                  </p>
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="grid gap-1.5 text-xs font-semibold" htmlFor="sort-order">
                    Trier par
                    <select
                      className="min-h-10 rounded-md border border-border-strong bg-surface-raised px-3 text-sm font-normal outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                      id="sort-order"
                      onChange={(event) => {
                        router.replace(
                          searchHref(currentSearchParameters, {
                            sort: event.target.value === "start-asc" ? "start-asc" : null,
                          }),
                          { scroll: false },
                        );
                      }}
                      value={sort}
                    >
                      <option value="conservative-ev-desc">EV prudente décroissante</option>
                      <option value="start-asc">Heure de début</option>
                    </select>
                  </label>
                  <div aria-label="Mode d’affichage" className="flex gap-1" role="group">
                    <Button
                      aria-label="Vue tableau"
                      asChild
                      size="icon"
                      variant={display === "table" ? "primary" : "outline"}
                    >
                      <Link
                        href={searchHref(currentSearchParameters, { display: null })}
                        scroll={false}
                      >
                        <TableProperties aria-hidden="true" className="size-4" />
                      </Link>
                    </Button>
                    <Button
                      aria-label="Vue cartes"
                      asChild
                      size="icon"
                      variant={display === "cards" ? "primary" : "outline"}
                    >
                      <Link
                        href={searchHref(currentSearchParameters, { display: "cards" })}
                        scroll={false}
                      >
                        <LayoutGrid aria-hidden="true" className="size-4" />
                      </Link>
                    </Button>
                  </div>
                </div>
              </div>

              {display === "table" && visibleOpportunities.length > 0 ? (
                <p className="text-xs text-ink-secondary xl:hidden">
                  Faites défiler le tableau horizontalement pour consulter toutes les mesures.
                </p>
              ) : null}

              {visibleOpportunities.length === 0 ? (
                <RemoteEmptyState
                  action={
                    <Button asChild size="small" variant="outline">
                      <Link href="/" scroll={false}>
                        Réinitialiser les filtres
                      </Link>
                    </Button>
                  }
                  description="Aucun signal ne satisfait à la fois les critères actifs et la politique d’admission prudente."
                  title="Aucune opportunité admissible"
                />
              ) : display === "cards" ? (
                <OpportunityCards
                  histories={histories}
                  opportunities={visibleOpportunities}
                  referenceTime={referenceTime}
                />
              ) : (
                <OpportunityTable
                  histories={histories}
                  opportunities={visibleOpportunities}
                  referenceTime={referenceTime}
                />
              )}
            </section>
          </div>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
