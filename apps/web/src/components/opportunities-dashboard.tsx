"use client";

import { QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend } from "../lib/backend";

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
  IconButton,
  Input,
  InlineValues,
  Metric,
  Select,
  ToggleGroup,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableCellContent,
  TableRow,
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
  ChevronDown,
  CircleAlert,
  Clock3,
  LayoutGrid,
  Search,
  SlidersHorizontal,
  TableProperties,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode, SubmitEventHandler } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { OddsObservation } from "./odds-observation";

const API_PROXY_BASE_URL = "/api/backend";
const ODDS_REFRESH_INTERVAL_MS = 30_000;
const SOURCE_REFRESH_INTERVAL_MS = 60_000;

type Eligibility = "admissible" | "all";
type DisplayMode = "table" | "cards";
type OpportunityQuery = NonNullable<ListOpportunitiesApiV1OpportunitiesGetData["query"]>;

async function fetchContract<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`${API_PROXY_BASE_URL}${path}`, {
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
  const offset = Number(searchParameters.get("offset") ?? 0);
  const query: OpportunityQuery = {
    limit: 100,
    offset: Number.isSafeInteger(offset) && offset >= 0 ? Math.floor(offset / 100) * 100 : 0,
  };
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
  mobileWide = false,
  value,
}: Readonly<{
  detail: string;
  icon: ReactNode;
  label: string;
  mobileWide?: boolean;
  value: ReactNode;
}>) {
  return (
    <Card
      aria-label={label}
      className={`max-md:rounded-none max-md:border-0 max-md:bg-transparent ${mobileWide ? "max-md:col-span-2" : ""}`}
    >
      <CardContent className="max-md:p-0">
        <div>
          <Metric
            className={
              mobileWide
                ? "max-md:py-0 max-md:[&_.ui-metric-definition]:grid-cols-[1fr_auto] max-md:[&_.ui-metric-definition]:items-baseline max-md:[&_.ui-metric-detail]:col-span-2"
                : "max-md:py-0"
            }
            emphasis="statistic"
            detail={detail}
            label={
              <span className="inline-flex items-center gap-2">
                <span aria-hidden="true" className="hidden md:inline [&_svg]:size-4">
                  {icon}
                </span>
                {label}
              </span>
            }
            value={value}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function providerSummary(providers: readonly ProviderHealth[] | undefined) {
  if (!providers) {
    return { detail: "Vérification en cours", label: "Vérification", tone: "text-ink-secondary" };
  }
  if (providers.length === 0) {
    return {
      detail: "Aucune source déclarée",
      label: "Non disponible",
      tone: "text-ink-secondary",
    };
  }
  if (providers.some((provider) => provider.status === "unavailable")) {
    return {
      detail: "Au moins une source indisponible",
      label: "Indisponible",
      tone: "text-red-700 dark:text-red-300",
    };
  }
  if (providers.every((provider) => provider.status === "disabled")) {
    return {
      detail: "Toutes les sources sont désactivées",
      label: "Désactivée",
      tone: "text-ink-secondary",
    };
  }
  if (providers.some((provider) => provider.status === "disabled")) {
    return {
      detail: "Au moins une source est désactivée",
      label: "Partielle",
      tone: "text-amber-700 dark:text-amber-300",
    };
  }
  if (
    providers.some(
      (provider) =>
        provider.status === "degraded" ||
        (provider.freshness != null && provider.freshness !== "fresh"),
    )
  ) {
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

function snapshotAge(capturedAt: string, referenceTime: string) {
  const age = Math.max(0, Math.floor((Date.parse(referenceTime) - Date.parse(capturedAt)) / 1000));
  if (!Number.isFinite(age)) return "Non disponible";
  if (age < 60) return "À l’instant";
  if (age < 3600) return `Il y a ${String(Math.floor(age / 60))} min`;
  if (age < 86400) return `Il y a ${String(Math.floor(age / 3600))} h`;
  return `Il y a ${String(Math.floor(age / 86400))} j`;
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
  const blocked = freshness === "failed" || freshness === "quarantined";
  return (
    <Badge
      className={
        fresh
          ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
          : blocked
            ? "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
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

function Explanation({
  opportunity,
  referenceTime,
}: Readonly<{ opportunity: Opportunity; referenceTime: string }>) {
  return (
    <details className="group max-w-64 text-xs">
      <summary className="cursor-pointer rounded font-semibold text-accent-strong outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
        Explication
      </summary>
      <p className="mt-2 leading-5 text-ink-secondary">
        {describeOpportunity(opportunity, referenceTime)}
      </p>
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
    <Table
      aria-label="Tableau des opportunités"
      columns={[
        { label: "Match", variant: "identity", weight: 2.4 },
        { label: "Marché", variant: "text", weight: 1.5 },
        { label: "Cote", variant: "detail", weight: 1.9 },
        { label: "P. marché sans marge", variant: "number", weight: 1 },
        { label: "Modèle", variant: "number", weight: 1.5 },
        { label: "EV prudente", variant: "number", weight: 1.2 },
        { label: "Fraîcheur", variant: "status", weight: 1.1 },
        { label: "Détail", variant: "action", weight: 1.4 },
      ]}
    >
      <TableBody>
        {opportunities.map((opportunity, index) => (
          <TableRow data-signal-id={opportunity.signalId} key={opportunity.signalId}>
            <TableCell label="Match" variant="identity">
              <TableCellContent
                primary={
                  <Link
                    className="rounded underline decoration-border-strong underline-offset-4 outline-none hover:decoration-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                    href={`/events/${encodeURIComponent(opportunity.event.eventId)}`}
                  >
                    <InlineValues
                      items={[opportunity.event.teamA, opportunity.event.teamB]}
                      separator="vs"
                    />
                  </Link>
                }
                secondary={
                  <>
                    <p>{opportunity.event.competition}</p>
                    <p>{formatDateTime(opportunity.event.startsAt)}</p>
                    <p>{formatTimeUntil(opportunity.event.startsAt, referenceTime)}</p>
                  </>
                }
              />
            </TableCell>
            <TableCell label="Marché">
              <TableCellContent
                primary={opportunity.market.selectionLabel}
                secondary="Vainqueur · Série"
              />
            </TableCell>
            <TableCell label="Cote" variant="detail">
              <OddsObservation history={histories[index]} opportunity={opportunity} />
            </TableCell>
            <TableCell label="P. marché sans marge" variant="number">
              {opportunity.book.noVigProbability === null
                ? "Non calculée"
                : formatPercent(opportunity.book.noVigProbability)}
            </TableCell>
            <TableCell label="Modèle" variant="number">
              <TableCellContent
                primary={<>P. modèle {formatPercent(opportunity.model.probability)}</>}
                secondary={
                  <>
                    <p>Cote juste {formatDecimal(opportunity.value.fairOdds)}</p>
                    <p>Confiance {formatPercent(opportunity.model.confidence)}</p>
                  </>
                }
              />
            </TableCell>
            <TableCell label="EV prudente" variant="number">
              <TableCellContent
                primary={<SignedMetric value={opportunity.value.conservativeExpectedValue} />}
                secondary={
                  <>
                    <p>
                      Edge <SignedMetric value={opportunity.value.edge} />
                    </p>
                    <GradeBadge grade={opportunity.value.grade} />
                  </>
                }
              />
            </TableCell>
            <TableCell label="Fraîcheur" variant="status">
              <FreshnessBadge freshness={opportunity.meta.freshness} />
            </TableCell>
            <TableCell label="Détail" variant="action">
              <div className="grid justify-items-start gap-2">
                <Button asChild size="small" variant="outline">
                  <Link href={`/opportunities/${encodeURIComponent(opportunity.signalId)}`}>
                    Ouvrir le signal
                  </Link>
                </Button>
                <Explanation opportunity={opportunity} referenceTime={referenceTime} />
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function DataPoint({ label, value }: Readonly<{ label: string; value: ReactNode }>) {
  return (
    <div className="grid min-w-0 gap-1 [overflow-wrap:anywhere]">
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
          data-signal-id={opportunity.signalId}
          key={opportunity.signalId}
        >
          <CardContent className="grid gap-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-secondary">
                  {opportunity.event.competition}
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">
                  <Link
                    className="rounded underline decoration-border-strong underline-offset-4 outline-none hover:decoration-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                    href={`/events/${encodeURIComponent(opportunity.event.eventId)}`}
                  >
                    <InlineValues
                      items={[opportunity.event.teamA, opportunity.event.teamB]}
                      separator="vs"
                    />
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
                value={<OddsObservation history={histories[index]} opportunity={opportunity} />}
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
                <Explanation opportunity={opportunity} referenceTime={referenceTime} />
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
  const filterForm = useRef<HTMLFormElement>(null);
  const pathname = usePathname();
  const router = useRouter();
  const searchParameters = useSearchParams();
  const [draftGrade, setDraftGrade] = useState(parseGrade(searchParameters.get("grade")) ?? "");
  const [draftFreshness, setDraftFreshness] = useState(
    parseFreshness(searchParameters.get("freshness")) ?? "",
  );
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
  const activeFilterCount = [query.competition, query.team, query.grade, query.freshness].filter(
    Boolean,
  ).length;
  const hasFilters = activeFilterCount > 0;
  const [filtersExpanded, setFiltersExpanded] = useState(hasFilters);
  const clearedFiltersHref = searchHref(currentSearchParameters, {
    competition: null,
    team: null,
    grade: null,
    freshness: null,
    offset: null,
  });

  const opportunitiesQuery = useQuery({
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => fetchContract<PageResponseOpportunity>(opportunityPath(query), signal),
    queryKey: ["opportunities", query],
    refetchInterval: ODDS_REFRESH_INTERVAL_MS,
  });
  const providersQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchContract<PageResponseProviderHealth>(
        "/api/v1/admin/data-sources?offset=0&limit=20",
        signal,
      ),
    queryKey: ["data-sources"],
    refetchInterval: SOURCE_REFRESH_INTERVAL_MS,
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
      placeholderData: keepPreviousData,
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchContract<PageResponseOddsSnapshot>(
          `/api/v1/events/${encodeURIComponent(opportunity.event.eventId)}/odds-history?offset=0&limit=100`,
          signal,
        ),
      queryKey: ["odds-history", opportunity.event.eventId],
      refetchInterval: ODDS_REFRESH_INTERVAL_MS,
    })),
  });
  const histories = historyQueries.map((historyQuery) =>
    historyQuery.isError && !canReadPrevious(historyQuery) ? [] : historyQuery.data?.data,
  );
  const historyErrors = historyQueries.filter((historyQuery) => historyQuery.isError);
  const historyRefreshing = historyQueries.some(
    (historyQuery) => historyQuery.isFetching && !historyQuery.isPending,
  );
  const sourceSummary = providersQuery.isError
    ? {
        detail: "Le contrôle des sources est indisponible",
        label: "À vérifier",
        tone: "text-amber-700 dark:text-amber-300",
      }
    : providerSummary(providersQuery.data?.data);
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
    next.delete("offset");
    for (const key of ["competition", "team", "grade", "freshness"] as const) {
      const entry = formData.get(key);
      const value = typeof entry === "string" ? entry.trim() : "";
      if (value) next.set(key, value);
      else next.delete(key);
    }
    const queryString = next.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  };

  useEffect(() => {
    // Follow shared URLs and browser history without unmounting the focused control.
    setDraftGrade(parseGrade(currentSearchParameters.get("grade")) ?? "");
    setDraftFreshness(parseFreshness(currentSearchParameters.get("freshness")) ?? "");
    for (const name of ["competition", "team"]) {
      const control = filterForm.current?.elements.namedItem(name);
      if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
        control.value = currentSearchParameters.get(name) ?? "";
      }
    }
  }, [currentSearchParameters]);

  useEffect(() => {
    // Shared filtered URLs reveal their controls on mobile as well as on desktop.
    if (hasFilters) setFiltersExpanded(true);
  }, [hasFilters]);

  return (
    <div className="ui-page-stack">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div className="grid max-w-3xl gap-2">
          <p className="ui-eyebrow">Décisions pré-match</p>
          <h1 className="ui-page-title">Opportunités</h1>
          <p className="text-body max-w-2xl text-ink-secondary">
            Comparez le prix du marché au modèle avec une lecture prudente de l’incertitude. Analyse
            et paper trading uniquement.
          </p>
        </div>
        <Badge className="hidden border-border-subtle bg-accent-soft text-ink-primary md:inline-flex">
          {sort === "start-asc" ? "Tri par heure de début" : "Tri par EV prudente"}
        </Badge>
      </header>

      <Card aria-labelledby="filters-title">
        <CardContent className="grid gap-4 max-md:p-3 md:gap-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="hidden md:block">
              <h2 className="font-semibold" id="filters-title">
                Filtres rapides
              </h2>
              <p className="mt-1 text-xs text-ink-secondary">
                Les critères actifs sont conservés dans l’URL pour partager cette vue.
              </p>
            </div>
            <Button
              aria-controls="opportunity-filter-fields"
              aria-expanded={filtersExpanded}
              className="w-full justify-between md:hidden"
              onClick={() => {
                setFiltersExpanded((expanded) => !expanded);
              }}
              variant="outline"
            >
              <span className="inline-flex items-center gap-2">
                <SlidersHorizontal aria-hidden="true" className="size-4" />
                Filtres{" "}
                <span className="text-xs">
                  ({activeFilterCount} actif{activeFilterCount === 1 ? "" : "s"})
                </span>
              </span>
              <ChevronDown
                aria-hidden="true"
                className={`size-4 ${filtersExpanded ? "rotate-180" : ""}`}
              />
            </Button>
            <div aria-label="Périmètre des signaux" className="flex flex-wrap gap-2" role="group">
              <Button
                asChild
                size="small"
                variant={eligibility === "admissible" ? "secondary" : "ghost"}
              >
                <Link
                  aria-current={eligibility === "admissible" ? "true" : undefined}
                  href={searchHref(currentSearchParameters, { eligibility: null, offset: null })}
                  scroll={false}
                >
                  Admissibles
                </Link>
              </Button>
              <Button asChild size="small" variant={eligibility === "all" ? "secondary" : "ghost"}>
                <Link
                  aria-current={eligibility === "all" ? "true" : undefined}
                  href={searchHref(currentSearchParameters, { eligibility: "all", offset: null })}
                  scroll={false}
                >
                  Tous les signaux
                </Link>
              </Button>
            </div>
          </div>

          <div
            id="opportunity-filter-fields"
            className={`${filtersExpanded ? "block" : "hidden"} md:block`}
          >
            <p className="mb-3 text-xs text-ink-secondary md:hidden" role="status">
              {hasFilters
                ? `${String(activeFilterCount)} filtre${activeFilterCount === 1 ? "" : "s"} appliqué${activeFilterCount === 1 ? "" : "s"}. Modifiez les critères puis appliquez les changements.`
                : "Aucun filtre appliqué. Choisissez vos critères puis appliquez-les."}
            </p>
            <form
              className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_0.9fr_0.9fr_auto_auto] xl:items-end"
              ref={filterForm}
              onSubmit={applyFilters}
            >
              <label className="ui-field" htmlFor="competition-filter">
                Ligue
                <Input
                  defaultValue={searchParameters.get("competition") ?? ""}
                  id="competition-filter"
                  name="competition"
                  placeholder="Ex. Ligue Démo 02"
                />
              </label>
              <label className="ui-field" htmlFor="team-filter">
                Équipe
                <Input
                  defaultValue={searchParameters.get("team") ?? ""}
                  id="team-filter"
                  name="team"
                  placeholder="Ex. Aurore"
                />
              </label>
              <label className="ui-field" htmlFor="grade-filter">
                Grade
                <Select
                  value={draftGrade}
                  onValueChange={setDraftGrade}
                  id="grade-filter"
                  name="grade"
                >
                  <option value="">Tous</option>
                  {Object.entries(gradeLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="ui-field" htmlFor="freshness-filter">
                Fraîcheur
                <Select
                  value={draftFreshness}
                  onValueChange={setDraftFreshness}
                  id="freshness-filter"
                  name="freshness"
                >
                  <option value="">Toutes</option>
                  {Object.entries(freshnessLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </label>
              <Button type="submit">
                <Search aria-hidden="true" className="size-4" />
                Appliquer
              </Button>
              <Button asChild variant="ghost">
                <Link href={clearedFiltersHref} scroll={false}>
                  Effacer
                </Link>
              </Button>
            </form>
          </div>
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
        <QueryRecovery queries={[opportunitiesQuery]} />
        {opportunitiesQuery.isError && !canReadPrevious(opportunitiesQuery) ? (
          <RemoteRecoverableErrorState
            description="Les opportunités n’ont pas pu être chargées. Réessayez pour retrouver vos résultats et vos filtres."
            onRetry={() => {
              void opportunitiesQuery.refetch();
            }}
            retryDisabled={opportunitiesQuery.isFetching}
          />
        ) : response ? (
          <div className="grid min-w-0 gap-6">
            <section
              aria-label="Résumé du dashboard"
              className="grid grid-cols-2 gap-x-4 gap-y-3 border-y border-border-subtle py-3 md:grid-cols-3 md:gap-4 md:border-0 md:p-0"
            >
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
                mobileWide
                value={<span className={sourceSummary.tone}>{sourceSummary.label}</span>}
              />
              <MetricCard
                detail={
                  response.page.total > response.data.length
                    ? `Sur cette page · ${String(response.data.length)} signaux évalués sur ${String(response.page.total)}`
                    : `${response.page.total.toString()} ${response.page.total === 1 ? "signal évalué" : "signaux évalués"}`
                }
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
                value={latestUpdate ? snapshotAge(latestUpdate, referenceTime) : "—"}
              />
            </section>

            <QueryRecovery queries={[providersQuery]} />
            {providersQuery.isError && !canReadPrevious(providersQuery) ? (
              <RemoteRecoverableErrorState
                compact
                title="Santé des sources indisponible"
                description="Le contrôle des sources n’a pas pu être chargé."
                onRetry={() => void providersQuery.refetch()}
                retryDisabled={providersQuery.isFetching}
              />
            ) : null}

            {hasStaleData ? (
              <RemoteStaleState
                description="Le dernier snapshot valide reste visible, mais ces signaux ne sont pas admissibles tant que leur fraîcheur n’est pas rétablie."
                title="Données anciennes — décision bloquée"
              />
            ) : null}
            {historyErrors.length > 0 ? (
              <RemoteRecoverableErrorState
                compact
                title="Historique des cotes indisponible"
                description="La cote du signal reste visible. Les dernières observations n’ont pas pu être vérifiées pour certains matchs."
                onRetry={() =>
                  void Promise.all(historyErrors.map((historyQuery) => historyQuery.refetch()))
                }
                retryDisabled={historyErrors.some((historyQuery) => historyQuery.isFetching)}
              />
            ) : null}

            <section aria-labelledby="results-title" className="grid min-w-0 gap-4">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="ui-section-title" id="results-title">
                    {eligibility === "admissible" ? "Opportunités admissibles" : "Tous les signaux"}
                  </h2>
                  <p
                    className="mt-1 text-xs text-ink-secondary"
                    role="status"
                    aria-label="Résultats des filtres"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    {`${visibleOpportunities.length.toString()} résultat${visibleOpportunities.length === 1 ? "" : "s"}`}
                    {response.page.total > 100 ? " sur cette page" : ""}
                  </p>
                  {response.page.total > 100 ? (
                    <p className="mt-1 text-xs leading-5 text-ink-secondary">
                      Le tri et l’admission s’appliquent aux signaux de la page affichée.
                    </p>
                  ) : null}
                </div>
                <div className="ui-toolbar">
                  <label className="ui-field" htmlFor="sort-order">
                    Trier par
                    <Select
                      id="sort-order"
                      onValueChange={(value) => {
                        router.replace(
                          searchHref(currentSearchParameters, {
                            sort: value === "start-asc" ? "start-asc" : null,
                          }),
                          { scroll: false },
                        );
                      }}
                      value={sort}
                    >
                      <option value="conservative-ev-desc">EV prudente décroissante</option>
                      <option value="start-asc">Heure de début</option>
                    </Select>
                  </label>
                  <ToggleGroup aria-label="Mode d’affichage">
                    <IconButton aria-label="Vue tableau" asChild active={display === "table"}>
                      <Link
                        aria-current={display === "table" ? "true" : undefined}
                        href={searchHref(currentSearchParameters, { display: null })}
                        scroll={false}
                      >
                        <TableProperties aria-hidden="true" className="size-4" />
                      </Link>
                    </IconButton>
                    <IconButton aria-label="Vue cartes" asChild active={display === "cards"}>
                      <Link
                        aria-current={display === "cards" ? "true" : undefined}
                        href={searchHref(currentSearchParameters, { display: "cards" })}
                        scroll={false}
                      >
                        <LayoutGrid aria-hidden="true" className="size-4" />
                      </Link>
                    </IconButton>
                  </ToggleGroup>
                </div>
              </div>

              {visibleOpportunities.length === 0 ? (
                <RemoteEmptyState
                  action={
                    <Button asChild size="small" variant="outline">
                      <Link
                        href={
                          (query.offset ?? 0) > 0
                            ? searchHref(currentSearchParameters, { offset: null })
                            : response.data.length > 0 && eligibility === "admissible"
                              ? searchHref(currentSearchParameters, { eligibility: "all" })
                              : hasFilters
                                ? clearedFiltersHref
                                : "/data"
                        }
                        scroll={false}
                      >
                        {(query.offset ?? 0) > 0
                          ? "Revenir à la première page"
                          : response.data.length > 0 && eligibility === "admissible"
                            ? "Voir les signaux écartés"
                            : hasFilters
                              ? "Réinitialiser les filtres"
                              : "Vérifier les sources de données"}
                      </Link>
                    </Button>
                  }
                  description={
                    response.data.length === 0 && (query.offset ?? 0) > 0
                      ? "Cette page ne contient aucun signal. Revenez à la première page en conservant vos filtres."
                      : response.data.length === 0 && !hasFilters
                        ? "Aucun signal n’a encore été calculé dans ce mode. Vérifiez les sources de données pour alimenter les opportunités."
                        : eligibility === "admissible"
                          ? "Aucun signal ne satisfait à la fois les critères actifs et la politique d’admission prudente."
                          : "Aucun signal ne correspond aux filtres sélectionnés."
                  }
                  title={
                    response.data.length === 0 && (query.offset ?? 0) > 0
                      ? "Aucun signal sur cette page"
                      : response.data.length === 0 && !hasFilters
                        ? "Aucun signal disponible"
                        : eligibility === "admissible"
                          ? "Aucune opportunité admissible"
                          : "Aucun signal"
                  }
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
              {response.page.total > 100 || (query.offset ?? 0) > 0 ? (
                <nav
                  aria-label="Pagination des opportunités"
                  className="flex flex-wrap items-center justify-between gap-3"
                >
                  <Button
                    disabled={(query.offset ?? 0) === 0 || opportunitiesQuery.isFetching}
                    onClick={() => {
                      router.replace(
                        searchHref(currentSearchParameters, {
                          offset:
                            (query.offset ?? 0) <= 100 ? null : String((query.offset ?? 0) - 100),
                        }),
                        { scroll: false },
                      );
                    }}
                    variant="outline"
                  >
                    Page précédente
                  </Button>
                  <p className="text-sm text-ink-secondary" role="status">
                    Page {Math.floor(response.page.offset / 100) + 1} sur{" "}
                    {Math.max(1, Math.ceil(response.page.total / 100))}
                  </p>
                  <Button
                    disabled={
                      (query.offset ?? 0) + 100 >= response.page.total ||
                      opportunitiesQuery.isFetching
                    }
                    onClick={() => {
                      router.replace(
                        searchHref(currentSearchParameters, {
                          offset: String((query.offset ?? 0) + 100),
                        }),
                        { scroll: false },
                      );
                    }}
                    variant="outline"
                  >
                    Page suivante
                  </Button>
                </nav>
              ) : null}
            </section>
          </div>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
