"use client";

import { QueryFailure, QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend, requestBackend } from "../lib/backend";

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
  Input,
  Metric,
  MetricGrid,
  Select,
  TechnicalText,
  Section,
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BanknoteArrowDown,
  BanknoteArrowUp,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  ClipboardPlus,
  ArrowRight,
  FileCheck2,
  FlaskConical,
  Scale,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";

import {
  describeOpportunity,
  formatDateTime,
  formatDecimal,
  isAdmissible,
} from "./opportunity-presenters";
import { PaperFinancialReport } from "./paper-financial-report";
import { RealPaperSettlement } from "./real-paper-settlement";

const statusLabels: Readonly<Record<PaperBetStatus, string>> = {
  lost: "Perdu",
  open: "En attente (open)",
  pending_review: "Revue requise",
  push: "Égalité / push",
  void: "Annulé / void",
  won: "Gagné",
};

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`/api/backend${path}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("Les décisions paper ne sont pas disponibles");
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown, key?: string): Promise<T> {
  const response = await requestBackend(`/api/backend${path}`, {
    body: JSON.stringify(body),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "Idempotency-Key": key ?? crypto.randomUUID(),
      "X-Metiquo-CSRF": "1",
    },
    method: "POST",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? "L’action paper n’a pas pu être enregistrée");
  }
  return (await response.json()) as T;
}

export function formatMoney(value: string | number, currency: string, signed = false) {
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
      <CardContent className="grid h-full gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-ink-secondary">
              {local ? "Résultat de cette session" : formatDateTime(bet.placedAt)}
            </p>
            <TechnicalText className="mt-1">{bet.paperBetId}</TechnicalText>
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
            <dd className="mt-1 font-semibold">{formatDecimal(bet.entryOdds)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">P&L</dt>
            <dd className="mt-1">
              <ProfitLoss bet={bet} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Règles</dt>
            <dd className="mt-1">
              <TechnicalText>{bet.settlementRulesVersion}</TechnicalText>
            </dd>
          </div>
        </dl>
        <div className="mt-auto flex flex-wrap gap-2">
          {!local ? (
            <Button asChild variant="outline">
              <Link href={`/paper-trading/${encodeURIComponent(bet.paperBetId)}`}>
                Ouvrir la fiche
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </Button>
          ) : null}
          <Button asChild variant="ghost">
            <Link href={`/opportunities/${encodeURIComponent(bet.signalId)}`}>
              Voir le signal associé
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function PnlSummary({ bets }: Readonly<{ bets: readonly PaperBet[] }>) {
  const gains = bets.reduce((total, bet) => total + Math.max(Number(bet.profitLoss ?? 0), 0), 0);
  const losses = bets.reduce((total, bet) => total + Math.min(Number(bet.profitLoss ?? 0), 0), 0);
  const currency = bets[0]?.currency ?? "EUR";
  return (
    <section aria-label="Résumé du P&L">
      <p className="mb-3 text-xs text-ink-secondary">
        Résumé des décisions affichées sur cette page.
      </p>
      <MetricGrid>
        <Metric
          aria-label="Gains paper"
          role="region"
          emphasis="statistic"
          label={
            <span className="flex items-center gap-2">
              <BanknoteArrowUp aria-hidden="true" className="size-4" /> Gains
            </span>
          }
          value={
            <span className="text-emerald-700 dark:text-emerald-300">
              {formatMoney(gains, currency, gains !== 0)}
            </span>
          }
        />
        <Metric
          aria-label="Pertes paper"
          role="region"
          emphasis="statistic"
          label={
            <span className="flex items-center gap-2">
              <BanknoteArrowDown aria-hidden="true" className="size-4" /> Pertes
            </span>
          }
          value={
            <span className="text-red-700 dark:text-red-300">
              {formatMoney(losses, currency, losses !== 0)}
            </span>
          }
        />
        <Metric
          aria-label="Solde paper"
          role="region"
          emphasis="statistic"
          label={
            <span className="flex items-center gap-2">
              <Scale aria-hidden="true" className="size-4" /> Solde
            </span>
          }
          value={formatMoney(gains + losses, currency, gains + losses !== 0)}
        />
      </MetricGrid>
    </section>
  );
}

export function SettlementForm({ bet }: Readonly<{ bet: PaperBet }>) {
  const queryClient = useQueryClient();
  const identity = useRef({ payload: "", key: "" });
  const [status, setStatus] = useState<"lost" | "push" | "void" | "won">("won");
  const [profitLoss, setProfitLoss] = useState(
    (Number(bet.stakeAmount) * (Number(bet.entryOdds) - 1)).toFixed(2),
  );
  const [reason, setReason] = useState("");
  const settlement = useMutation({
    mutationFn: () => {
      const body = {
        paperBetId: bet.paperBetId,
        profitLoss,
        reason: reason.trim(),
        status,
      };
      const payload = JSON.stringify(body);
      if (identity.current.payload !== payload)
        identity.current = { payload, key: crypto.randomUUID() };
      return postJson<ItemResponsePaperBet>(
        "/api/v1/admin/paper-bets/settle",
        body,
        identity.current.key,
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["paper-bets"] }),
        queryClient.invalidateQueries({ queryKey: ["paper-bet", bet.paperBetId] }),
        queryClient.invalidateQueries({ queryKey: ["paper-metrics"] }),
      ]);
    },
  });
  const validAmount = profitLoss.trim().length > 0 && Number.isFinite(Number(profitLoss));
  const coherentAmount =
    validAmount &&
    (status === "won"
      ? Number(profitLoss) > 0
      : status === "lost"
        ? Number(profitLoss) < 0
        : Number(profitLoss) === 0);
  const canSubmit = reason.trim().length > 0 && coherentAmount;

  if (settlement.data) {
    return (
      <div className="grid gap-3">
        <div
          aria-live="polite"
          className="rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/30"
          role="status"
        >
          <p className="font-semibold">
            Règlement enregistré · {statusLabels[settlement.data.data.status]}
          </p>
          <p className="mt-1">
            <ProfitLoss bet={settlement.data.data} /> · {settlement.data.data.settlementReason}
          </p>
        </div>
        <PaperCard bet={settlement.data.data} local />
      </div>
    );
  }

  return (
    <Section aria-label="Règlement fictif">
      <h3 className="font-semibold">Régler cette décision fictive</h3>
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit && !settlement.isPending) settlement.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="ui-field">
            <span className="font-semibold">Statut</span>
            <Select
              aria-label="Statut"
              disabled={settlement.isPending}
              onValueChange={(value) => {
                setStatus(value as typeof status);
                setProfitLoss(
                  value === "won"
                    ? (Number(bet.stakeAmount) * (Number(bet.entryOdds) - 1)).toFixed(2)
                    : value === "lost"
                      ? (-Number(bet.stakeAmount)).toFixed(2)
                      : "0.00",
                );
              }}
              value={status}
            >
              <option value="won">Gagné</option>
              <option value="lost">Perdu</option>
              <option value="push">Égalité / push</option>
              <option value="void">Annulé / void</option>
            </Select>
          </label>
          <label className="ui-field">
            <span className="font-semibold">P&L fictif</span>
            <Input
              aria-describedby="paper-settlement-amount-hint"
              aria-invalid={!coherentAmount || undefined}
              disabled={settlement.isPending}
              inputMode="decimal"
              onChange={(event) => {
                setProfitLoss(event.currentTarget.value);
              }}
              type="number"
              required
              step="0.01"
              value={profitLoss}
            />
          </label>
          <label className="ui-field">
            <span className="font-semibold">Motif</span>
            <Input
              disabled={settlement.isPending}
              onChange={(event) => {
                setReason(event.currentTarget.value);
              }}
              placeholder="Résultat vérifié"
              required
              value={reason}
            />
          </label>
        </div>
        <p className="text-xs text-ink-secondary" id="paper-settlement-amount-hint">
          {status === "won"
            ? "Le gain net doit être positif."
            : status === "lost"
              ? "La perte doit être négative."
              : "Une égalité ou une annulation restitue la mise : P&L nul."}{" "}
          Montant fictif en {bet.currency}. Un motif est obligatoire.
        </p>
        <Button disabled={!canSubmit || settlement.isPending} type="submit">
          <FileCheck2 aria-hidden="true" className="size-4" />
          {settlement.isPending ? "Règlement…" : "Enregistrer le règlement fictif"}
        </Button>
      </form>
      {settlement.isError ? (
        <RemoteRecoverableErrorState
          compact
          description={settlement.error.message}
          retryDisabled={!canSubmit || settlement.isPending}
          onRetry={() => {
            settlement.mutate();
          }}
        />
      ) : null}
    </Section>
  );
}

function CreationPanel({ signalId }: Readonly<{ signalId: string | null }>) {
  const queryClient = useQueryClient();
  const identity = useRef({ payload: "", key: "" });
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
    mutationFn: () => {
      const body = {
        currency: "EUR",
        signalId,
        stakeAmount,
      };
      const payload = JSON.stringify(body);
      if (identity.current.payload !== payload)
        identity.current = { payload, key: crypto.randomUUID() };
      return postJson<ItemResponsePaperBet>("/api/v1/paper-bets", body, identity.current.key);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["paper-bets"] }),
        queryClient.invalidateQueries({ queryKey: ["paper-metrics"] }),
      ]);
    },
  });
  const selected = opportunity.data?.data;
  const publishable =
    selected !== undefined &&
    isAdmissible(selected, opportunity.data?.meta.computedAt ?? new Date(0).toISOString());
  const validStake =
    stakeAmount.trim().length > 0 &&
    Number.isFinite(Number(stakeAmount)) &&
    Number(stakeAmount) >= 0.01;

  return (
    <Card aria-label="Créer une décision paper" id="paper-create" tabIndex={-1}>
      <CardContent className="grid gap-4">
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
          <div className="grid justify-items-start gap-3">
            <QueryFailure
              description="Le signal sélectionné n’a pas pu être chargé."
              missingDescription="Ce signal n’est plus disponible. Choisissez un autre signal depuis les opportunités."
              missingTitle="Signal introuvable"
              queries={[opportunity]}
            />
            <Button asChild variant="outline">
              <Link href="/">Choisir un autre signal</Link>
            </Button>
          </div>
        ) : opportunity.isPending ? (
          <RemoteLoadingState minHeight="10rem" rows={3} />
        ) : selected ? (
          <div className="grid min-w-0 gap-4 [overflow-wrap:anywhere]">
            <div className="grid gap-2 rounded-lg bg-surface-muted p-4 text-sm">
              <p className="font-semibold">
                {selected.event.teamA} — {selected.event.teamB}
              </p>
              <p>
                Cote figée {formatDecimal(selected.book.decimalOdds)} · sélection{" "}
                {selected.market.selectionLabel}
              </p>
              <p className="text-xs text-ink-secondary">
                Signal <TechnicalText>{selected.signalId}</TechnicalText>
              </p>
            </div>
            {!publishable ? (
              <div
                className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50/80 p-4 text-sm dark:border-red-900 dark:bg-red-950/30"
                role="alert"
              >
                <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                {describeOpportunity(selected, opportunity.data.meta.computedAt)}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="ghost" size="small">
                <Link href={`/opportunities/${encodeURIComponent(selected.signalId)}`}>
                  Revoir le signal
                </Link>
              </Button>
              <Button asChild variant="ghost" size="small">
                <Link href="/">Choisir un autre signal</Link>
              </Button>
            </div>
            <form
              className="grid justify-items-start gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (publishable && validStake && !creation.isPending && !creation.data)
                  creation.mutate();
              }}
            >
              <label className="ui-field w-full max-w-xs">
                <span className="font-semibold">Mise fictive (EUR)</span>
                <Input
                  aria-describedby="paper-stake-hint"
                  aria-invalid={!validStake || undefined}
                  disabled={!publishable || creation.isPending || Boolean(creation.data)}
                  inputMode="decimal"
                  min="0.01"
                  onChange={(event) => {
                    setStakeAmount(event.currentTarget.value);
                  }}
                  step="0.01"
                  required
                  type="number"
                  value={stakeAmount}
                />
              </label>
              <p className="text-xs text-ink-secondary" id="paper-stake-hint">
                Saisissez une mise fictive d’au moins 0,01 €.
              </p>
              <Button
                disabled={
                  !publishable || creation.isPending || !validStake || Boolean(creation.data)
                }
                type="submit"
              >
                <FlaskConical aria-hidden="true" className="size-4" />
                {creation.isPending
                  ? "Création…"
                  : creation.data
                    ? "Paper bet créé"
                    : "Créer le paper bet"}
              </Button>
            </form>
            {creation.isError ? (
              <RemoteRecoverableErrorState
                compact
                description={creation.error.message}
                retryDisabled={!publishable || !validStake || creation.isPending}
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
                {creation.data.meta.dataMode === "real" ? (
                  <RealPaperSettlement bet={creation.data.data} />
                ) : creation.data.data.status === "open" ? (
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
  const [offset, setOffset] = useState(0);
  const searchParameters = useSearchParams();
  const signalIdParameter = searchParameters.get("signalId")?.trim();
  const signalId =
    signalIdParameter === undefined || signalIdParameter.length === 0 ? null : signalIdParameter;
  const paperBets = useQuery({
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      getJson<PageResponsePaperBet>(
        `/api/v1/paper-bets?offset=${String(offset)}&limit=100`,
        signal,
      ),
    queryKey: ["paper-bets", offset],
    refetchInterval: 30_000,
  });
  const bets = paperBets.data?.data ?? [];

  return (
    <div className="ui-page-stack">
      <header className="grid gap-3">
        <p className="ui-eyebrow">Simulation isolée</p>
        <h1 className="ui-page-title">Paper trading</h1>
        <p className="max-w-3xl text-sm leading-6 text-ink-secondary sm:text-base">
          Décisions simulées, règlement et performance. Aucune mise n’est envoyée à un bookmaker et
          aucun argent réel n’est engagé.
        </p>
      </header>

      <nav aria-label="Sections du paper trading" className="ui-toolbar">
        <Button asChild size="small" variant="outline">
          <a href="#paper-create">Création</a>
        </Button>
        <Button asChild size="small" variant="outline">
          <a href="#paper-history">Historique</a>
        </Button>
        <Button asChild size="small" variant="outline">
          <a href="#paper-report">Rapport financier</a>
        </Button>
      </nav>

      <div
        className="flex items-start gap-3 rounded-xl border border-border-subtle bg-accent-soft p-4 text-sm leading-6"
        role="note"
      >
        <FlaskConical aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
        Mode paper uniquement : les montants, gains et pertes ci-dessous sont fictifs ; aucun argent
        réel n’est engagé.
      </div>

      <CreationPanel key={signalId ?? "no-signal"} signalId={signalId} />

      <section
        aria-labelledby="paper-history-title"
        className="grid gap-4"
        id="paper-history"
        tabIndex={-1}
      >
        <div className="flex items-center gap-3">
          <ChartNoAxesCombined aria-hidden="true" className="size-5 text-ink-secondary" />
          <h2 className="ui-section-title" id="paper-history-title">
            Historique et P&L
          </h2>
        </div>
        <QueryRecovery queries={[paperBets]} />
        {paperBets.isError && !canReadPrevious(paperBets) ? (
          <RemoteRecoverableErrorState
            onRetry={() => void paperBets.refetch()}
            retryDisabled={paperBets.isFetching}
          />
        ) : (
          <RemoteDataBoundary
            isLoading={paperBets.isPending}
            isRefetching={paperBets.isFetching && !paperBets.isPending}
            loadingFallback={<RemoteLoadingState minHeight="20rem" rows={6} />}
          >
            <div className="grid gap-4">
              {paperBets.data?.meta.dataMode === "mock" ? <PnlSummary bets={bets} /> : null}
              {bets.length > 0 ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  {bets.map((bet) => (
                    <PaperCard bet={bet} key={bet.paperBetId} />
                  ))}
                </div>
              ) : (
                <RemoteEmptyState
                  title={offset > 0 ? "Aucune décision sur cette page" : "Aucune décision paper"}
                  description={
                    offset > 0
                      ? "Revenez à la première page pour retrouver les décisions disponibles."
                      : "Créez votre première décision fictive depuis un signal admissible pour suivre sa performance ici."
                  }
                  action={
                    offset > 0 ? (
                      <Button
                        variant="outline"
                        onClick={() => {
                          setOffset(0);
                        }}
                      >
                        Revenir à la première page
                      </Button>
                    ) : (
                      <Button asChild variant="outline">
                        <Link href="/">Voir les opportunités</Link>
                      </Button>
                    )
                  }
                />
              )}
              {paperBets.data && (paperBets.data.page.total > 100 || offset > 0) ? (
                <nav
                  aria-label="Pagination des décisions paper"
                  className="flex flex-wrap items-center justify-between gap-3"
                >
                  <Button
                    variant="outline"
                    disabled={offset === 0 || paperBets.isFetching}
                    onClick={() => {
                      setOffset(Math.max(0, offset - 100));
                    }}
                  >
                    Page précédente
                  </Button>
                  <span className="text-sm text-ink-secondary" role="status">
                    {paperBets.data.page.total} décisions · page{" "}
                    {Math.floor(paperBets.data.page.offset / 100) + 1}
                    {" sur "}
                    {Math.max(1, Math.ceil(paperBets.data.page.total / 100))}
                  </span>
                  <Button
                    variant="outline"
                    disabled={offset + 100 >= paperBets.data.page.total || paperBets.isFetching}
                    onClick={() => {
                      setOffset(offset + 100);
                    }}
                  >
                    Page suivante
                  </Button>
                </nav>
              ) : null}
            </div>
          </RemoteDataBoundary>
        )}
      </section>

      <PaperFinancialReport />

      <Card aria-label="Statuts paper supportés">
        <CardContent className="grid gap-3">
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
