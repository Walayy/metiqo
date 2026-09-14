"use client";

import { BackendReadError, canReadPrevious, readBackend } from "../lib/backend";
import { QueryFailure, QueryRecovery } from "./query-recovery";

import type { ItemResponseOpportunity, ItemResponsePaperBet } from "@metiquo/contracts/types";
import {
  Button,
  Card,
  CardContent,
  Metric,
  MetricGrid,
  TechnicalText,
  RemoteBlockingErrorState,
  RemoteDataBoundary,
  RemotePageLoadingState,
  RemoteRecoverableErrorState,
  RemotePermissionDeniedState,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical } from "lucide-react";
import Link from "next/link";

import { formatDateTime, formatDecimal } from "./opportunity-presenters";
import {
  formatMoney,
  PaperStatusBadge,
  ProfitLoss,
  SettlementForm,
} from "./paper-trading-dashboard";
import { RealPaperSettlement } from "./real-paper-settlement";

async function getPaperBet(paperBetId: string, signal: AbortSignal) {
  const response = await readBackend(
    `/api/backend/api/v1/paper-bets/${encodeURIComponent(paperBetId)}`,
    {
      headers: { accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) throw new Error("Paper bet introuvable");
  return (await response.json()) as ItemResponsePaperBet;
}

export function PaperBetDetail({ paperBetId }: Readonly<{ paperBetId: string }>) {
  const paperBet = useQuery({
    queryFn: ({ signal }) => getPaperBet(paperBetId, signal),
    queryKey: ["paper-bet", paperBetId],
    refetchInterval: 30_000,
  });
  const bet = paperBet.data?.data;
  const sourceSignalId = bet ? bet.signalId : undefined;
  const sourceSignal = useQuery({
    enabled: Boolean(sourceSignalId) && canReadPrevious(paperBet),
    queryKey: ["opportunity", sourceSignalId],
    staleTime: Infinity,
    queryFn: async ({ signal }): Promise<ItemResponseOpportunity> => {
      const response = await readBackend(
        `/api/backend/api/v1/opportunities/${encodeURIComponent(sourceSignalId ?? "")}`,
        { signal },
      );
      return (await response.json()) as ItemResponseOpportunity;
    },
  });
  const source = canReadPrevious(sourceSignal) ? sourceSignal.data?.data : undefined;

  if (paperBet.isError && !canReadPrevious(paperBet)) {
    const status = paperBet.error instanceof BackendReadError ? paperBet.error.status : null;
    if (status === 401 || status === 403)
      return (
        <RemotePermissionDeniedState
          action={
            <Button asChild variant="outline">
              <Link href="/paper-trading">Retour au paper trading</Link>
            </Button>
          }
        />
      );
    if (status !== 404 && status !== 410)
      return (
        <div className="ui-page-stack">
          <Button asChild className="w-fit" variant="ghost">
            <Link href="/paper-trading">Retour au paper trading</Link>
          </Button>
          <RemoteRecoverableErrorState
            title="Décision paper indisponible"
            description="La lecture a échoué temporairement. La décision n’a pas été supprimée."
            onRetry={() => void paperBet.refetch()}
            retryDisabled={paperBet.isFetching}
          />
        </div>
      );
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
    <div className="ui-page-stack">
      <Button asChild className="w-fit" size="small" variant="ghost">
        <Link href="/paper-trading">
          <ArrowLeft aria-hidden="true" className="size-4" />
          Retour au paper trading
        </Link>
      </Button>
      <RemoteDataBoundary
        className="min-w-0"
        isLoading={paperBet.isPending}
        isRefetching={paperBet.isFetching && !paperBet.isPending}
        loadingFallback={<RemotePageLoadingState label="Chargement de la décision paper" />}
      >
        <QueryRecovery queries={[paperBet]} />
        {paperBet.data?.data ? (
          <div className="ui-page-stack">
            <header className="grid gap-3">
              <p className="ui-eyebrow">Décision simulée</p>
              <h1 className="ui-page-title">Paper bet</h1>
              <div aria-label="Match et sélection" className="grid min-h-16 gap-1" role="group">
                {source ? (
                  <>
                    <p className="text-xl font-semibold [overflow-wrap:anywhere]">
                      {source.event.teamA} <span className="text-ink-secondary">vs</span>{" "}
                      {source.event.teamB}
                    </p>
                    <p className="text-sm text-ink-secondary">
                      Sélection : {source.market.selectionLabel} · {source.event.competition} ·{" "}
                      {formatDateTime(source.event.startsAt)}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-ink-secondary" role="status">
                    {sourceSignal.isPending
                      ? "Chargement du match et de la sélection…"
                      : "Le contexte du signal source est indisponible. Les détails de la décision restent consultables."}
                  </p>
                )}
              </div>
              <TechnicalText>{paperBet.data.data.paperBetId}</TechnicalText>
            </header>

            <QueryRecovery queries={[sourceSignal]} />
            {sourceSignal.isError && !canReadPrevious(sourceSignal) ? (
              <QueryFailure
                description="Le match et la sélection n’ont pas pu être récupérés depuis le signal source."
                missingDescription="Le signal source n’est plus disponible. La décision paper et son règlement restent consultables."
                missingTitle="Signal source indisponible"
                queries={[sourceSignal]}
              />
            ) : null}

            <div
              className="flex items-start gap-3 rounded-xl border border-border-subtle bg-accent-soft p-4 text-sm leading-6"
              role="note"
            >
              <FlaskConical aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
              Aucune exécution réelle : cette fiche retrace uniquement une décision paper.
            </div>

            <Card aria-label="Détail du paper bet">
              <CardContent className="grid gap-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="ui-section-title">Décision et règlement</h2>
                  <PaperStatusBadge status={paperBet.data.data.status} />
                </div>
                <MetricGrid>
                  <Metric
                    label="Mise fictive"
                    value={formatMoney(paperBet.data.data.stakeAmount, paperBet.data.data.currency)}
                  />
                  <Metric
                    label="Cote d’entrée"
                    value={formatDecimal(paperBet.data.data.entryOdds)}
                  />
                  <Metric label="P&L" value={<ProfitLoss bet={paperBet.data.data} />} />
                  <Metric label="Créé le" value={formatDateTime(paperBet.data.data.placedAt)} />
                  <Metric
                    label="Réglé le"
                    value={
                      paperBet.data.data.settledAt
                        ? formatDateTime(paperBet.data.data.settledAt)
                        : "Non réglé"
                    }
                  />
                  <Metric
                    label="Règles versionnées"
                    value={
                      <TechnicalText>{paperBet.data.data.settlementRulesVersion}</TechnicalText>
                    }
                  />
                  <Metric
                    label="CLV · proxy de prix"
                    value={
                      paperBet.data.data.clv == null
                        ? "Indisponible"
                        : new Intl.NumberFormat("fr-FR", {
                            style: "percent",
                            maximumFractionDigits: 2,
                          }).format(Number(paperBet.data.data.clv))
                    }
                  />
                </MetricGrid>
                <div className="grid gap-2 rounded-lg bg-surface-muted p-4 text-sm">
                  <p>
                    <strong>Motif :</strong> {paperBet.data.data.settlementReason ?? "En attente"}
                  </p>
                  <p className="ui-metadata">
                    <strong>Snapshot d’entrée :</strong>{" "}
                    <TechnicalText>{paperBet.data.data.oddsSnapshotId}</TechnicalText>
                  </p>
                  <p className="ui-metadata">
                    <strong>Snapshot de clôture :</strong>{" "}
                    <TechnicalText>
                      {paperBet.data.data.closingOddsSnapshotId ?? "Non disponible"}
                    </TechnicalText>
                  </p>
                </div>
                <Button asChild className="w-fit" variant="outline">
                  <Link href={`/opportunities/${encodeURIComponent(paperBet.data.data.signalId)}`}>
                    Ouvrir le signal source
                  </Link>
                </Button>
              </CardContent>
            </Card>
            {paperBet.data.meta.dataMode === "real" ? (
              <RealPaperSettlement bet={paperBet.data.data} />
            ) : paperBet.data.data.status === "open" ? (
              <SettlementForm bet={paperBet.data.data} />
            ) : null}
          </div>
        ) : (
          <RemoteRecoverableErrorState
            title="Décision paper indisponible"
            description="Aucune fiche n’a été renvoyée pour cette décision. Réessayez pour la récupérer."
            onRetry={() => void paperBet.refetch()}
            retryDisabled={paperBet.isFetching}
          />
        )}
      </RemoteDataBoundary>
    </div>
  );
}
