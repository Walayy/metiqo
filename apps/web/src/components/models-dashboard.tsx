"use client";

import { QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend, requestBackend } from "../lib/backend";

import type {
  BacktestSummary,
  ItemResponseJobSummary,
  ItemResponseModelSummary,
  JobSummary,
  ModelSummary,
  PageResponseBacktestSummary,
  PageResponseModelSummary,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  Metric,
  Select,
  TitledCard as Panel,
  TechnicalText,
  Table,
  TableBody,
  TableCell,
  TableCellContent,
  TableRow,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemotePageLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CalendarRange,
  ChartColumnIncreasing,
  CheckCircle2,
  CircleAlert,
  GitCompareArrows,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { formatDateTime, formatDecimal } from "./opportunity-presenters";
import { nextPageOffset, PagedResults } from "./paged-results";

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Les modèles ne sont pas disponibles");
  return (await response.json()) as T;
}

type ModelAction = { action: "train" } | { action: "promote" | "retire"; modelVersionId: string };

async function runModelAction(
  request: ModelAction,
  key: string,
): Promise<ItemResponseModelSummary | ItemResponseJobSummary> {
  const endpoint =
    request.action === "train"
      ? "/api/v1/admin/models/train"
      : `/api/v1/admin/models/${encodeURIComponent(request.modelVersionId)}/${request.action}`;
  const body =
    request.action === "train"
      ? { gameTitle: "lol", marketType: "MATCH_WINNER" }
      : {
          reason:
            request.action === "promote"
              ? "Promotion manuelle depuis le tableau des modèles"
              : "Retrait manuel depuis le tableau des modèles",
        };
  const response = await requestBackend(`/api/backend${endpoint}`, {
    body: JSON.stringify(body),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "Idempotency-Key": key,
      "X-Metiquo-CSRF": "1",
    },
    method: "POST",
  }).catch(() => {
    throw new Error("La réponse à la demande n’a pas pu être confirmée. Vous pouvez réessayer.");
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? "La décision sur le modèle a échoué");
  }
  return (await response.json()) as ItemResponseModelSummary | ItemResponseJobSummary;
}

function metricLabel(metric: string) {
  if (metric === "log_loss") return "Log loss";
  if (metric === "brier") return "Score de Brier";
  return metric.replaceAll("_", " ");
}

function metricValue(value: string | number | undefined) {
  return value === undefined || !Number.isFinite(Number(value)) ? "N/D" : formatDecimal(value);
}

