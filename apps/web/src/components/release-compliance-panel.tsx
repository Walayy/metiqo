"use client";

import type { ReleaseCompliance } from "@metiquo/contracts/types";
import { Badge, Card, CardContent, RemoteRecoverableErrorState } from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
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
      <CardContent className="grid min-h-64 content-start gap-4 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Portes de publication</h2>
        {status.isError ? (
          <RemoteRecoverableErrorState
            title="Publication bloquée : état indisponible"
            description="La validation des portes n’a pas pu être confirmée."
            onRetry={() => void status.refetch()}
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
                <Badge key={name}>
                  {name} : {state}
                </Badge>
              ))}
            </div>
            <p className="text-sm font-medium">
              {status.data.publicReleaseAllowed
                ? "Preuves manuelles vérifiées ; prévol à rejouer avant chaque publication."
                : "Publication publique ou commerciale bloquée."}
            </p>
            <p className="text-sm text-ink-secondary">Provider Stake désactivé.</p>
          </>
        ) : (
          <p role="status" className="text-sm text-ink-secondary">
            Vérification des portes en cours…
          </p>
        )}
        <p className="text-sm leading-6 text-ink-secondary">
          Les autorisations écrites des sources et la revue du produit sont nécessaires avant toute
          ouverture à des tiers. Metiquo n’est ni affilié à Riot Games ni approuvé par Riot Games.
        </p>
      </CardContent>
    </Card>
  );
}
