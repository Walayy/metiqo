"use client";

import type { ReleaseCompliance } from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  ContextPanel,
  RemoteRecoverableErrorState,
  RemoteLoadingState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { readBackend } from "../lib/backend";

export function ReleaseCompliancePanel() {
  const status = useQuery({
    queryKey: ["system", "compliance"],
    queryFn: async ({ signal }): Promise<ReleaseCompliance> => {
      const response = await readBackend("/api/backend/api/v1/system/compliance", { signal });
      return (await response.json()) as ReleaseCompliance;
    },
  });
  return (
    <Card aria-label="Portes de publication">
      <CardContent className="grid min-h-64 content-start gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Portes de publication</h2>
          <Button
            aria-busy={status.isFetching}
            disabled={status.isFetching}
            onClick={() => void status.refetch()}
            variant="outline"
          >
            {status.isFetching ? "Vérification…" : "Vérifier les conditions"}
          </Button>
        </div>
        {status.isError ? (
          <RemoteRecoverableErrorState
            title="Publication bloquée : état indisponible"
            description="La validation des portes n’a pas pu être confirmée."
            onRetry={() => void status.refetch()}
            retryDisabled={status.isFetching}
          />
        ) : status.data ? (
          <>
            <p className="text-sm text-ink-secondary">
              {status.data.audience === "personal"
                ? "Usage personnel."
                : "Audience soumise à une revue manuelle."}
            </p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(status.data.gates).map(([name, state]) => (
                <Badge
                  className={
                    state === "GO"
                      ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                      : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
                  }
                  key={name}
                >
                  {name} : {state}
                </Badge>
              ))}
            </div>
            <p className="text-xs leading-5 text-ink-secondary">
              GO : condition validée. NO-GO : condition non validée, publication bloquée.
            </p>
            <ContextPanel tone={status.data.publicReleaseAllowed ? "success" : "warning"}>
              {status.data.publicReleaseAllowed
                ? "Preuves manuelles vérifiées ; prévol à rejouer avant chaque publication."
                : "Publication publique ou commerciale bloquée."}
            </ContextPanel>
            <Link href="/odds" className="text-sm text-ink-secondary underline underline-offset-4">
              Consulter l’état de la collecte Stake
            </Link>
          </>
        ) : (
          <RemoteLoadingState label="Vérification des portes en cours" minHeight="10rem" rows={3} />
        )}
        <p className="text-sm leading-6 text-ink-secondary">
          Les autorisations écrites des sources et la revue du produit sont nécessaires avant toute
          ouverture à des tiers. Metiquo n’est ni affilié à Riot Games ni approuvé par Riot Games.
        </p>
      </CardContent>
    </Card>
  );
}
