"use client";

import type { OperationalStatus, SystemStatusResponse } from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  RemoteLoadingState,
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

function Measurements({ operations }: Readonly<{ operations: OperationalStatus }>) {
  const { source, model, metrics, backups } = operations;
  const states = [
    {
      name: "Source historique",
      status: labels[source.status],
      detail: source.asOf ? `Confirmée le ${formatDateTime(source.asOf)}` : "Aucune confirmation",
      reason: source.reasonCode,
    },
    {
      name: "Modèle champion",
      status: labels[model.status],
      detail: model.trainingCutoff
        ? `Données jusqu’au ${formatDateTime(model.trainingCutoff)}`
        : "Aucun modèle actif",
    },
    {
      name: "Jobs",
      status: `${String(operations.jobCounts.running ?? 0)} en cours`,
      detail: `${String(operations.jobCounts.queued ?? 0)} en attente · ${String(metrics.jobFailures)} échecs conservés`,
    },
    {
      name: "Mapping à examiner",
      status: String(operations.mappingBacklog),
      detail: "Revues en attente",
    },
    {
      name: "Qualité des données",
      status: `${String(metrics.blockingAnomalies)} anomalies bloquantes`,
      detail: `${String(metrics.anomalies)} anomalies conservées`,
    },
    {
      name: "Sauvegardes",
      status: labels[backups.status],
      detail: backups.lastSuccessAt
        ? `Dernier succès le ${formatDateTime(backups.lastSuccessAt)}`
        : "Aucun succès enregistré",
    },
  ];
  return (
    <div className="grid gap-4">
      <p className="text-sm font-medium">
        {operations.readsAvailable
          ? "Snapshot validé disponible en lecture"
          : "Aucun snapshot courant utilisable"}
      </p>
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {states.map((state) => (
          <div
            className="grid content-start gap-1 rounded-lg border border-border-subtle p-3"
            key={state.name}
          >
            <dt className="text-xs text-ink-secondary">{state.name}</dt>
            <dd className="text-sm font-semibold">{state.status}</dd>
            <dd className="text-xs text-ink-secondary">{state.detail}</dd>
            {state.reason ? (
              <dd className="break-all text-xs text-ink-secondary">{state.reason}</dd>
            ) : null}
          </div>
        ))}
      </dl>
      <p className="text-xs leading-5 text-ink-secondary">
        Historique conservé : {metrics.processedRows} lignes chargées · durée moyenne des jobs{" "}
        {metrics.meanJobDurationSeconds === null || metrics.meanJobDurationSeconds === undefined
          ? "non mesurée"
          : `${metrics.meanJobDurationSeconds.toFixed(2)} s`}{" "}
        ({metrics.measuredJobCount} mesurés). Signaux :{" "}
        {Object.entries(metrics.signals)
          .map(([grade, count]) => `${grade} ${String(count)}`)
          .join(" · ")}
        .
      </p>
      <p className="text-xs leading-5 text-ink-secondary">
        Depuis le démarrage de ce processus API : {metrics.api.requestCount} requêtes ·{" "}
        {metrics.api.failureCount} erreurs serveur · latence moyenne{" "}
        {metrics.api.meanLatencyMs === null || metrics.api.meanLatencyMs === undefined
          ? "non mesurée"
          : `${metrics.api.meanLatencyMs.toFixed(1)} ms`}
        .
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
        ) : status.isPending ? (
          <RemoteLoadingState minHeight="12rem" />
        ) : status.data.operations ? (
          <Measurements operations={status.data.operations} />
        ) : (
          <p className="text-sm text-ink-secondary">
            {status.data.dataMode === "mock"
              ? "Les mesures opérationnelles réelles sont disponibles en mode réel."
              : "La base est indisponible ; les mesures ne peuvent pas être lues."}
          </p>
        )}
        {status.data ? (
          <p className="flex flex-wrap items-center gap-2 text-xs text-ink-secondary">
            <Badge>{status.data.dataMode}</Badge>Mesure du {formatDateTime(status.data.generatedAt)}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
