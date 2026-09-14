"use client";

import { QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend, requestBackend } from "../lib/backend";

import type {
  AuditEntry,
  CapabilityEvaluationDto,
  DataQualityIssue,
  IngestionRunSummary,
  ItemResponseIngestionRunSummary,
  ItemResponseJobSummary,
  JobSummary,
  PageResponseAuditEntry,
  PageResponseCapabilityEvaluationDto,
  PageResponseDataQualityIssue,
  PageResponseIngestionRunSummary,
  PageResponseJobSummary,
  PageResponseProviderHealth,
  ProviderHealth,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  TitledCard as Panel,
  Metric,
  MetricGrid,
  ContextPanel,
  TechnicalText,
  StatusList,
  Table,
  TableBody,
  TableCell,
  TableCellContent,
  TableRow,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
  RemoteSkeleton,
} from "@metiquo/ui";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArchiveRestore,
  CalendarRange,
  CheckCircle2,
  CircleAlert,
  Database,
  FileClock,
  Fingerprint,
  ListChecks,
  Play,
  RefreshCw,
  Rows3,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { formatDateTime } from "./opportunity-presenters";
import { MappingReviewQueue } from "./mapping-review-queue";
import { OperationalStatusPanel } from "./operational-status-panel";
import { nextPageOffset, PagedResults } from "./paged-results";

const API_BASE = "/api/backend/api/v1/admin";

