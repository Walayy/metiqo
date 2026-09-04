"use client";

import type {
  ItemResponseOpportunity,
  ItemResponsePaperBet,
  PageResponsePaperBet,
  PaperBet,
  PaperBetStatus,
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
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BanknoteArrowDown,
  BanknoteArrowUp,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  ClipboardPlus,
  ExternalLink,
  FileCheck2,
  FlaskConical,
  Scale,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { formatDateTime } from "./opportunity-presenters";

const statusLabels: Readonly<Record<PaperBetStatus, string>> = {
  lost: "Perdu",
  open: "En attente (open)",
  pending_review: "Revue requise",
  push: "Égalité / push",
  void: "Annulé / void",
  won: "Gagné",
};

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Les décisions paper ne sont pas disponibles");
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
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
    throw new Error(problem?.detail ?? "L’action paper n’a pas pu être enregistrée");
  }
  return (await response.json()) as T;
}

function formatMoney(value: string | number, currency: string, signed = false) {
  const amount = Number(value);
  const formatted = new Intl.NumberFormat("fr-FR", {
    currency,
    currencyDisplay: "symbol",
    signDisplay: signed ? "always" : "auto",
    style: "currency",
  }).format(amount);
  return formatted;
}

function statusTone(status: PaperBetStatus) {
  if (status === "won") {
    return "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (status === "lost") {
    return "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200";
  }
  if (status === "pending_review" || status === "open") {
    return "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200";
  }
  return "border-border-strong bg-surface-muted text-ink-secondary";
}

export function PaperStatusBadge({ status }: Readonly<{ status: PaperBetStatus }>) {
  return <Badge className={statusTone(status)}>{statusLabels[status]}</Badge>;
}

export function ProfitLoss({ bet }: Readonly<{ bet: PaperBet }>) {
  if (bet.profitLoss === null || bet.profitLoss === undefined) {
    return <span className="text-ink-secondary">Non réalisé</span>;
  }
  const amount = Number(bet.profitLoss);
  return (
    <span
      className={
        amount < 0
          ? "font-semibold text-red-700 dark:text-red-300"
          : amount > 0
            ? "font-semibold text-emerald-700 dark:text-emerald-300"
            : "font-semibold"
      }
    >
      {formatMoney(bet.profitLoss, bet.currency, amount !== 0)}
    </span>
  );
}

