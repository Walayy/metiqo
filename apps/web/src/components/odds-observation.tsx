"use client";

import type { OddsSnapshot, Opportunity } from "@metiquo/contracts/types";
import { InlineValues, TableCellContent } from "@metiquo/ui";

import {
  formatDecimal,
  formatDateTime,
  latestMatchingOddsSnapshot,
  newerOddsSnapshot,
} from "./opportunity-presenters";

/** One presentation for both list and card views, retaining the signal's original price. */
export function OddsObservation({
  history,
  opportunity,
}: Readonly<{
  history: readonly OddsSnapshot[] | undefined;
  opportunity: Opportunity;
}>) {
  const latest = history ? latestMatchingOddsSnapshot(opportunity, history) : undefined;
  const updated = latest && history && newerOddsSnapshot(opportunity, history) ? latest : undefined;
  const difference = updated
    ? Number(updated.decimalOdds) - Number(opportunity.book.decimalOdds)
    : 0;
  const stable = Math.abs(difference) < 0.005;
  const movement = stable
    ? "→ Stable"
    : `${difference > 0 ? "↑ Hausse" : "↓ Baisse"} ${formatDecimal(Math.abs(difference))}`;
  const movementTone = stable
    ? "text-ink-secondary"
    : difference > 0
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-red-700 dark:text-red-300";

  return (
    <TableCellContent
      aria-label={`Cote observée pour ${opportunity.event.teamA} contre ${opportunity.event.teamB}`}
      aria-live="polite"
      aria-atomic="true"
      role="status"
      primary={
        <span className="tabular-nums">
          <span className="sr-only">Cote du signal : </span>
          {formatDecimal(opportunity.book.decimalOdds)}
        </span>
      }
      secondary={
        updated ? (
          <>
            <p>Cote mise à jour</p>
            <InlineValues
              items={[
                <span className="font-medium tabular-nums" key="updated">
                  {formatDecimal(updated.decimalOdds)}
                </span>,
                <span className={`whitespace-nowrap ${movementTone}`} key="movement">
                  {movement}
                </span>,
              ]}
            />
            <p>Relevée le {formatDateTime(updated.capturedAt)}</p>
            {updated.informationalOnly ? <p>Information uniquement</p> : null}
            {updated.providerStatus !== "operational" ? (
              <p>
                {
                  {
                    degraded: "Source dégradée",
                    unavailable: "Source indisponible",
                    disabled: "Source désactivée",
                  }[updated.providerStatus]
                }
              </p>
            ) : null}
            {updated.marketStatus !== "open" ? (
              <p>
                {
                  {
                    suspended: "Marché suspendu",
                    closed: "Marché fermé",
                    settled: "Marché réglé",
                    void: "Marché annulé",
                  }[updated.marketStatus]
                }
              </p>
            ) : null}
          </>
        ) : !history ? (
          "Vérification…"
        ) : !latest ? (
          "Aucun nouveau relevé disponible"
        ) : (
          "Cote enregistrée avec le signal"
        )
      }
    />
  );
}
