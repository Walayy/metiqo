"use client";

import type {
  AuditEntry,
  CapabilityEvaluationDto,
  DataQualityIssue,
  IngestionRunSummary,
  ItemResponseIngestionRunSummary,
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
  Card,
  CardContent,
  RemoteBlockingErrorState,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import type { ReactNode } from "react";

import { formatDateTime } from "./opportunity-presenters";
import { MappingReviewQueue } from "./mapping-review-queue";

const API_BASE = "/api/backend/api/v1/admin";

async function readResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La ressource d’administration ne répond pas");
  return (await response.json()) as T;
}

async function startSync(): Promise<ItemResponseIngestionRunSummary> {
  const response = await fetch(`${API_BASE}/oracles-elixir/sync`, {
    headers: {
      accept: "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    method: "POST",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? "La synchronisation n’a pas pu démarrer");
  }
  return (await response.json()) as ItemResponseIngestionRunSummary;
}

function Panel({
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

function statusTone(status: string) {
  if (status === "succeeded" || status === "fresh" || status === "enabled") {
    return "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (
    status === "failed" ||
    status === "blocking" ||
    status === "quarantined" ||
    status === "disabled"
  ) {
    return "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200";
  }
  if (status === "degraded" || status === "stale" || status === "warning" || status === "pending") {
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
    <div className="grid min-w-0 gap-2 rounded-lg border border-border-subtle bg-surface-muted p-4">
      <dt className="flex items-center gap-2 text-xs uppercase tracking-[0.1em] text-ink-secondary">
        <span aria-hidden="true">{icon}</span>
        <span>{label}</span>
      </dt>
      <dd className="break-words text-sm font-semibold">{value}</dd>
    </div>
  );
}

function SourceCatalogue({ source }: Readonly<{ source: ProviderHealth }>) {
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{source.providerCode}</p>
          <p className="mt-1 text-xs text-ink-secondary">
            Contrôle : {formatDateTime(source.checkedAt)}
          </p>
        </div>
        <StatusBadge status={source.status} />
      </div>
      {source.status === "degraded" ? (
        <div
          className="rounded-lg border border-amber-300 bg-amber-50/80 p-4 text-sm leading-6 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100"
          role="status"
        >
          <p className="font-semibold">Erreur récupérable · dernier snapshot conservé</p>
          <p>{source.detail}</p>
        </div>
      ) : null}
      <dl className="grid gap-3 sm:grid-cols-2">
        <Stat
          icon={<CheckCircle2 className="size-4" />}
          label="Dernier succès"
          value={source.lastSuccessAt ? formatDateTime(source.lastSuccessAt) : "Aucun"}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Fraîcheur source"
          value={source.status}
        />
      </dl>
    </div>
  );
}

function SnapshotOverview({ runs }: Readonly<{ runs: readonly IngestionRunSummary[] }>) {
  const orderedRuns = runs.toSorted((left, right) => right.startedAt.localeCompare(left.startedAt));
  const lastAttempt = orderedRuns[0];
  const lastSuccess = orderedRuns.find((run) => run.status === "succeeded");
  const activeSnapshot = orderedRuns.find((run) => run.lastValidSnapshotId)?.lastValidSnapshotId;
  const years = [
    ...new Set(runs.map((run) => run.seasonYear ?? new Date(run.startedAt).getUTCFullYear())),
  ].sort((left, right) => right - left);

  return (
    <div className="grid gap-4">
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
          value={lastSuccess?.rowCount.toString() ?? "0"}
        />
        <Stat
          icon={<Fingerprint className="size-4" />}
          label="Snapshot actif"
          value={activeSnapshot ?? "Non exposé"}
        />
        <Stat
          icon={<CalendarRange className="size-4" />}
          label="Fraîcheur annuelle"
          value={years.length > 0 ? years.join(", ") : "Non exposée"}
        />
        <Stat
          icon={<ArchiveRestore className="size-4" />}
          label="Hash actif"
          value={lastSuccess?.snapshotSha256 ?? "Non exposé dans ce mode"}
        />
      </dl>
      <div className="grid gap-2 rounded-lg border border-border-subtle p-4 text-sm leading-6">
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
            : "aucun changement déclaré dans ce mode"}
        </p>
      </div>
    </div>
  );
}

function IngestionHistory({ runs }: Readonly<{ runs: readonly IngestionRunSummary[] }>) {
  return (
    <div
      aria-label="Historique des synchronisations"
      className="max-w-full overflow-x-auto rounded-lg border border-border-subtle"
      role="region"
      tabIndex={0}
    >
      <table className="w-full min-w-[48rem] border-collapse text-left text-xs">
        <thead className="bg-surface-muted text-ink-secondary">
          <tr>
            {["Source", "Statut", "Début", "Fin", "Lignes", "Dernier snapshot valide"].map(
              (label) => (
                <th className="px-3 py-3 font-semibold" key={label} scope="col">
                  {label}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {runs.map((run) => (
            <tr key={run.runId}>
              <td className="px-3 py-3 font-semibold">{run.source}</td>
              <td className="px-3 py-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="whitespace-nowrap px-3 py-3">{formatDateTime(run.startedAt)}</td>
              <td className="whitespace-nowrap px-3 py-3">{formatDateTime(run.completedAt)}</td>
              <td className="px-3 py-3 tabular-nums">{run.rowCount}</td>
              <td className="max-w-64 break-all px-3 py-3">{run.lastValidSnapshotId ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QualityList({ issues }: Readonly<{ issues: readonly DataQualityIssue[] }>) {
  return (
    <div className="grid gap-3">
      {issues.map((issue) => (
        <article
          className="grid gap-2 rounded-lg border border-border-subtle p-4 sm:grid-cols-[1fr_auto]"
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
    <div
      aria-label="Matrice des capacités"
      className="max-w-full overflow-x-auto rounded-lg border border-border-subtle"
      role="region"
      tabIndex={0}
    >
      <table className="w-full min-w-[62rem] border-collapse text-left text-xs">
        <thead className="bg-surface-muted text-ink-secondary">
          <tr>
            {["Capacité", "État", "Gates", "Complétude", "Échantillon", "Seuils", "Raisons"].map(
              (label) => (
                <th className="px-3 py-3 font-semibold" key={label} scope="col">
                  {label}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {values.map((value) => (
            <tr key={`${value.snapshotId}:${value.capability}:${value.thresholdVersion}`}>
              <td className="px-3 py-3">
                <p className="font-semibold">{value.capability}</p>
                <p className="mt-1 text-ink-secondary">
                  {value.kind} · révision {value.evaluationRevision}
                </p>
              </td>
              <td className="px-3 py-3">
                <StatusBadge status={value.status} />
              </td>
              <td className="max-w-72 px-3 py-3">
                <div className="flex flex-wrap gap-1">
                  {Object.entries(value.gates).map(([gate, state]) => (
                    <Badge
                      className={statusTone(
                        state === true ? "enabled" : state === false ? "disabled" : "pending",
                      )}
                      key={gate}
                    >
                      {gate}: {state === true ? "ok" : state === false ? "non" : "attente"}
                    </Badge>
                  ))}
                </div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                {(Number(value.observedCompleteness) * 100).toFixed(1)} % /{" "}
                {(Number(value.minimumCompleteness) * 100).toFixed(1)} %
              </td>
              <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                {value.observedSampleSize} / {value.minimumSampleSize}
              </td>
              <td className="px-3 py-3">
                <p>{value.thresholdVersion}</p>
                <p className="mt-1 max-w-56 break-all text-ink-secondary">
                  snapshot {value.snapshotId}
                </p>
              </td>
              <td className="max-w-72 px-3 py-3 text-ink-secondary">
                {value.reasonCodes.length > 0 ? value.reasonCodes.join(" · ") : "Aucun blocage"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PageHeader({ description, eyebrow, title }: Readonly<Record<string, string>>) {
  return (
    <header className="grid gap-3">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      <p className="max-w-3xl text-sm leading-6 text-ink-secondary sm:text-base">{description}</p>
    </header>
  );
}

export function DataHealthDashboard() {
  const sources = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseProviderHealth>("/data-sources?offset=0&limit=100", signal),
    queryKey: ["admin", "data-sources"],
  });
  const runs = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseIngestionRunSummary>("/ingestion-runs?offset=0&limit=100", signal),
    queryKey: ["admin", "ingestion-runs"],
  });
  const issues = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseDataQualityIssue>("/quality-issues?offset=0&limit=100", signal),
    queryKey: ["admin", "quality-issues"],
  });
  const capabilities = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseCapabilityEvaluationDto>("/capabilities?offset=0&limit=100", signal),
    queryKey: ["admin", "capabilities"],
  });
  const quarantined = issues.data?.data.filter((issue) => issue.status === "quarantined") ?? [];

  return (
    <div className="grid gap-6 sm:gap-8">
      <PageHeader
        description="Catalogue de provenance, snapshots validés, fraîcheur et anomalies. Les champs absents du mode courant sont signalés au lieu d’être déduits."
        eyebrow="Provenance & qualité"
        title="Santé des données"
      />

      <Panel icon={<Database className="size-5" />} title="Catalogue des sources">
        {sources.isError ? (
          <RemoteBlockingErrorState
            description="Le catalogue primaire est indisponible : aucun état de source fiable ne peut être affiché."
            title="Catalogue indisponible"
          />
        ) : (
          <RemoteDataBoundary
            isLoading={sources.isPending}
            isRefetching={sources.isFetching && !sources.isPending}
            loadingFallback={<RemoteLoadingState minHeight="14rem" rows={4} />}
          >
            {sources.data?.data[0] ? (
              <SourceCatalogue source={sources.data.data[0]} />
            ) : (
              <RemoteEmptyState description="Aucune source n’est déclarée dans ce mode." />
            )}
          </RemoteDataBoundary>
        )}
      </Panel>

      <Panel icon={<Fingerprint className="size-5" />} title="Snapshot et couverture">
        {runs.isError ? (
          <RemoteRecoverableErrorState
            onRetry={() => void runs.refetch()}
            title="Historique indisponible"
          />
        ) : (
          <RemoteDataBoundary
            isLoading={runs.isPending}
            isRefetching={runs.isFetching && !runs.isPending}
          >
            <SnapshotOverview runs={runs.data?.data ?? []} />
          </RemoteDataBoundary>
        )}
      </Panel>

      <Panel icon={<FileClock className="size-5" />} title="Tentatives d’ingestion">
        {runs.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void runs.refetch()} />
        ) : runs.data?.data.length ? (
          <IngestionHistory runs={runs.data.data} />
        ) : (
          <RemoteEmptyState description="Aucune synchronisation n’a encore été enregistrée." />
        )}
      </Panel>

      <Panel icon={<ListChecks className="size-5" />} title="Capacités par snapshot">
        {capabilities.isError ? (
          <RemoteRecoverableErrorState
            description="Les capacités restent fermées tant que leur dernière évaluation n’est pas disponible."
            onRetry={() => void capabilities.refetch()}
            title="Registre indisponible"
          />
        ) : capabilities.data?.data.length ? (
          <CapabilityMatrix values={capabilities.data.data} />
        ) : (
          <RemoteEmptyState description="Aucun snapshot n’a encore été évalué ; tous les marchés restent fermés." />
        )}
      </Panel>

      <Panel icon={<ShieldAlert className="size-5" />} title="Anomalies bloquantes">
        {issues.isError ? (
          <RemoteRecoverableErrorState
            description="Les snapshots valides restent consultables ; la liste d’anomalies peut être rechargée séparément."
            onRetry={() => void issues.refetch()}
          />
        ) : issues.data?.data.length ? (
          <QualityList issues={issues.data.data} />
        ) : (
          <RemoteEmptyState description="Aucune anomalie ouverte." />
        )}
      </Panel>

      <Panel icon={<ArchiveRestore className="size-5" />} title="Quarantaine">
        {quarantined.length > 0 ? (
          <QualityList issues={quarantined} />
        ) : (
          <RemoteEmptyState description="Aucun snapshot n’est actuellement en quarantaine." />
        )}
      </Panel>
    </div>
  );
}

function JobList({ jobs }: Readonly<{ jobs: readonly JobSummary[] }>) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {jobs.map((job) => (
        <article className="grid gap-3 rounded-lg border border-border-subtle p-4" key={job.jobId}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-semibold">{job.name}</p>
            <StatusBadge status={job.status} />
          </div>
          <p className="text-xs leading-5 text-ink-secondary">
            Dernière exécution : {job.lastRunAt ? formatDateTime(job.lastRunAt) : "jamais"}
          </p>
        </article>
      ))}
    </div>
  );
}

function AuditList({ entries }: Readonly<{ entries: readonly AuditEntry[] }>) {
  return (
    <ol className="grid gap-3">
      {entries.map((entry) => (
        <li className="grid gap-2 rounded-lg border border-border-subtle p-4" key={entry.auditId}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold">{entry.action}</p>
            <Badge>{entry.dataMode}</Badge>
          </div>
          <p className="text-xs text-ink-secondary">
            {formatDateTime(entry.occurredAt)} · ressource {entry.resourceId ?? "—"}
          </p>
          <p className="break-all text-xs text-ink-secondary">
            Empreinte d’idempotence : {entry.idempotencyFingerprint}
          </p>
        </li>
      ))}
    </ol>
  );
}

export function AdminOperationsDashboard() {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseJobSummary>("/jobs?offset=0&limit=100", signal),
    queryKey: ["admin", "jobs"],
  });
  const audit = useQuery({
    queryFn: ({ signal }) =>
      readResource<PageResponseAuditEntry>("/audit-log?offset=0&limit=100", signal),
    queryKey: ["admin", "audit-log"],
  });
  const sync = useMutation({
    mutationFn: startSync,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "data-sources"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "ingestion-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "quality-issues"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "jobs"] }),
      ]);
    },
  });
  const dataMode = jobs.data?.meta.dataMode ?? "mock";

  return (
    <div className="grid gap-6 sm:gap-8">
      <PageHeader
        description="Commandes idempotentes, résultats immédiats et journal audité. Une action déclenche une seule actualisation ciblée, sans polling."
        eyebrow="Opérations contrôlées"
        title="Administration"
      />

      <Panel icon={<RefreshCw className="size-5" />} title="Synchronisation contrôlée">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={sync.isPending}
            onClick={() => {
              sync.mutate();
            }}
          >
            {sync.isPending ? (
              <RefreshCw
                aria-hidden="true"
                className="size-4 animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Play aria-hidden="true" className="size-4" />
            )}
            {sync.isPending ? "Synchronisation en cours…" : `Lancer la synchronisation ${dataMode}`}
          </Button>
          <p className="text-xs leading-5 text-ink-secondary">
            Une clé d’idempotence unique est générée pour cette action.
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
              sync.mutate();
            }}
            title="Synchronisation échouée"
          />
        ) : null}
        {sync.data ? (
          <div
            aria-live="polite"
            className="grid gap-3 rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/30"
            role="status"
          >
            <p className="flex items-center gap-2 font-semibold">
              <CheckCircle2 aria-hidden="true" className="size-4" />
              Synchronisation terminée
            </p>
            <p>
              {sync.data.data.rowCount} lignes · {sync.data.data.status} · fin{" "}
              {formatDateTime(sync.data.data.completedAt)}
            </p>
            <p className="break-all text-xs text-ink-secondary">Run {sync.data.data.runId}</p>
          </div>
        ) : null}
      </Panel>

      <Panel icon={<Activity className="size-5" />} title="Jobs">
        {jobs.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void jobs.refetch()} />
        ) : jobs.data?.data.length ? (
          <JobList jobs={jobs.data.data} />
        ) : jobs.isPending ? (
          <RemoteLoadingState minHeight="12rem" />
        ) : (
          <RemoteEmptyState description="Aucun job n’est déclaré." />
        )}
      </Panel>

      <MappingReviewQueue />

      <Panel icon={<ListChecks className="size-5" />} title="Journal d’audit">
        {audit.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void audit.refetch()} />
        ) : audit.data?.data.length ? (
          <AuditList entries={audit.data.data} />
        ) : audit.isPending ? (
          <RemoteLoadingState minHeight="12rem" />
        ) : (
          <RemoteEmptyState description="Aucune action auditée dans cette session mock." />
        )}
      </Panel>

      <div
        className="flex items-start gap-3 rounded-xl border border-border-subtle bg-surface-muted p-4 text-sm leading-6 text-ink-secondary"
        role="note"
      >
        <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
        {dataMode === "mock"
          ? "Les synchronisations mock n’accèdent pas au réseau Oracle’s Elixir et restent isolées du mode réel."
          : "La synchronisation réelle conserve le dernier snapshot validé lorsqu’une source externe échoue."}
      </div>
    </div>
  );
}