function PaperCard({ bet, local = false }: Readonly<{ bet: PaperBet; local?: boolean }>) {
  return (
    <Card aria-label={`Paper bet ${bet.paperBetId}`}>
      <CardContent className="grid h-full gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
              {local ? "Résultat de cette session" : formatDateTime(bet.placedAt)}
            </p>
            <p className="mt-1 break-all font-semibold">{bet.paperBetId}</p>
          </div>
          <PaperStatusBadge status={bet.status} />
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-secondary">Mise fictive</dt>
            <dd className="mt-1 font-semibold">{formatMoney(bet.stakeAmount, bet.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Cote d’entrée</dt>
            <dd className="mt-1 font-semibold">{bet.entryOdds}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">P&L</dt>
            <dd className="mt-1">
              <ProfitLoss bet={bet} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Règles</dt>
            <dd className="mt-1 break-words font-semibold">{bet.settlementRulesVersion}</dd>
          </div>
        </dl>
        {!local ? (
          <Button asChild className="mt-auto" variant="outline">
            <Link href={`/paper-trading/${encodeURIComponent(bet.paperBetId)}`}>
              Ouvrir la fiche
              <ExternalLink aria-hidden="true" className="size-4" />
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PnlSummary({ bets }: Readonly<{ bets: readonly PaperBet[] }>) {
  const gains = bets.reduce((total, bet) => total + Math.max(Number(bet.profitLoss ?? 0), 0), 0);
  const losses = bets.reduce((total, bet) => total + Math.min(Number(bet.profitLoss ?? 0), 0), 0);
  const currency = bets[0]?.currency ?? "EUR";
  return (
    <section aria-label="Résumé du P&L" className="grid gap-3 sm:grid-cols-3">
      <Card aria-label="Gains paper">
        <CardContent className="grid gap-2 p-4">
          <p className="flex items-center gap-2 text-xs uppercase tracking-[0.1em] text-ink-secondary">
            <BanknoteArrowUp aria-hidden="true" className="size-4" /> Gains
          </p>
          <p className="text-xl font-semibold text-emerald-700 dark:text-emerald-300">
            {formatMoney(gains, currency, gains !== 0)}
          </p>
        </CardContent>
      </Card>
      <Card aria-label="Pertes paper">
        <CardContent className="grid gap-2 p-4">
          <p className="flex items-center gap-2 text-xs uppercase tracking-[0.1em] text-ink-secondary">
            <BanknoteArrowDown aria-hidden="true" className="size-4" /> Pertes
          </p>
          <p className="text-xl font-semibold text-red-700 dark:text-red-300">
            {formatMoney(losses, currency, losses !== 0)}
          </p>
        </CardContent>
      </Card>
      <Card aria-label="Solde paper">
        <CardContent className="grid gap-2 p-4">
          <p className="flex items-center gap-2 text-xs uppercase tracking-[0.1em] text-ink-secondary">
            <Scale aria-hidden="true" className="size-4" /> Solde
          </p>
          <p className="text-xl font-semibold">
            {formatMoney(gains + losses, currency, gains + losses !== 0)}
          </p>
        </CardContent>
      </Card>
    </section>
  );
}

function SettlementForm({ bet }: Readonly<{ bet: PaperBet }>) {
  const [status, setStatus] = useState<"lost" | "push" | "void" | "won">("won");
  const [profitLoss, setProfitLoss] = useState("10");
  const [reason, setReason] = useState("");
  const settlement = useMutation({
    mutationFn: () =>
      postJson<ItemResponsePaperBet>("/api/v1/admin/paper-bets/settle", {
        paperBetId: bet.paperBetId,
        profitLoss,
        reason: reason.trim(),
        status,
      }),
  });
  const canSubmit = reason.trim().length > 0 && profitLoss.trim().length > 0;

  if (settlement.data) {
    return (
      <div className="grid gap-3">
        <div
          aria-live="polite"
          className="rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/30"
          role="status"
        >
          <p className="font-semibold">Règlement {settlement.data.data.status}</p>
          <p className="mt-1">
            <ProfitLoss bet={settlement.data.data} /> · {settlement.data.data.settlementReason}
          </p>
        </div>
        <PaperCard bet={settlement.data.data} local />
      </div>
    );
  }

  return (
    <section aria-label="Règlement fictif" className="grid gap-3 rounded-lg border p-4">
      <h3 className="font-semibold">Régler cette décision fictive</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="grid gap-1 text-sm">
          <span className="font-semibold">Statut</span>
          <select
            className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
            onChange={(event) => {
              setStatus(event.currentTarget.value as typeof status);
            }}
            value={status}
          >
            <option value="won">Gagné</option>
            <option value="lost">Perdu</option>
            <option value="push">Push</option>
            <option value="void">Void</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-semibold">P&L fictif</span>
          <input
            className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
            inputMode="decimal"
            onChange={(event) => {
              setProfitLoss(event.currentTarget.value);
            }}
            type="number"
            value={profitLoss}
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-semibold">Motif</span>
          <input
            className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
            onChange={(event) => {
              setReason(event.currentTarget.value);
            }}
            placeholder="Résultat vérifié"
            value={reason}
          />
        </label>
      </div>
      <Button
        disabled={!canSubmit || settlement.isPending}
        onClick={() => {
          settlement.mutate();
        }}
      >
        <FileCheck2 aria-hidden="true" className="size-4" />
        {settlement.isPending ? "Règlement…" : "Enregistrer le règlement fictif"}
      </Button>
      {settlement.isError ? (
        <RemoteRecoverableErrorState
          compact
          description={settlement.error.message}
          onRetry={() => {
            settlement.mutate();
          }}
        />
      ) : null}
    </section>
  );
}

function CreationPanel({ signalId }: Readonly<{ signalId: string | null }>) {
  const [stakeAmount, setStakeAmount] = useState("10");
  const opportunity = useQuery({
    enabled: signalId !== null,
    queryFn: ({ signal }) =>
      getJson<ItemResponseOpportunity>(
        `/api/v1/opportunities/${encodeURIComponent(signalId ?? "")}`,
        signal,
      ),
    queryKey: ["opportunity", signalId],
  });
  const creation = useMutation({
    mutationFn: () =>
      postJson<ItemResponsePaperBet>("/api/v1/paper-bets", {
        currency: "EUR",
        signalId,
        stakeAmount,
      }),
  });
  const selected = opportunity.data?.data;
  const publishable = selected?.quality.publishable === true;

  return (
    <Card aria-label="Créer une décision paper">
      <CardContent className="grid gap-4 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="grid size-9 place-items-center rounded-lg bg-surface-muted text-ink-secondary"
          >
            <ClipboardPlus className="size-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">Créer une décision paper</h2>
            <p className="mt-1 text-xs text-ink-secondary">
              Depuis un signal admissible uniquement
            </p>
          </div>
        </div>
        {!signalId ? (
          <div className="rounded-lg bg-surface-muted p-4 text-sm leading-6">
            Choisissez un signal depuis les{" "}
            <Link className="font-semibold underline" href="/">
              opportunités
            </Link>
            .
          </div>
        ) : opportunity.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void opportunity.refetch()} />
        ) : opportunity.isPending ? (
          <RemoteLoadingState minHeight="10rem" rows={3} />
        ) : selected ? (
          <div className="grid gap-4">
            <div className="grid gap-2 rounded-lg bg-surface-muted p-4 text-sm">
              <p className="font-semibold">
                {selected.event.teamA} — {selected.event.teamB}
              </p>
              <p>
                Cote figée {selected.book.decimalOdds} · sélection {selected.market.selectionLabel}
              </p>
              <p className="break-all text-xs text-ink-secondary">Signal {selected.signalId}</p>
            </div>
            {!publishable ? (
              <div
                className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50/80 p-4 text-sm dark:border-red-900 dark:bg-red-950/30"
                role="alert"
              >
                <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                Signal non publiable : la création paper reste bloquée.
              </div>
            ) : null}
            <label className="grid max-w-xs gap-1 text-sm">
              <span className="font-semibold">Mise fictive (EUR)</span>
              <input
                className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
                inputMode="decimal"
                min="0.01"
                onChange={(event) => {
                  setStakeAmount(event.currentTarget.value);
                }}
                step="0.01"
                type="number"
                value={stakeAmount}
              />
            </label>
            <Button
              disabled={!publishable || creation.isPending || Number(stakeAmount) <= 0}
              onClick={() => {
                creation.mutate();
              }}
            >
              <FlaskConical aria-hidden="true" className="size-4" />
              {creation.isPending ? "Création…" : "Créer le paper bet"}
            </Button>
            {creation.isError ? (
              <RemoteRecoverableErrorState
                compact
                description={creation.error.message}
                onRetry={() => {
                  creation.mutate();
                }}
              />
            ) : null}
            {creation.data ? (
              <div className="grid gap-4">
                <div
                  aria-live="polite"
                  className="flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm font-semibold dark:border-emerald-900 dark:bg-emerald-950/30"
                  role="status"
                >
                  <CheckCircle2 aria-hidden="true" className="size-4" />
                  Paper bet créé · aucune exécution réelle
                </div>
                <PaperCard bet={creation.data.data} local />
                {creation.data.data.status === "open" ? (
                  <SettlementForm bet={creation.data.data} />
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function PaperTradingDashboard() {
  const searchParameters = useSearchParams();
  const signalIdParameter = searchParameters.get("signalId")?.trim();
  const signalId =
    signalIdParameter === undefined || signalIdParameter.length === 0 ? null : signalIdParameter;
  const paperBets = useQuery({
    queryFn: ({ signal }) =>
      getJson<PageResponsePaperBet>("/api/v1/paper-bets?offset=0&limit=100", signal),
    queryKey: ["paper-bets"],
  });
  const bets = paperBets.data?.data ?? [];

  return (
    <div className="grid gap-6 sm:gap-8">
      <header className="grid gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
          Simulation isolée
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Paper trading</h1>
        <p className="max-w-3xl text-sm leading-6 text-ink-secondary sm:text-base">
          Décisions simulées, règlement et performance. Aucune mise n’est envoyée à un bookmaker et
          aucun argent réel n’est engagé.
        </p>
      </header>

      <div
        className="flex items-start gap-3 rounded-xl border border-accent bg-accent-soft p-4 text-sm leading-6"
        role="note"
      >
        <FlaskConical aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
        Mode paper uniquement : les montants, gains et pertes ci-dessous sont fictifs ; aucun argent
        réel n’est engagé.
      </div>

      <CreationPanel signalId={signalId} />

      <section aria-labelledby="paper-history" className="grid gap-4">
        <div className="flex items-center gap-3">
          <ChartNoAxesCombined aria-hidden="true" className="size-5 text-ink-secondary" />
          <h2 className="text-xl font-semibold" id="paper-history">
            Historique et P&L
          </h2>
        </div>
        {paperBets.isError ? (
          <RemoteRecoverableErrorState onRetry={() => void paperBets.refetch()} />
        ) : (
          <RemoteDataBoundary
            isLoading={paperBets.isPending}
            isRefetching={paperBets.isFetching && !paperBets.isPending}
            loadingFallback={<RemoteLoadingState minHeight="20rem" rows={6} />}
          >
            <div className="grid gap-4">
              <PnlSummary bets={bets} />
              {bets.length > 0 ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  {bets.map((bet) => (
                    <PaperCard bet={bet} key={bet.paperBetId} />
                  ))}
                </div>
              ) : (
                <RemoteEmptyState description="Aucune décision paper dans ce mode." />
              )}
            </div>
          </RemoteDataBoundary>
        )}
      </section>

      <Card aria-label="Statuts paper supportés">
        <CardContent className="grid gap-3 p-5">
          <h2 className="font-semibold">Statuts supportés</h2>
          <div className="flex flex-wrap gap-2">
            {(["open", "won", "lost", "push", "void", "pending_review"] as const).map((status) => (
              <PaperStatusBadge key={status} status={status} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
