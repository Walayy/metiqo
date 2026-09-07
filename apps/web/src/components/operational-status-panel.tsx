"use client";

import type { OperationalStatus, SystemStatusResponse } from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  RemoteSkeleton,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";

import { formatDateTime } from "./opportunity-presenters";

const labels: Record<string, string> = {
  fresh: "À jour",
  stale: "Périmé",
  degraded: "Dégradé",
  failed: "En échec",
  quarantined: "En quarantaine",
  missing: "Absent",
  invalid: "Invalide",
  not_configured: "Non configurées",
};

function Measurements({
  operations,
  pending = false,
  dataMode,
}: Readonly<{
  operations?: OperationalStatus | null;
  pending?: boolean;
  dataMode?: string;
}>) {
  const { source, model, metrics, backups } = operations ?? {};
  const states = [
    {
      name: "Source historique",
      status: source ? labels[source.status] : "Indisponible",
      detail: source?.asOf ? `Confirmée le ${formatDateTime(source.asOf)}` : "Aucune confirmation",
      reason: source?.reasonCode,
    },
    {
      name: "Modèle champion",
      status: model ? labels[model.status] : "Indisponible",
      detail: model?.trainingCutoff
        ? `Données jusqu’au ${formatDateTime(model.trainingCutoff)}`
        : "Aucun modèle actif",
    },
    {
      name: "Jobs",
      status: operations ? `${String(operations.jobCounts.running ?? 0)} en cours` : "Indisponible",
      detail: operations
        ? `${String(operations.jobCounts.queued ?? 0)} en attente · ${String(operations.metrics.jobFailures)} échecs conservés`
        : "Aucune mesure réelle",
    },
    {
      name: "Mapping à examiner",
      status: operations ? String(operations.mappingBacklog) : "Indisponible",
      detail: "Revues en attente",
    },
    {
      name: "Qualité des données",
      status: metrics
        ? `${String(metrics.blockingAnomalies)} anomalies bloquantes`
        : "Indisponible",
      detail: metrics
        ? `${String(metrics.anomalies)} anomalies conservées`
        : "Aucune mesure réelle",
    },
    {
      name: "Sauvegardes",
      status: backups ? labels[backups.status] : "Indisponible",
      reason: backups?.errorCode,
      detail: backups?.lastSuccessAt
        ? `Dernier succès le ${formatDateTime(backups.lastSuccessAt)}`
        : "Aucun succès enregistré",
    },
  ];
  return (
    <div aria-busy={pending} className="grid gap-4">
      <p className="min-h-15 text-sm leading-5 font-medium sm:min-h-10 xl:min-h-5" role="status">
        {pending
          ? "Chargement des mesures…"
          : !operations
            ? dataMode === "mock"
              ? "Les mesures opérationnelles réelles sont disponibles en mode réel."
              : "La base est indisponible ; les mesures ne peuvent pas être lues."
            : operations.readsAvailable
              ? "Snapshot validé disponible en lecture"
              : "Aucun snapshot courant utilisable"}
      </p>
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {states.map((state) => (
          <div
            className="grid content-start gap-1 rounded-lg border border-border-subtle p-3"
            key={state.name}
          >
            <dt className="text-xs leading-4 text-ink-secondary">{state.name}</dt>
            <dd className="min-h-5 text-sm leading-5 font-semibold">
              {pending ? <RemoteSkeleton height="1.25rem" width="65%" /> : state.status}
            </dd>
            <dd className="min-h-8 text-xs leading-4 text-ink-secondary">
              {pending ? <RemoteSkeleton width="90%" /> : state.detail}
            </dd>
            <dd className="min-h-4 break-all text-xs leading-4 text-ink-secondary">
              {pending ? <RemoteSkeleton width="45%" /> : state.reason}
            </dd>
          </div>
        ))}
      </dl>
      <p className="min-h-20 text-xs leading-5 text-ink-secondary sm:min-h-10 xl:min-h-5">
        {pending ? (
          <RemoteSkeleton width="90%" />
        ) : metrics ? (
          <>
            Historique conservé : {metrics.processedRows} lignes chargées · durée moyenne des jobs{" "}
            {metrics.meanJobDurationSeconds === null || metrics.meanJobDurationSeconds === undefined
              ? "non mesurée"
              : `${metrics.meanJobDurationSeconds.toFixed(2)} s`}{" "}
            ({metrics.measuredJobCount} mesurés). Signaux :{" "}
            {Object.entries(metrics.signals)
              .map(([grade, count]) => `${grade} ${String(count)}`)
              .join(" · ")}
            .
          </>
        ) : (
          "Les compteurs et durées apparaîtront après la collecte de mesures réelles."
        )}
      </p>
      <p className="min-h-15 text-xs leading-5 text-ink-secondary sm:min-h-10 xl:min-h-5">
        {pending ? (
          <RemoteSkeleton width="75%" />
        ) : metrics ? (
          <>
            Depuis le démarrage de ce processus API : {metrics.api.requestCount} requêtes ·{" "}
            {metrics.api.failureCount} erreurs serveur · latence moyenne{" "}
            {metrics.api.meanLatencyMs === null || metrics.api.meanLatencyMs === undefined
              ? "non mesurée"
              : `${metrics.api.meanLatencyMs.toFixed(1)} ms`}
            .
          </>
        ) : (
          "Aucune latence API réelle n’a été mesurée dans ce mode."
        )}
      </p>
    </div>
  );
}

export function OperationalStatusPanel() {
  const status = useQuery({
    queryKey: ["admin", "system-status"],
    queryFn: async ({ signal }): Promise<SystemStatusResponse> => {
      const response = await fetch("/api/backend/api/v1/system/status", { signal });
      if (!response.ok) throw new Error("État opérationnel indisponible");
      return (await response.json()) as SystemStatusResponse;
    },
  });
  return (
    <Card aria-label="État opérationnel">
      <CardContent className="grid content-start gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight">État opérationnel</h2>
          <Button disabled={status.isFetching} onClick={() => void status.refetch()}>
            Actualiser l’état
          </Button>
        </div>
        {status.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void status.refetch()} />
        ) : (
          <Measurements
            operations={status.data?.operations ?? null}
            pending={status.isPending}
            dataMode={status.data?.dataMode ?? ""}
          />
        )}
        <p className="flex min-h-6 flex-wrap items-center gap-2 text-xs text-ink-secondary">
          {status.data ? (
            <>
              <Badge>{status.data.dataMode}</Badge>Mesure du{" "}
              {formatDateTime(status.data.generatedAt)}
            </>
          ) : (
            <RemoteSkeleton width="14rem" />
          )}
        </p>
      </CardContent>
    </Card>
  );
}
