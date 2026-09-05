"use client";

import type {
  BacktestSummary,
  ItemResponseModelSummary,
  ModelSummary,
  PageResponseBacktestSummary,
  PageResponseModelSummary,
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
} from "@metiquo/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import type { ReactNode } from "react";

import { formatDateTime, formatDecimal } from "./opportunity-presenters";

async function fetchResource<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Les modèles ne sont pas disponibles");
  return (await response.json()) as T;
}

type ModelAction = { action: "train" } | { action: "promote" | "retire"; modelVersionId: string };

async function runModelAction(request: ModelAction): Promise<ItemResponseModelSummary> {
  const endpoint =
    request.action === "train"
      ? "/api/v1/admin/models/train"
      : `/api/v1/admin/models/${request.modelVersionId}/${request.action}`;
  const body =
    request.action === "train"
      ? { gameTitle: "lol", marketType: "MATCH_WINNER" }
      : {
          reason:
            request.action === "promote"
              ? "Promotion manuelle depuis le tableau des modèles"
              : "Retrait manuel depuis le tableau des modèles",
        };
  const response = await fetch(`/api/backend${endpoint}`, {
    body: JSON.stringify(body),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    method: "POST",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? "La décision sur le modèle a échoué");
  }
  return (await response.json()) as ItemResponseModelSummary;
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

function metricLabel(metric: string) {
  if (metric === "log_loss") return "Log loss";
  if (metric === "brier") return "Score de Brier";
  return metric.replaceAll("_", " ");
}

function MetricComparison({ model, metric }: Readonly<{ model: ModelSummary; metric: string }>) {
  const value = Number(model.metrics[metric] ?? 0);
  const baselineValue = model.baselineMetrics[metric];
  const baseline = baselineValue === undefined ? null : Number(baselineValue);
  const summary = `${metricLabel(metric)} : modèle ${formatDecimal(value)}, baseline ${baseline === null ? "non disponible" : formatDecimal(baseline)}. Une valeur plus basse est préférable.`;
  const maximum = Math.max(value, baseline ?? 0, 0.01);

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
            <div className="grid grid-cols-[5rem_1fr_auto] items-center gap-2 text-xs" key={label}>
              <span>{label}</span>
              <span className="h-2 overflow-hidden rounded-full bg-surface-muted">
                <span
                  className={`block h-full rounded-full ${tone}`}
                  style={{ width: `${Math.max((numericValue / maximum) * 100, 2).toFixed(2)}%` }}
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
  isPending,
  model,
  onAction,
}: Readonly<{
  isPending: boolean;
  model: ModelSummary;
  onAction: (request: ModelAction) => void;
}>) {
  const badgeTone =
    model.status === "champion"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
      : model.status === "candidate"
        ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
        : "border-border-strong bg-surface-muted text-ink-secondary";
  return (
    <Card aria-label={`Modèle ${model.modelVersion}`}>
      <CardContent className="grid h-full gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
              {model.algorithm}
            </p>
            <h3 className="mt-1 break-all font-semibold">{model.modelVersion}</h3>
          </div>
          <Badge className={badgeTone}>
            <CheckCircle2 aria-hidden="true" className="mr-1 size-3.5" />
            {model.status}
          </Badge>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-secondary">Log loss</dt>
            <dd className="mt-1 font-semibold">{formatDecimal(model.metrics.log_loss ?? 0)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Brier / calibration</dt>
            <dd className="mt-1 font-semibold">{formatDecimal(model.metrics.brier ?? 0)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Marché</dt>
            <dd className="mt-1 font-semibold">Vainqueur du match</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Features</dt>
            <dd className="mt-1 font-semibold">{model.featureVersion}</dd>
          </div>
        </dl>
        <div className="rounded-lg border border-border-subtle p-3 text-xs leading-5">
          <p className="font-semibold">Version exacte de prédiction</p>
          <p className="mt-1 break-all font-mono text-ink-secondary">{model.modelVersionId}</p>
        </div>
        <div className="mt-auto rounded-lg bg-surface-muted p-3 text-xs leading-5 text-ink-secondary">
          <p className="font-semibold text-ink-primary">Promotion</p>
          <p>{model.promotionReason ?? "Aucune promotion enregistrée"}</p>
          {model.promotedAt ? <p>{formatDateTime(model.promotedAt)}</p> : null}
        </div>
        {model.status === "candidate" || model.status === "champion" ? (
          <div className="flex flex-wrap gap-2">
            {model.status === "candidate" ? (
              <Button
                disabled={isPending}
                onClick={() => {
                  onAction({ action: "promote", modelVersionId: model.modelVersionId });
                }}
                size="small"
              >
                <ShieldCheck aria-hidden="true" className="size-4" />
                Promouvoir
              </Button>
            ) : null}
            <Button
              disabled={isPending}
              onClick={() => {
                onAction({ action: "retire", modelVersionId: model.modelVersionId });
              }}
              size="small"
              variant="outline"
            >
              Retirer
            </Button>
          </div>
        ) : null}
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
    <div
      aria-label="Performance temporelle des backtests"
      className="max-w-full overflow-x-auto rounded-lg border border-border-subtle"
      role="region"
      tabIndex={0}
    >
      <table className="w-full min-w-[64rem] border-collapse text-left text-xs">
        <thead className="bg-surface-muted text-ink-secondary">
          <tr>
            {[
              "Version",
              "Période walk-forward",
              "Échantillon",
              "Log loss",
              "Baseline",
              "Brier",
              "Test final",
              "Segment",
            ].map((label) => (
              <th className="px-3 py-3 font-semibold" key={label} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {backtests.map((backtest) => (
            <tr key={backtest.backtestId}>
              <td className="max-w-52 break-all px-3 py-3 font-semibold">
                {versions.get(backtest.modelVersionId) ?? backtest.modelVersionId}
              </td>
              <td className="whitespace-nowrap px-3 py-3">
                {formatDateTime(backtest.startsAt)} – {formatDateTime(backtest.endsAt)}
              </td>
              <td className="px-3 py-3">
                <span className="font-semibold">{backtest.sampleCount.toString()}</span>
                {backtest.sampleCount < 500 ? (
                  <span className="mt-1 block text-amber-700 dark:text-amber-300">
                    ⚠ Faible échantillon
                  </span>
                ) : null}
              </td>
              <td className="px-3 py-3">{formatDecimal(backtest.metrics.log_loss ?? 0)}</td>
              <td className="px-3 py-3">{formatDecimal(backtest.baselineMetrics.log_loss ?? 0)}</td>
              <td className="px-3 py-3">{formatDecimal(backtest.metrics.brier ?? 0)}</td>
              <td className="px-3 py-3">
                {backtest.finalTestUntouched ? "Préservé" : "Non préservé"}
              </td>
              <td className="px-3 py-3">Game winner · global</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ModelsDashboard() {
  const queryClient = useQueryClient();
  const modelsQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<PageResponseModelSummary>("/api/v1/models?offset=0&limit=100", signal),
    queryKey: ["models"],
  });
  const backtestsQuery = useQuery({
    queryFn: ({ signal }) =>
      fetchResource<PageResponseBacktestSummary>("/api/v1/backtests?offset=0&limit=100", signal),
    queryKey: ["backtests"],
  });
  const isPending = modelsQuery.isPending || backtestsQuery.isPending;
  const isFetching = modelsQuery.isFetching || backtestsQuery.isFetching;
  const isError = modelsQuery.isError || backtestsQuery.isError;
  const models = modelsQuery.data?.data ?? [];
  const backtests = backtestsQuery.data?.data ?? [];
  const champions = models.filter((model) => model.status === "champion");
  const challengers = models.filter((model) => model.status === "candidate");
  const referenceModel = champions.at(0) ?? models.at(0);
  const action = useMutation({
    mutationFn: runModelAction,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["models"] }),
        queryClient.invalidateQueries({ queryKey: ["backtests"] }),
      ]);
    },
  });

  return (
    <div className="grid min-w-0 gap-7">
      <header className="grid max-w-3xl gap-2">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
          <Activity aria-hidden="true" className="size-4" />
          Validation hors échantillon
        </p>
        <h1 className="text-title text-balance font-semibold tracking-tight">
          Modèles & backtests
        </h1>
        <p className="text-body max-w-2xl text-ink-secondary">
          Versions traçables, calibration, baselines et validation walk-forward. Une métrique plus
          basse n’efface jamais l’incertitude d’échantillonnage.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={action.isPending}
            onClick={() => {
              action.mutate({ action: "train" });
            }}
          >
            {action.isPending ? (
              <RefreshCw
                aria-hidden="true"
                className="size-4 animate-spin motion-reduce:animate-none"
              />
            ) : (
              <Play aria-hidden="true" className="size-4" />
            )}
            Entraîner un candidat
          </Button>
          {action.data ? (
            <p aria-live="polite" className="text-sm text-emerald-700" role="status">
              Action terminée · {action.data.data.status} · {action.data.data.modelVersion}
            </p>
          ) : null}
          {action.error ? (
            <p className="text-sm text-red-700" role="alert">
              {action.error.message}
            </p>
          ) : null}
        </div>
      </header>

      <RemoteDataBoundary
        className="min-w-0"
        isLoading={isPending}
        isRefetching={isFetching && !isPending}
        loadingFallback={<RemoteLoadingState label="Chargement des modèles" rows={8} />}
      >
        {isError ? (
          <RemoteRecoverableErrorState
            description="Le registre ou les backtests ne répondent pas."
            onRetry={() => void Promise.all([modelsQuery.refetch(), backtestsQuery.refetch()])}
          />
        ) : models.length === 0 ? (
          <RemoteEmptyState
            description="Aucune version de modèle n’est enregistrée."
            title="Registre vide"
          />
        ) : (
          <div className="grid min-w-0 gap-6">
            <section aria-label="Résumé des modèles" className="grid gap-4 sm:grid-cols-3">
              <Card aria-label="Champions">
                <CardContent className="flex items-center justify-between gap-4 p-5">
                  <div>
                    <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
                      Champions
                    </p>
                    <p className="mt-2 text-2xl font-semibold">{champions.length.toString()}</p>
                  </div>
                  <ShieldCheck aria-hidden="true" className="size-5 text-ink-secondary" />
                </CardContent>
              </Card>
              <Card aria-label="Challengers">
                <CardContent className="flex items-center justify-between gap-4 p-5">
                  <div>
                    <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
                      Challengers
                    </p>
                    <p className="mt-2 text-2xl font-semibold">{challengers.length.toString()}</p>
                  </div>
                  <GitCompareArrows aria-hidden="true" className="size-5 text-ink-secondary" />
                </CardContent>
              </Card>
              <Card aria-label="Backtests">
                <CardContent className="flex items-center justify-between gap-4 p-5">
                  <div>
                    <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
                      Backtests
                    </p>
                    <p className="mt-2 text-2xl font-semibold">{backtests.length.toString()}</p>
                  </div>
                  <CalendarRange aria-hidden="true" className="size-5 text-ink-secondary" />
                </CardContent>
              </Card>
            </section>

            <Panel icon={<ShieldCheck className="size-4.5" />} title="Champions actifs">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {champions.map((model) => (
                  <ModelCard
                    isPending={action.isPending}
                    key={model.modelVersionId}
                    model={model}
                    onAction={action.mutate}
                  />
                ))}
              </div>
            </Panel>

            <Panel icon={<GitCompareArrows className="size-4.5" />} title="Challengers">
              {challengers.length === 0 ? (
                <p className="rounded-lg border border-border-subtle bg-surface-muted p-4 text-sm text-ink-secondary">
                  Aucun challenger n’est enregistré. Aucune comparaison artificielle n’est créée.
                </p>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {challengers.map((model) => (
                    <ModelCard
                      isPending={action.isPending}
                      key={model.modelVersionId}
                      model={model}
                      onAction={action.mutate}
                    />
                  ))}
                </div>
              )}
            </Panel>

            {referenceModel ? (
              <Panel
                icon={<ChartColumnIncreasing className="size-4.5" />}
                title="Calibration et comparaison aux baselines"
              >
                <p className="text-sm text-ink-secondary">
                  Version affichée :{" "}
                  <strong className="text-ink-primary">{referenceModel.modelVersion}</strong>
                </p>
                <div className="grid gap-4 md:grid-cols-2">
                  {Object.keys(referenceModel.metrics).map((metric) => (
                    <MetricComparison key={metric} metric={metric} model={referenceModel} />
                  ))}
                </div>
              </Panel>
            ) : null}

            <Panel
              icon={<CalendarRange className="size-4.5" />}
              title="Performance temporelle et segments"
            >
              <BacktestTable backtests={backtests} models={models} />
              {backtests.some((backtest) => backtest.sampleCount < 500) ? (
                <p className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs leading-5 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
                  <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                  Les backtests de moins de 500 observations sont signalés comme faible échantillon
                  et ne suffisent pas, seuls, à une promotion.
                </p>
              ) : null}
            </Panel>

            <Panel icon={<CheckCircle2 className="size-4.5" />} title="Capacité des marchés">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
                  <p className="font-semibold">✓ Vainqueur du match</p>
                  <p className="mt-1 text-xs">Capacité contractuelle active : MATCH_WINNER.</p>
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
    </div>
  );
}