function MetricComparison({ model, metric }: Readonly<{ model: ModelSummary; metric: string }>) {
  const modelValue = model.metrics[metric];
  const value =
    modelValue === undefined || !Number.isFinite(Number(modelValue)) ? null : Number(modelValue);
  const baselineValue = model.baselineMetrics[metric];
  const baseline =
    baselineValue === undefined || !Number.isFinite(Number(baselineValue))
      ? null
      : Number(baselineValue);
  const summary = `${metricLabel(metric)} : modèle ${value === null ? "non disponible" : formatDecimal(value)}, baseline ${baseline === null ? "non disponible" : formatDecimal(baseline)}.${metric === "log_loss" || metric === "brier" ? " Une valeur plus basse est préférable." : ""}`;
  const maximum = Math.max(value ?? 0, baseline ?? 0, 0.01);

  return (
    <figure className="grid gap-2 rounded-lg border border-border-subtle p-4">
      <figcaption className="text-sm font-semibold">{metricLabel(metric)}</figcaption>
      <div aria-label={summary} className="grid gap-2" role="img">
        {(
          [
            ["Modèle", value, "bg-accent"],
            ["Baseline", baseline, "bg-ink-secondary"],
          ] satisfies readonly (readonly [string, number | null, string])[]
        ).map(([label, rawValue, tone]) => {
          const numericValue = rawValue ?? 0;
          return (
            <div
              className="grid min-w-0 grid-cols-[4rem_minmax(0,1fr)_auto] items-center gap-2 text-xs"
              key={label}
            >
              <span>{label}</span>
              <span className="h-2 overflow-hidden rounded-full bg-surface-muted">
                <span
                  className={`block h-full rounded-full ${tone}`}
                  style={{
                    width: `${Math.max(0, Math.min((numericValue / maximum) * 100, 100)).toFixed(2)}%`,
                  }}
                />
              </span>
              <span className="font-semibold tabular-nums">
                {rawValue === null ? "N/D" : formatDecimal(numericValue)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-xs leading-5 text-ink-secondary">{summary}</p>
    </figure>
  );
}

function ModelCard({
  error,
  isPending,
  model,
  onAction,
  pendingAction,
}: Readonly<{
  error?: string | undefined;
  isPending: boolean;
  model: ModelSummary;
  onAction: (request: ModelAction) => void;
  pendingAction?: ModelAction | undefined;
}>) {
  const actionForModel =
    isPending &&
    pendingAction &&
    "modelVersionId" in pendingAction &&
    pendingAction.modelVersionId === model.modelVersionId
      ? pendingAction.action
      : null;
  const badgeTone =
    model.status === "champion"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
      : model.status === "candidate"
        ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
        : "border-border-strong bg-surface-muted text-ink-secondary";
  return (
    <Card aria-label={`Modèle ${model.modelVersion}`}>
      <CardContent className="grid h-full gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 [overflow-wrap:anywhere]">
            <h3 className="font-semibold">
              <TechnicalText className="text-sm text-ink-primary">
                {model.modelVersion}
              </TechnicalText>
            </h3>
          </div>
          <Badge className={badgeTone}>
            {model.status === "champion" ? (
              <CheckCircle2 aria-hidden="true" className="mr-1 size-3.5" />
            ) : null}
            {model.status}
          </Badge>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-secondary">Log loss</dt>
            <dd className="mt-1 font-semibold">{metricValue(model.metrics.log_loss)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Brier / calibration</dt>
            <dd className="mt-1 font-semibold">{metricValue(model.metrics.brier)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-ink-secondary">Marché</dt>
            <dd className="mt-1 font-semibold">Vainqueur du match</dd>
          </div>
        </dl>
        {model.status === "candidate" || model.status === "champion" ? (
          <div className="flex flex-wrap gap-2">
            {model.status === "candidate" ? (
              <Button
                aria-busy={actionForModel === "promote"}
                disabled={isPending}
                onClick={() => {
                  onAction({ action: "promote", modelVersionId: model.modelVersionId });
                }}
                size="small"
              >
                <ShieldCheck aria-hidden="true" className="size-4" />
                {actionForModel === "promote" ? "Promotion…" : "Promouvoir"}
              </Button>
            ) : null}
            <Button
              aria-busy={actionForModel === "retire"}
              disabled={isPending}
              onClick={() => {
                onAction({ action: "retire", modelVersionId: model.modelVersionId });
              }}
              size="small"
              variant="outline"
            >
              {actionForModel === "retire" ? "Retrait…" : "Retirer"}
            </Button>
          </div>
        ) : null}
        {error ? (
          <p className="text-sm text-red-700 dark:text-red-300" role="alert">
            {error}
          </p>
        ) : null}
        <details className="min-w-0 border-t border-border-subtle pt-3 text-xs leading-5">
          <summary className="cursor-pointer rounded font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus">
            Traçabilité et promotion
          </summary>
          <dl className="mt-3 grid min-w-0 gap-3 text-ink-secondary">
            <div>
              <dt>Algorithme</dt>
              <dd className="font-medium text-ink-primary [overflow-wrap:anywhere]">
                {model.algorithm}
              </dd>
            </div>
            <div>
              <dt>Features</dt>
              <dd>
                <TechnicalText>{model.featureVersion}</TechnicalText>
              </dd>
            </div>
            <div>
              <dt>Version exacte de prédiction</dt>
              <dd>
                <TechnicalText>{model.modelVersionId}</TechnicalText>
              </dd>
            </div>
            <div>
              <dt>Promotion</dt>
              <dd className="[overflow-wrap:anywhere]">
                {model.promotionReason ?? "Aucune promotion enregistrée"}
              </dd>
              {model.promotedAt ? <dd>{formatDateTime(model.promotedAt)}</dd> : null}
            </div>
          </dl>
        </details>
      </CardContent>
    </Card>
  );
}

function BacktestTable({
  backtests,
  models,
}: Readonly<{ backtests: readonly BacktestSummary[]; models: readonly ModelSummary[] }>) {
  const versions = new Map(models.map((model) => [model.modelVersionId, model.modelVersion]));

  return (
    <Table
      aria-label="Performance temporelle des backtests"
      columns={[
        { label: "Version", variant: "technical", weight: 1.8 },
        { label: "Période walk-forward", variant: "date", weight: 1.7 },
        { label: "Échantillon", variant: "number", weight: 1.2 },
        { label: "Log loss", variant: "number" },
        { label: "Baseline", variant: "number" },
        { label: "Brier", variant: "number" },
        { label: "Test final", variant: "status" },
        { label: "Segment", variant: "text" },
      ]}
    >
      <TableBody>
        {backtests.map((backtest) => (
          <TableRow key={backtest.backtestId}>
            <TableCell label="Version" variant="technical">
              {versions.get(backtest.modelVersionId) ?? backtest.modelVersionId}
            </TableCell>
            <TableCell label="Période walk-forward" variant="date">
              <TableCellContent
                primary={formatDateTime(backtest.startsAt)}
                secondary={<>au {formatDateTime(backtest.endsAt)}</>}
              />
            </TableCell>
            <TableCell label="Échantillon" variant="number">
              <TableCellContent
                primary={backtest.sampleCount.toString()}
                secondary={
                  backtest.sampleCount < 500 ? (
                    <span className="text-amber-700 dark:text-amber-300">⚠ Faible échantillon</span>
                  ) : null
                }
              />
            </TableCell>
            <TableCell label="Log loss" variant="number">
              {metricValue(backtest.metrics.log_loss)}
            </TableCell>
            <TableCell label="Baseline" variant="number">
              {metricValue(backtest.baselineMetrics.log_loss)}
            </TableCell>
            <TableCell label="Brier" variant="number">
              {metricValue(backtest.metrics.brier)}
            </TableCell>
            <TableCell label="Test final" variant="status">
              {backtest.finalTestUntouched ? "Préservé" : "Non préservé"}
            </TableCell>
            <TableCell label="Segment">Game winner · global</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ModelsDashboard() {
  const queryClient = useQueryClient();
  const trainingKey = useRef<string | null>(null);
  const [submittedJob, setSubmittedJob] = useState<JobSummary | null>(null);
  const [comparisonModelId, setComparisonModelId] = useState("");
  const trainingQuery = useQuery({
    enabled: submittedJob !== null,
    queryKey: ["training-job", submittedJob?.jobId],
    queryFn: ({ signal }) =>
      fetchResource<ItemResponseJobSummary>(
        `/api/v1/admin/jobs/${encodeURIComponent(submittedJob?.jobId ?? "")}`,
        signal,
      ),
    refetchInterval: (query) => {
      if (!canReadPrevious({ data: query.state.data ?? submittedJob, error: query.state.error })) {
        return false;
      }
      const status = query.state.data?.data.status ?? submittedJob?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
  const observedTraining = trainingQuery.data?.data ?? submittedJob;
  const training = canReadPrevious({ data: observedTraining, error: trainingQuery.error })
    ? observedTraining
    : null;
  const trainingPending = training?.status === "queued" || training?.status === "running";
  useEffect(() => {
    if (training?.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    }
  }, [queryClient, training?.jobId, training?.status]);
  const modelsQuery = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    queryFn: ({ signal, pageParam }) =>
      fetchResource<PageResponseModelSummary>(
        `/api/v1/models?offset=${String(pageParam)}&limit=100`,
        signal,
      ),
    queryKey: ["models"],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseModelSummary,
  });
  const backtestsQuery = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    queryFn: ({ signal, pageParam }) =>
      fetchResource<PageResponseBacktestSummary>(
        `/api/v1/backtests?offset=${String(pageParam)}&limit=100`,
        signal,
      ),
    queryKey: ["backtests"],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseBacktestSummary,
  });
  const isPending = modelsQuery.isPending;
  const isFetching = modelsQuery.isFetching;
  const isError = modelsQuery.isError;
  const models = modelsQuery.data?.data ?? [];
  const backtests = canReadPrevious(backtestsQuery) ? (backtestsQuery.data?.data ?? []) : [];
  const champions = models.filter((model) => model.status === "champion");
  const challengers = models.filter((model) => model.status === "candidate");
  const inactive = models.filter(
    (model) => model.status === "blocked" || model.status === "retired",
  );
  const referenceModel =
    models.find((model) => model.modelVersionId === comparisonModelId) ??
    champions.at(0) ??
    models.at(0);
  const action = useMutation({
    mutationFn: (request: ModelAction) =>
      runModelAction(
        request,
        request.action === "train"
          ? (trainingKey.current ??= crypto.randomUUID())
          : crypto.randomUUID(),
      ),
    onSuccess: async (response, request) => {
      if (request.action === "train") trainingKey.current = null;
      if ("jobId" in response.data) {
        setSubmittedJob(response.data);
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["models"] }),
        queryClient.invalidateQueries({ queryKey: ["backtests"] }),
      ]);
    },
  });

  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-2">
        <p className="flex items-center gap-2 ui-eyebrow">
          <Activity aria-hidden="true" className="size-4" />
          Validation hors échantillon
        </p>
        <h1 className="ui-page-title">Modèles & backtests</h1>
        <p className="text-body max-w-2xl text-ink-secondary">
          Versions traçables, calibration, baselines et validation walk-forward. Une métrique plus
          basse n’efface jamais l’incertitude d’échantillonnage.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            aria-busy={(action.isPending && action.variables.action === "train") || trainingPending}
            disabled={action.isPending || trainingPending}
            onClick={() => {
              action.mutate({ action: "train" });
            }}
          >
            {(action.isPending && action.variables.action === "train") || trainingPending ? (
              <RefreshCw
                aria-hidden="true"
                className="size-4 animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Play aria-hidden="true" className="size-4" />
            )}
            Entraîner un candidat
          </Button>
          {action.data && "modelVersion" in action.data.data ? (
            <p
              aria-live="polite"
              className="text-sm text-emerald-700 dark:text-emerald-300"
              role="status"
            >
              Action terminée · {action.data.data.status} · {action.data.data.modelVersion}
            </p>
          ) : null}
          {training ? (
            <p
              aria-label="Entraînement"
              aria-live="polite"
              className="min-w-0 text-sm text-ink-secondary [overflow-wrap:anywhere]"
              role="status"
            >
              Entraînement ·{" "}
              {
                {
                  queued: "En attente",
                  running: "En cours",
                  succeeded: "Terminé",
                  failed: "Échec",
                  dead: "Échec définitif",
                  cancelled: "Annulé",
                  idle: "Inactif",
                }[training.status]
              }
              {training.errorCode ? ` · ${training.errorCode}` : ""}
              {training.modelVersionId ? ` · ${training.modelVersionId}` : ""}
            </p>
          ) : null}
          {trainingQuery.isError ? (
            <div className="flex flex-wrap items-center gap-2 text-sm" role="alert">
              Suivi de l’entraînement indisponible.
              <Button
                disabled={trainingQuery.isFetching}
                onClick={() => void trainingQuery.refetch()}
                size="small"
                variant="outline"
              >
                Réessayer le suivi
              </Button>
            </div>
          ) : null}
          {action.error && action.variables.action === "train" ? (
            <p className="text-sm text-red-700 dark:text-red-300" role="alert">
              {action.error.message}
            </p>
          ) : null}
        </div>
      </header>

      <RemoteDataBoundary
        className="min-w-0"
        isLoading={isPending && !isError}
        isRefetching={isFetching && !isPending}
        loadingFallback={<RemotePageLoadingState label="Chargement des modèles" rows={8} />}
      >
        <QueryRecovery queries={[modelsQuery]} />
        {isError && !canReadPrevious(modelsQuery) ? (
          <RemoteRecoverableErrorState
            description="Le registre des modèles ne répond pas. Les backtests restent consultables ci-dessous."
            onRetry={() => void modelsQuery.refetch()}
            retryDisabled={isFetching}
          />
        ) : models.length === 0 ? (
          <RemoteEmptyState
            description="Aucune version de modèle n’est enregistrée."
            title="Registre vide"
          />
        ) : (
          <div className="grid min-w-0 gap-6">
            <section
              aria-label="Résumé des modèles"
              className="grid grid-cols-3 gap-2 sm:gap-4 max-sm:[&_.ui-metric-label]:text-xs max-sm:[&_.ui-metric-label]:whitespace-nowrap"
            >
              <Card aria-label="Champions">
                <CardContent className="flex items-center justify-between gap-2 p-2 sm:gap-4 sm:p-6">
                  <div>
                    <Metric
                      emphasis="statistic"
                      label="Champions"
                      value={champions.length.toString()}
                    />
                  </div>
                  <ShieldCheck
                    aria-hidden="true"
                    className="hidden size-5 text-ink-secondary sm:block"
                  />
                </CardContent>
              </Card>
              <Card aria-label="Challengers">
                <CardContent className="flex items-center justify-between gap-2 p-2 sm:gap-4 sm:p-6">
                  <div>
                    <Metric
                      emphasis="statistic"
                      label="Challengers"
                      value={challengers.length.toString()}
                    />
                  </div>
                  <GitCompareArrows
                    aria-hidden="true"
                    className="hidden size-5 text-ink-secondary sm:block"
                  />
                </CardContent>
              </Card>
              <Card aria-label="Backtests">
                <CardContent className="flex items-center justify-between gap-2 p-2 sm:gap-4 sm:p-6">
                  <div>
                    <Metric
                      emphasis="statistic"
                      label="Backtests"
                      value={
                        backtestsQuery.isPending
                          ? "…"
                          : canReadPrevious(backtestsQuery)
                            ? backtests.length.toString()
                            : "N/D"
                      }
                    />
                  </div>
                  <CalendarRange
                    aria-hidden="true"
                    className="hidden size-5 text-ink-secondary sm:block"
                  />
                </CardContent>
              </Card>
            </section>

            <nav aria-label="Sections des modèles" className="flex flex-wrap gap-2">
              <Button asChild variant="outline">
                <a href="#model-calibration">Calibration</a>
              </Button>
              <Button asChild variant="outline">
                <a href="#model-champions">Champions</a>
              </Button>
              <Button asChild variant="outline">
                <a href="#model-challengers">Challengers</a>
              </Button>
              {inactive.length > 0 ? (
                <Button asChild variant="outline">
                  <a href="#model-inactive">Versions inactives</a>
                </Button>
              ) : null}
              <Button asChild variant="outline">
                <a href="#model-capabilities">Capacités</a>
              </Button>
              <Button asChild variant="outline">
                <a href="#model-backtests">Backtests</a>
              </Button>
            </nav>

            {referenceModel ? (
              <Panel
                id="model-calibration"
                className="scroll-mt-24"
                tabIndex={-1}
                icon={<ChartColumnIncreasing className="size-4.5" />}
                title="Calibration et comparaison aux baselines"
              >
                <label className="ui-field max-w-xl" htmlFor="comparison-model">
                  <span>Version affichée</span>
                  <Select
                    id="comparison-model"
                    value={referenceModel.modelVersionId}
                    onValueChange={setComparisonModelId}
                  >
                    {models.map((model) => (
                      <option key={model.modelVersionId} value={model.modelVersionId}>
                        {model.modelVersion} · {model.status}
                      </option>
                    ))}
                  </Select>
                </label>
                {Object.keys(referenceModel.metrics).length === 0 ? (
                  <RemoteEmptyState
                    compact
                    title="Métriques indisponibles"
                    description="Aucune mesure de performance n’est enregistrée pour cette version."
                  />
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    {Object.keys(referenceModel.metrics).map((metric) => (
                      <MetricComparison key={metric} metric={metric} model={referenceModel} />
                    ))}
                  </div>
                )}
              </Panel>
            ) : null}

            <Panel
              id="model-champions"
              className="scroll-mt-24"
              tabIndex={-1}
              icon={<ShieldCheck className="size-4.5" />}
              title="Champions actifs"
            >
              {champions.length === 0 ? (
                <RemoteEmptyState
                  compact
                  title="Aucun champion actif"
                  description="Aucun modèle n’est actuellement promu pour produire les prédictions."
                />
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {champions.map((model) => (
                    <ModelCard
                      error={
                        action.error &&
                        "modelVersionId" in action.variables &&
                        action.variables.modelVersionId === model.modelVersionId
                          ? action.error.message
                          : undefined
                      }
                      isPending={action.isPending}
                      key={model.modelVersionId}
                      model={model}
                      onAction={action.mutate}
                      pendingAction={action.variables}
                    />
                  ))}
                </div>
              )}
            </Panel>

            <Panel
              id="model-challengers"
              className="scroll-mt-24"
              tabIndex={-1}
              icon={<GitCompareArrows className="size-4.5" />}
              title="Challengers"
            >
              {challengers.length === 0 ? (
                <p className="rounded-lg border border-border-subtle bg-surface-muted p-4 text-sm text-ink-secondary">
                  Aucun challenger n’est enregistré. Aucune comparaison artificielle n’est créée.
                </p>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {challengers.map((model) => (
                    <ModelCard
                      error={
                        action.error &&
                        "modelVersionId" in action.variables &&
                        action.variables.modelVersionId === model.modelVersionId
                          ? action.error.message
                          : undefined
                      }
                      isPending={action.isPending}
                      key={model.modelVersionId}
                      model={model}
                      onAction={action.mutate}
                      pendingAction={action.variables}
                    />
                  ))}
                </div>
              )}
            </Panel>

            {inactive.length > 0 ? (
              <Panel
                id="model-inactive"
                className="scroll-mt-24"
                tabIndex={-1}
                icon={<CircleAlert className="size-4.5" />}
                title="Versions bloquées et retirées"
              >
                <div className="grid gap-4 md:grid-cols-2">
                  {inactive.map((model) => (
                    <ModelCard
                      error={
                        action.error &&
                        "modelVersionId" in action.variables &&
                        action.variables.modelVersionId === model.modelVersionId
                          ? action.error.message
                          : undefined
                      }
                      isPending={action.isPending}
                      key={model.modelVersionId}
                      model={model}
                      onAction={action.mutate}
                      pendingAction={action.variables}
                    />
                  ))}
                </div>
              </Panel>
            ) : null}

            {modelsQuery.hasNextPage ? (
              <div className="grid gap-2">
                <PagedResults label="de modèles" query={modelsQuery} />
                <p className="text-xs text-ink-secondary">
                  Les résumés portent sur les versions affichées.
                </p>
              </div>
            ) : null}

            <Panel
              id="model-capabilities"
              className="scroll-mt-24"
              tabIndex={-1}
              icon={<CheckCircle2 className="size-4.5" />}
              title="Capacité des marchés"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-border-subtle p-4 text-sm">
                  <p className="font-semibold">Vainqueur du match</p>
                  <p className="mt-1 text-xs text-ink-secondary">
                    Marché pris en charge : MATCH_WINNER. Sa disponibilité dépend de la validation
                    des données, du modèle et des cotes du snapshot.
                  </p>
                  <Link
                    className="mt-2 inline-block text-xs underline underline-offset-4"
                    href="/data"
                  >
                    Vérifier les capacités par snapshot
                  </Link>
                </div>
                <div className="rounded-lg border border-border-subtle p-4 text-sm text-ink-secondary">
                  <p className="font-semibold text-ink-primary">○ Autres marchés LoL</p>
                  <p className="mt-1 text-xs">
                    Désactivés jusqu’à validation complète de leur capability gate.
                  </p>
                </div>
              </div>
            </Panel>
          </div>
        )}
      </RemoteDataBoundary>

      <Panel
        id="model-backtests"
        className="scroll-mt-24"
        tabIndex={-1}
        icon={<CalendarRange className="size-4.5" />}
        title="Performance temporelle et segments"
      >
        <QueryRecovery queries={[backtestsQuery]} />
        {backtestsQuery.isError && !canReadPrevious(backtestsQuery) ? (
          <RemoteRecoverableErrorState
            title="Backtests indisponibles"
            description="L’historique des validations peut être rechargé indépendamment du registre des modèles."
            onRetry={() => void backtestsQuery.refetch()}
            retryDisabled={backtestsQuery.isFetching}
          />
        ) : (
          <RemoteDataBoundary
            isLoading={backtestsQuery.isPending}
            isRefetching={backtestsQuery.isFetching && !backtestsQuery.isPending}
            loadingFallback={<RemoteLoadingState label="Chargement des backtests" rows={4} />}
          >
            {backtests.length === 0 ? (
              <RemoteEmptyState
                compact
                title="Aucun backtest"
                description="Les résultats apparaîtront après la validation d’une version."
              />
            ) : (
              <BacktestTable
                backtests={backtests}
                models={canReadPrevious(modelsQuery) ? models : []}
              />
            )}
            <PagedResults label="de backtests" query={backtestsQuery} />
            {backtests.some((backtest) => backtest.sampleCount < 500) ? (
              <p className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs leading-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
                <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                Les backtests de moins de 500 observations sont signalés comme faible échantillon et
                ne suffisent pas, seuls, à une promotion.
              </p>
            ) : null}
          </RemoteDataBoundary>
        )}
      </Panel>
    </div>
  );
}