async function readResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`${API_BASE}${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La ressource d’administration ne répond pas");
  return (await response.json()) as T;
}

interface AdminPage {
  data: unknown[];
  page: { total: number; offset: number };
}

function usePagedAdminResource<T extends AdminPage>(
  resource: string,
  refreshInterval?: (pages: readonly T[]) => number | false,
) {
  return useInfiniteQuery({
    queryKey: ["admin", resource],
    initialPageParam: 0,
    queryFn: ({ signal, pageParam }) =>
      readResource<T>(`/${resource}?offset=${String(pageParam)}&limit=100`, signal),
    getNextPageParam: nextPageOffset,
    select: ({ pages }) => ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as T,
    refetchInterval: (query) =>
      canReadPrevious({ data: query.state.data, error: query.state.error })
        ? (refreshInterval?.(query.state.data?.pages ?? []) ?? false)
        : false,
  });
}

async function startSync(
  key: string,
): Promise<ItemResponseIngestionRunSummary | ItemResponseJobSummary> {
  const response = await requestBackend(`${API_BASE}/oracles-elixir/sync`, {
    headers: {
      accept: "application/json",
      "Idempotency-Key": key,
      "X-Metiquo-CSRF": "1",
    },
    method: "POST",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? "La synchronisation n’a pas pu démarrer");
  }
  return (await response.json()) as ItemResponseIngestionRunSummary | ItemResponseJobSummary;
}

function statusTone(status: string) {
  if (
    status === "succeeded" ||
    status === "fresh" ||
    status === "enabled" ||
    status === "operational"
  ) {
    return "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (
    status === "failed" ||
    status === "dead" ||
    status === "unavailable" ||
    status === "blocking" ||
    status === "quarantined" ||
    status === "disabled"
  ) {
    return "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200";
  }
  if (
    status === "degraded" ||
    status === "stale" ||
    status === "warning" ||
    status === "pending" ||
    status === "queued" ||
    status === "running"
  ) {
    return "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200";
  }
  return "border-border-strong bg-surface-muted text-ink-secondary";
}

function StatusBadge({ status }: Readonly<{ status: string }>) {
  return <Badge className={statusTone(status)}>{status}</Badge>;
}

function Stat({
  icon,
  label,
  value,
}: Readonly<{ icon: ReactNode; label: string; value: ReactNode }>) {
  return (
    <Metric
      label={
        <span className="flex items-center gap-2">
          <span aria-hidden="true">{icon}</span>
          {label}
        </span>
      }
      value={value}
    />
  );
}

function formatAge(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "Inconnu";
  if (seconds < 60) return `${String(seconds)} s`;
  if (seconds < 3_600) return `${String(Math.floor(seconds / 60))} min`;
  if (seconds < 86_400) return `${String(Math.floor(seconds / 3_600))} h`;
  return `${String(Math.floor(seconds / 86_400))} j`;
}

function SourceCatalogue({ source }: Readonly<{ source: ProviderHealth }>) {
  return (
    <div className="grid min-w-0 gap-4 [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{source.providerCode}</p>
          <p className="mt-1 text-xs text-ink-secondary">
            Contrôle : {formatDateTime(source.checkedAt)}
          </p>
        </div>
        <StatusBadge status={source.status} />
      </div>
      {source.status === "degraded" || source.status === "unavailable" ? (
        <ContextPanel tone={source.status === "unavailable" ? "danger" : "warning"} role="status">
          <p className="font-semibold">
            {source.status === "unavailable"
              ? "Source indisponible"
              : "Erreur récupérable · dernier snapshot conservé"}
          </p>
          <p>{source.detail}</p>
        </ContextPanel>
      ) : null}
      <MetricGrid>
        <Stat
          icon={<CheckCircle2 className="size-4" />}
          label="Dernier succès"
          value={source.lastSuccessAt ? formatDateTime(source.lastSuccessAt) : "Aucun"}
        />
        <Stat
          icon={<FileClock className="size-4" />}
          label="Dernière capture"
          value={source.lastCaptureAt ? formatDateTime(source.lastCaptureAt) : "Aucune"}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Âge de la capture"
          value={formatAge(source.ageSeconds)}
        />
        <Stat
          icon={<CircleAlert className="size-4" />}
          label="Échecs observés"
          value={source.failureCount === undefined ? "Non mesurés" : source.failureCount.toString()}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Fraîcheur source"
          value={source.freshness ?? "Non mesurée"}
        />
      </MetricGrid>
    </div>
  );
}

function SourceCatalogueLoading() {
  return (
    <div
      aria-busy="true"
      aria-label="Chargement du catalogue des sources"
      className="grid gap-4"
      data-remote-state="loading"
      role="status"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <RemoteSkeleton height="1.5rem" width="8rem" />
          <RemoteSkeleton height="1rem" width="12rem" />
        </div>
        <RemoteSkeleton height="1.375rem" width="4.5rem" />
      </div>
      <ContextPanel>
        <RemoteSkeleton height="1.25rem" width="80%" />
        <RemoteSkeleton height="1.25rem" />
        <div className="grid gap-2 sm:hidden">
          <RemoteSkeleton height="1.25rem" width="90%" />
          <RemoteSkeleton height="1.25rem" width="65%" />
        </div>
      </ContextPanel>
      <MetricGrid>
        <Stat
          icon={<CheckCircle2 className="size-4" />}
          label="Dernier succès"
          value={<RemoteSkeleton height="1.40625rem" width="8rem" />}
        />
        <Stat
          icon={<FileClock className="size-4" />}
          label="Dernière capture"
          value={<RemoteSkeleton height="1.40625rem" width="8rem" />}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Âge de la capture"
          value={<RemoteSkeleton height="1.40625rem" width="4rem" />}
        />
        <Stat
          icon={<CircleAlert className="size-4" />}
          label="Échecs observés"
          value={<RemoteSkeleton height="1.40625rem" width="3rem" />}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Fraîcheur source"
          value={<RemoteSkeleton height="1.40625rem" width="6rem" />}
        />
      </MetricGrid>
    </div>
  );
}

function SnapshotOverview({ runs }: Readonly<{ runs: readonly IngestionRunSummary[] }>) {
  const orderedRuns = runs.toSorted((left, right) => right.startedAt.localeCompare(left.startedAt));
  const lastAttempt = orderedRuns[0];
  const lastSuccess = orderedRuns.find((run) => run.status === "succeeded");
  const activeSnapshot = orderedRuns.find((run) => run.lastValidSnapshotId)?.lastValidSnapshotId;
  const years = [
    ...new Set(runs.flatMap((run) => (run.seasonYear == null ? [] : [run.seasonYear]))),
  ].sort((left, right) => right - left);

  return (
    <div className="grid gap-4">
      <MetricGrid>
        <Stat
          icon={<FileClock className="size-4" />}
          label="Dernière tentative"
          value={lastAttempt ? formatDateTime(lastAttempt.startedAt) : "Aucune"}
        />
        <Stat
          icon={<CheckCircle2 className="size-4" />}
          label="Dernier succès"
          value={lastSuccess ? formatDateTime(lastSuccess.completedAt) : "Aucun"}
        />
        <Stat
          icon={<Rows3 className="size-4" />}
          label="Lignes validées"
          value={lastSuccess?.rowCount.toString() ?? "Aucun succès validé"}
        />
        <Stat
          icon={<Fingerprint className="size-4" />}
          label="Snapshot actif"
          value={activeSnapshot ? <TechnicalText>{activeSnapshot}</TechnicalText> : "Non exposé"}
        />
        <Stat
          icon={<CalendarRange className="size-4" />}
          label="Saisons renseignées"
          value={years.length > 0 ? years.join(", ") : "Non exposée"}
        />
        <Stat
          icon={<ArchiveRestore className="size-4" />}
          label="Hash actif"
          value={
            lastSuccess?.snapshotSha256 ? (
              <TechnicalText>{lastSuccess.snapshotSha256}</TechnicalText>
            ) : (
              "Non exposé dans ce mode"
            )
          }
        />
      </MetricGrid>
      <div className="grid min-w-0 gap-2 border-t border-border-subtle pt-3 text-sm leading-6 [overflow-wrap:anywhere]">
        <p>
          <strong>Plage de dates métier :</strong>{" "}
          {lastSuccess?.minEventDate && lastSuccess.maxEventDate
            ? `${formatDateTime(lastSuccess.minEventDate)} → ${formatDateTime(lastSuccess.maxEventDate)}`
            : "non exposée dans ce mode"}
        </p>
        <p>
          <strong>Schéma :</strong>{" "}
          {lastSuccess?.schemaFingerprint
            ? `${lastSuccess.schemaFingerprint} · ${lastSuccess.schemaChanged ? "changement détecté" : "stable"}`
            : "non exposé dans ce mode"}
        </p>
      </div>
    </div>
  );
}

function IngestionHistory({ runs }: Readonly<{ runs: readonly IngestionRunSummary[] }>) {
  return (
    <Table
      aria-label="Historique des synchronisations"
      columns={[
        { label: "Source", variant: "text" },
        { label: "Statut", variant: "status" },
        { label: "Début", variant: "date" },
        { label: "Fin", variant: "date" },
        { label: "Lignes", variant: "number" },
        { label: "Dernier snapshot valide", variant: "technical" },
      ]}
    >
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.runId}>
            <TableCell label="Source">{run.source}</TableCell>
            <TableCell label="Statut" variant="status">
              <StatusBadge status={run.status} />
            </TableCell>
            <TableCell label="Début" variant="date">
              {formatDateTime(run.startedAt)}
            </TableCell>
            <TableCell label="Fin" variant="date">
              {formatDateTime(run.completedAt)}
            </TableCell>
            <TableCell label="Lignes" variant="number">
              {run.rowCount}
            </TableCell>
            <TableCell label="Dernier snapshot valide" variant="technical">
              {run.lastValidSnapshotId ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function QualityList({ issues }: Readonly<{ issues: readonly DataQualityIssue[] }>) {
  return (
    <div className="grid gap-3">
      {issues.map((issue) => (
        <article
          className="grid min-w-0 gap-2 rounded-lg border border-border-subtle p-4 [overflow-wrap:anywhere] sm:grid-cols-[minmax(0,1fr)_auto]"
          key={issue.issueId}
        >
          <div>
            <p className="font-semibold">{issue.code}</p>
            <p className="mt-1 text-sm leading-6 text-ink-secondary">{issue.detail}</p>
            <p className="mt-2 text-xs text-ink-secondary">
              {issue.source} · {formatDateTime(issue.observedAt)}
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-2">
            <StatusBadge status={issue.severity} />
            <StatusBadge status={issue.status} />
          </div>
        </article>
      ))}
    </div>
  );
}

function CapabilityMatrix({ values }: Readonly<{ values: readonly CapabilityEvaluationDto[] }>) {
  return (
    <Table
      aria-label="Matrice des capacités"
      columns={[
        { label: "Capacité", variant: "technical", weight: 1.8 },
        { label: "État", variant: "status" },
        { label: "Gates", variant: "detail", weight: 2.8 },
        { label: "Complétude", variant: "number", weight: 1 },
        { label: "Échantillon", variant: "number", weight: 1 },
        { label: "Seuils", variant: "technical", weight: 1.8 },
        { label: "Raisons", variant: "technical", weight: 1.7 },
      ]}
    >
      <TableBody>
        {values.map((value) => (
          <TableRow key={`${value.snapshotId}:${value.capability}:${value.thresholdVersion}`}>
            <TableCell label="Capacité" variant="technical">
              <TableCellContent
                primary={value.capability}
                secondary={
                  <>
                    {value.kind} · révision {value.evaluationRevision}
                  </>
                }
              />
            </TableCell>
            <TableCell label="État" variant="status">
              <StatusBadge status={value.status} />
            </TableCell>
            <TableCell label="Gates" variant="detail">
              <StatusList
                aria-label="Détail des gates"
                items={Object.entries(value.gates).map(([gate, state]) => ({
                  label: gate,
                  value: state === true ? "ok" : state === false ? "non" : "attente",
                  tone: state === true ? "success" : state === false ? "danger" : "warning",
                }))}
              />
            </TableCell>
            <TableCell label="Complétude" variant="number">
              {(Number(value.observedCompleteness) * 100).toFixed(1)} % /{" "}
              {(Number(value.minimumCompleteness) * 100).toFixed(1)} %
            </TableCell>
            <TableCell label="Échantillon" variant="number">
              {value.observedSampleSize} / {value.minimumSampleSize}
            </TableCell>
            <TableCell label="Seuils" variant="technical">
              <TableCellContent
                primary={value.thresholdVersion}
                secondary={<>snapshot {value.snapshotId}</>}
              />
            </TableCell>
            <TableCell label="Raisons" variant="technical">
              {value.reasonCodes.length > 0 ? value.reasonCodes.join(" · ") : "Aucun blocage"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function PageHeader({ description, eyebrow, title }: Readonly<Record<string, string>>) {
  return (
    <header className="grid gap-3">
      <p className="ui-eyebrow">{eyebrow}</p>
      <h1 className="ui-page-title">{title}</h1>
      <p className="max-w-3xl text-sm leading-6 text-ink-secondary sm:text-base">{description}</p>
    </header>
  );
}

export function DataHealthDashboard() {
  const sources = usePagedAdminResource<PageResponseProviderHealth>("data-sources");
  const runs = usePagedAdminResource<PageResponseIngestionRunSummary>("ingestion-runs");
  const issues = usePagedAdminResource<PageResponseDataQualityIssue>("quality-issues");
  const capabilities = usePagedAdminResource<PageResponseCapabilityEvaluationDto>("capabilities");
  const quarantined = issues.data?.data.filter((issue) => issue.status === "quarantined") ?? [];

  return (
    <div className="ui-page-stack">
      <PageHeader
        description="Catalogue de provenance, snapshots validés, fraîcheur et anomalies. Les champs absents du mode courant sont signalés au lieu d’être déduits."
        eyebrow="Provenance & qualité"
        title="Santé des données"
      />

      <Panel icon={<Database className="size-5" />} title="Catalogue des sources">
        <QueryRecovery queries={[sources]} />
        {sources.isError && !canReadPrevious(sources) ? (
          <RemoteRecoverableErrorState
            description="Le catalogue primaire ne répond pas. Réessayez pour lire le dernier état validé."
            title="Catalogue indisponible"
            onRetry={() => void sources.refetch()}
            retryDisabled={sources.isFetching}
          />
        ) : (
          <RemoteDataBoundary
            className="min-w-0"
            isLoading={sources.isPending}
            isRefetching={sources.isFetching && !sources.isPending}
            loadingFallback={<SourceCatalogueLoading />}
          >
            {sources.data?.data.length ? (
              <div className="grid gap-6 divide-y divide-border-subtle [&>div+div]:pt-6">
                {sources.data.data.map((source) => (
                  <SourceCatalogue key={source.providerCode} source={source} />
                ))}
              </div>
            ) : (
              <RemoteEmptyState description="Aucune source n’est déclarée dans ce mode." />
            )}
          </RemoteDataBoundary>
        )}
        <PagedResults label="de sources" query={sources} />
      </Panel>

      <Panel icon={<Fingerprint className="size-5" />} title="Snapshot et couverture">
        <QueryRecovery queries={[runs]} />
        {runs.isError && !canReadPrevious(runs) ? (
          <RemoteRecoverableErrorState
            onRetry={() => void runs.refetch()}
            retryDisabled={runs.isFetching}
            title="Historique indisponible"
          />
        ) : (
          <RemoteDataBoundary
            isLoading={runs.isPending}
            isRefetching={runs.isFetching && !runs.isPending}
          >
            <SnapshotOverview runs={runs.data?.data ?? []} />
            {runs.hasNextPage ? (
              <p className="mt-3 text-xs text-ink-secondary">
                La couverture porte sur les tentatives chargées. Consultez la suite de l’historique
                pour compléter ce résumé.
              </p>
            ) : null}
          </RemoteDataBoundary>
        )}
      </Panel>

      <Panel icon={<FileClock className="size-5" />} title="Tentatives d’ingestion">
        <QueryRecovery queries={[runs]} />
        {runs.isError && !canReadPrevious(runs) ? (
          <RemoteRecoverableErrorState
            onRetry={() => void runs.refetch()}
            retryDisabled={runs.isFetching}
          />
        ) : runs.isPending ? (
          <RemoteLoadingState label="Chargement des tentatives d’ingestion" rows={4} />
        ) : runs.data?.data.length ? (
          <IngestionHistory runs={runs.data.data} />
        ) : (
          <RemoteEmptyState description="Aucune synchronisation n’a encore été enregistrée." />
        )}
        <PagedResults label="de tentatives" query={runs} />
      </Panel>

      <Panel icon={<ListChecks className="size-5" />} title="Capacités par snapshot">
        <QueryRecovery queries={[capabilities]} />
        {capabilities.isError && !canReadPrevious(capabilities) ? (
          <RemoteRecoverableErrorState
            description="Les capacités restent fermées tant que leur dernière évaluation n’est pas disponible."
            onRetry={() => void capabilities.refetch()}
            retryDisabled={capabilities.isFetching}
            title="Registre indisponible"
          />
        ) : capabilities.isPending ? (
          <RemoteLoadingState label="Chargement des capacités" rows={4} />
        ) : capabilities.data?.data.length ? (
          <CapabilityMatrix values={capabilities.data.data} />
        ) : (
          <RemoteEmptyState description="Aucun snapshot n’a encore été évalué ; tous les marchés restent fermés." />
        )}
        <PagedResults label="de capacités" query={capabilities} />
      </Panel>

      <Panel icon={<ShieldAlert className="size-5" />} title="Anomalies bloquantes">
        <QueryRecovery queries={[issues]} />
        {issues.isError && !canReadPrevious(issues) ? (
          <RemoteRecoverableErrorState
            description="Les snapshots valides restent consultables ; la liste d’anomalies peut être rechargée séparément."
            onRetry={() => void issues.refetch()}
            retryDisabled={issues.isFetching}
          />
        ) : issues.isPending ? (
          <RemoteLoadingState label="Chargement des anomalies" rows={4} />
        ) : issues.data?.data.length ? (
          <QualityList issues={issues.data.data} />
        ) : (
          <RemoteEmptyState description="Aucune anomalie ouverte." />
        )}
        <PagedResults label="d’anomalies" query={issues} />
      </Panel>

      <Panel icon={<ArchiveRestore className="size-5" />} title="Quarantaine">
        {issues.isError && !canReadPrevious(issues) ? (
          <RemoteRecoverableErrorState
            description="L’état de la quarantaine ne peut pas être vérifié pour le moment."
            onRetry={() => void issues.refetch()}
            retryDisabled={issues.isFetching}
          />
        ) : issues.isPending ? (
          <RemoteLoadingState label="Chargement de la quarantaine" rows={3} />
        ) : quarantined.length > 0 ? (
          <QualityList issues={quarantined} />
        ) : (
          <RemoteEmptyState
            description={
              issues.hasNextPage
                ? "Aucun snapshot en quarantaine parmi les anomalies chargées."
                : "Aucun snapshot n’est actuellement en quarantaine."
            }
          />
        )}
        {issues.hasNextPage ? (
          <p className="text-xs text-ink-secondary">
            Cette liste porte sur les anomalies chargées. Affichez la suite des anomalies pour
            compléter la quarantaine.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}

function JobList({ jobs }: Readonly<{ jobs: readonly JobSummary[] }>) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {jobs.map((job) => (
        <article
          className="grid min-w-0 gap-3 rounded-lg border border-border-subtle p-4 [overflow-wrap:anywhere]"
          key={job.jobId}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-semibold">{job.name}</p>
            <StatusBadge status={job.status} />
          </div>
          <p className="text-xs leading-5 text-ink-secondary">
            Dernière exécution : {job.lastRunAt ? formatDateTime(job.lastRunAt) : "jamais"}
          </p>
          {job.attempt !== null && job.attempt !== undefined ? (
            <p className="text-xs text-ink-secondary">
              Tentative {job.attempt} / {job.maxAttempts} · {job.scope}
            </p>
          ) : null}
          {job.scheduledAt && job.status === "queued" ? (
            <p className="text-xs text-ink-secondary">
              Planifié le {formatDateTime(job.scheduledAt)}
            </p>
          ) : null}
          {job.errorCode ? (
            <p className="text-xs text-ink-secondary">
              <TechnicalText>Erreur : {job.errorCode}</TechnicalText>
            </p>
          ) : null}
          {job.cancelRequested ? (
            <p className="text-xs text-ink-secondary">Annulation demandée</p>
          ) : null}
          {job.traceId ? (
            <p className="text-xs text-ink-secondary">
              <TechnicalText>Trace : {job.traceId}</TechnicalText>
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function AuditList({ entries }: Readonly<{ entries: readonly AuditEntry[] }>) {
  return (
    <ol className="grid gap-3">
      {entries.map((entry) => (
        <li
          className="grid min-w-0 gap-2 rounded-lg border border-border-subtle p-4 [overflow-wrap:anywhere]"
          key={entry.auditId}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold">{entry.action}</p>
            <Badge>{entry.dataMode}</Badge>
          </div>
          <p className="text-xs text-ink-secondary">
            {formatDateTime(entry.occurredAt)} · ressource {entry.resourceId ?? "—"}
          </p>
          <p className="text-xs text-ink-secondary">
            <TechnicalText>Empreinte : {entry.idempotencyFingerprint}</TechnicalText>
          </p>
          {entry.actor ? (
            <p className="text-xs text-ink-secondary">
              {entry.actor} · {entry.reason ?? "motif non renseigné"}
            </p>
          ) : null}
          {entry.impact ? (
            <details className="min-w-0 text-xs text-ink-secondary">
              <summary className="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus">
                Références et trace
              </summary>
              <pre
                aria-label="Références et trace de l’action"
                className="mt-2 max-h-64 overflow-auto overscroll-contain rounded whitespace-pre-wrap ui-technical-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                tabIndex={0}
              >
                {JSON.stringify(entry.impact, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function AdminOperationsDashboard() {
  const queryClient = useQueryClient();
  const [submittedJob, setSubmittedJob] = useState<JobSummary | null>(null);
  const jobs = usePagedAdminResource<PageResponseJobSummary>("jobs", (pages) => {
    if (!submittedJob) return false;
    const current =
      pages.flatMap((page) => page.data).find((job) => job.jobId === submittedJob.jobId) ??
      submittedJob;
    return ["queued", "running"].includes(current.status) ? 2000 : false;
  });
  const audit = usePagedAdminResource<PageResponseAuditEntry>("audit-log");
  const sync = useMutation({
    mutationFn: startSync,
    onSuccess: async (response) => {
      setSubmittedJob("jobId" in response.data ? response.data : null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "data-sources"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "ingestion-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "quality-issues"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "jobs"] }),
      ]);
    },
  });
  const dataMode = canReadPrevious(jobs) ? jobs.data?.meta.dataMode : undefined;
  const activeJob = canReadPrevious(jobs)
    ? (jobs.data?.data.find((job) => job.jobId === submittedJob?.jobId) ?? submittedJob)
    : null;
  const syncInProgress =
    sync.isPending || activeJob?.status === "queued" || activeJob?.status === "running";

  useEffect(() => {
    if (activeJob?.status !== "succeeded") return;
    for (const resource of [
      "audit-log",
      "data-sources",
      "ingestion-runs",
      "quality-issues",
      "capabilities",
    ]) {
      void queryClient.invalidateQueries({ queryKey: ["admin", resource] });
    }
  }, [activeJob?.jobId, activeJob?.status, queryClient]);

  return (
    <div className="ui-page-stack">
      <PageHeader
        description="Commandes idempotentes et journal audité. Les synchronisations en file sont suivies jusqu’à leur résultat."
        eyebrow="Opérations contrôlées"
        title="Administration"
      />

      <Panel icon={<RefreshCw className="size-5" />} title="Synchronisation contrôlée">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            aria-busy={syncInProgress}
            disabled={syncInProgress || !dataMode}
            onClick={() => {
              sync.mutate(crypto.randomUUID());
            }}
          >
            {syncInProgress ? (
              <RefreshCw
                aria-hidden="true"
                className="size-4 animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Play aria-hidden="true" className="size-4" />
            )}
            {syncInProgress
              ? "Synchronisation en cours…"
              : dataMode
                ? `Lancer la synchronisation ${dataMode}`
                : jobs.isError
                  ? "Mode indisponible"
                  : "Vérification du mode…"}
          </Button>
          <p className="text-xs leading-5 text-ink-secondary">
            {dataMode
              ? "Le résultat apparaît ici et dans le journal d’audit."
              : jobs.isError
                ? "Réessayez le chargement des jobs ci-dessous pour vérifier le mode."
                : "La synchronisation sera disponible lorsque le mode aura été vérifié."}
          </p>
        </div>
        {sync.isPending ? (
          <div aria-live="polite" className="rounded-lg bg-surface-muted p-4 text-sm" role="status">
            Progression : commande envoyée, validation du résultat en cours.
          </div>
        ) : null}
        {sync.isError ? (
          <RemoteRecoverableErrorState
            description={sync.error.message}
            onRetry={() => {
              sync.mutate(sync.variables);
            }}
            title="Synchronisation échouée"
            retryDisabled={syncInProgress}
          />
        ) : null}
        {sync.data && "rowCount" in sync.data.data && !submittedJob ? (
          <div
            aria-live="polite"
            className={`grid gap-3 rounded-lg border p-4 text-sm ${statusTone(sync.data.data.status)}`}
            role="status"
          >
            <p className="flex items-center gap-2 font-semibold">
              {sync.data.data.status === "succeeded" ? (
                <CheckCircle2 aria-hidden="true" className="size-4" />
              ) : (
                <CircleAlert aria-hidden="true" className="size-4" />
              )}
              {sync.data.data.status === "succeeded"
                ? "Synchronisation terminée"
                : "Synchronisation non validée"}
            </p>
            <p>
              {sync.data.data.rowCount} lignes · {sync.data.data.status} · fin{" "}
              {formatDateTime(sync.data.data.completedAt)}
            </p>
            <p className="text-xs text-ink-secondary">
              <TechnicalText>Run {sync.data.data.runId}</TechnicalText>
            </p>
          </div>
        ) : null}
        {activeJob ? (
          <div
            aria-live="polite"
            className="grid gap-2 rounded-lg border border-divider bg-surface-muted p-4 text-sm"
            role="status"
          >
            <p className="font-semibold">
              {activeJob.status === "queued"
                ? "Synchronisation en file"
                : activeJob.status === "running"
                  ? "Synchronisation en cours"
                  : activeJob.status === "succeeded"
                    ? "Synchronisation terminée"
                    : "Synchronisation interrompue"}
            </p>
            <p className="text-xs text-ink-secondary">
              <TechnicalText>Job {activeJob.jobId}</TechnicalText>
            </p>
            {activeJob.runId ? (
              <p className="text-xs text-ink-secondary">
                <TechnicalText>Run {activeJob.runId}</TechnicalText>
              </p>
            ) : null}
            {activeJob.errorCode ? <p>{activeJob.errorCode}</p> : null}
            <p>Le dernier snapshot validé reste actif jusqu’à la validation du suivant.</p>
          </div>
        ) : null}
      </Panel>

      <Panel icon={<Activity className="size-5" />} title="Jobs">
        <QueryRecovery queries={[jobs]} />
        {jobs.isError && !canReadPrevious(jobs) ? (
          <RemoteRecoverableErrorState
            onRetry={() => void jobs.refetch()}
            retryDisabled={jobs.isFetching}
          />
        ) : jobs.data?.data.length ? (
          <JobList jobs={jobs.data.data} />
        ) : jobs.isPending ? (
          <RemoteLoadingState minHeight="12rem" />
        ) : (
          <RemoteEmptyState description="Aucun job n’est déclaré." />
        )}
        <PagedResults label="de jobs" query={jobs} />
      </Panel>

      <MappingReviewQueue />

      <OperationalStatusPanel />

      <Panel icon={<ListChecks className="size-5" />} title="Journal d’audit">
        <QueryRecovery queries={[audit]} />
        {audit.isError && !canReadPrevious(audit) ? (
          <RemoteRecoverableErrorState
            onRetry={() => void audit.refetch()}
            retryDisabled={audit.isFetching}
          />
        ) : audit.data?.data.length ? (
          <AuditList entries={audit.data.data} />
        ) : audit.isPending ? (
          <RemoteLoadingState minHeight="12rem" />
        ) : (
          <RemoteEmptyState description="Aucune action auditée dans cet historique." />
        )}
        <PagedResults label="d’actions" query={audit} />
      </Panel>

      <div
        className="flex items-start gap-3 rounded-xl border border-border-subtle bg-surface-muted p-4 text-sm leading-6 text-ink-secondary"
        role="note"
      >
        <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
        {dataMode === "mock"
          ? "Les synchronisations mock n’accèdent pas au réseau Oracle’s Elixir et restent isolées du mode réel."
          : dataMode === "real"
            ? "La synchronisation réelle conserve le dernier snapshot validé lorsqu’une source externe échoue."
            : "Le mode de synchronisation est en cours de vérification."}
      </div>
    </div>
  );
}
