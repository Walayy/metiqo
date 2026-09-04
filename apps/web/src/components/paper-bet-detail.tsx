"use client";

import type { ItemResponsePaperBet } from "@metiquo/contracts/types";
import {
  Button,
  Card,
  CardContent,
  RemoteBlockingErrorState,
  RemoteDataBoundary,
  RemoteLoadingState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical } from "lucide-react";
import Link from "next/link";

import { formatDateTime } from "./opportunity-presenters";
import { PaperStatusBadge, ProfitLoss } from "./paper-trading-dashboard";

async function getPaperBet(paperBetId: string, signal: AbortSignal) {
  const response = await fetch(`/api/backend/api/v1/paper-bets/${encodeURIComponent(paperBetId)}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Paper bet introuvable");
  return (await response.json()) as ItemResponsePaperBet;
}

export function PaperBetDetail({ paperBetId }: Readonly<{ paperBetId: string }>) {
  const paperBet = useQuery({
    queryFn: ({ signal }) => getPaperBet(paperBetId, signal),
    queryKey: ["paper-bet", paperBetId],
  });

  if (paperBet.isError) {
    return (
      <RemoteBlockingErrorState
        action={
          <Button asChild variant="outline">
            <Link href="/paper-trading">Retour au paper trading</Link>
          </Button>
        }
        description="Cette décision paper n’existe pas dans le catalogue de lecture courant."
        title="Paper bet introuvable"
      />
    );
  }

  return (
    <RemoteDataBoundary
      isLoading={paperBet.isPending}
      loadingFallback={<RemoteLoadingState minHeight="32rem" rows={8} />}
    >
      {paperBet.data ? (
        <div className="grid gap-6 sm:gap-8">
          <header className="grid gap-3">
            <Button asChild className="w-fit" size="small" variant="ghost">
              <Link href="/paper-trading">
                <ArrowLeft aria-hidden="true" className="size-4" /> Retour
              </Link>
            </Button>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
              Décision simulée
            </p>
            <h1 className="break-all text-3xl font-semibold tracking-tight">Paper bet</h1>
            <p className="break-all text-sm text-ink-secondary">{paperBet.data.data.paperBetId}</p>
          </header>

          <div
            className="flex items-start gap-3 rounded-xl border border-accent bg-accent-soft p-4 text-sm leading-6"
            role="note"
          >
            <FlaskConical aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            Aucune exécution réelle : cette fiche retrace uniquement une décision paper.
          </div>

          <Card aria-label="Détail du paper bet">
            <CardContent className="grid gap-5 p-5 sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xl font-semibold">Décision et règlement</h2>
                <PaperStatusBadge status={paperBet.data.data.status} />
              </div>
              <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-xs text-ink-secondary">Mise fictive</dt>
                  <dd className="mt-1 font-semibold">
                    {paperBet.data.data.stakeAmount} {paperBet.data.data.currency}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-secondary">Cote d’entrée</dt>
                  <dd className="mt-1 font-semibold">{paperBet.data.data.entryOdds}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-secondary">P&L</dt>
                  <dd className="mt-1">
                    <ProfitLoss bet={paperBet.data.data} />
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-secondary">Créé le</dt>
                  <dd className="mt-1 font-semibold">
                    {formatDateTime(paperBet.data.data.placedAt)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-secondary">Réglé le</dt>
                  <dd className="mt-1 font-semibold">
                    {paperBet.data.data.settledAt
                      ? formatDateTime(paperBet.data.data.settledAt)
                      : "Non réglé"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-secondary">Règles versionnées</dt>
                  <dd className="mt-1 font-semibold">
                    {paperBet.data.data.settlementRulesVersion}
                  </dd>
                </div>
              </dl>
              <div className="grid gap-2 rounded-lg bg-surface-muted p-4 text-sm">
                <p>
                  <strong>Motif :</strong> {paperBet.data.data.settlementReason ?? "En attente"}
                </p>
                <p className="break-all">
                  <strong>Snapshot d’entrée :</strong> {paperBet.data.data.oddsSnapshotId}
                </p>
                <p className="break-all">
                  <strong>Snapshot de clôture :</strong>{" "}
                  {paperBet.data.data.closingOddsSnapshotId ?? "Non disponible"}
                </p>
              </div>
              <Button asChild className="w-fit" variant="outline">
                <Link href={`/opportunities/${encodeURIComponent(paperBet.data.data.signalId)}`}>
                  Ouvrir le signal source
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </RemoteDataBoundary>
  );
}
