"use client";

import { requestBackend } from "../lib/backend";

import type { ItemResponsePaperBet, PaperBet } from "@metiquo/contracts/types";
import {
  Button,
  ContextPanel,
  Input,
  Section,
  Textarea,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState, type SubmitEventHandler } from "react";

import { formatMoney } from "./paper-trading-dashboard";

export function RealPaperSettlement({ bet }: Readonly<{ bet: PaperBet }>) {
  const [reason, setReason] = useState("");
  const [actor, setActor] = useState("admin-local");
  const [verifiedBet, setVerifiedBet] = useState<PaperBet | null>(null);
  const helpId = useId();
  const identity = useRef({ payload: "", key: "" });
  const client = useQueryClient();
  const correction = !["open", "pending_review"].includes(verifiedBet?.status ?? bet.status);
  const settlement = useMutation({
    mutationFn: async (): Promise<ItemResponsePaperBet> => {
      const payload = JSON.stringify({
        paperBetId: bet.paperBetId,
        reason: reason.trim(),
        actor: actor.trim(),
        ...(correction ? { correctionReason: reason.trim() } : {}),
      });
      if (identity.current.payload !== payload)
        identity.current = { payload, key: crypto.randomUUID() };
      const response = await requestBackend("/api/backend/api/v1/admin/paper-bets/settle", {
        method: "POST",
        body: payload,
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": identity.current.key,
          "X-Metiquo-CSRF": "1",
        },
      });
      if (!response.ok) {
        const error = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(error?.detail ?? "Vérification du règlement impossible");
      }
      return (await response.json()) as ItemResponsePaperBet;
    },
    onSuccess: (response) => {
      setVerifiedBet(response.data);
      setReason("");
      void client.invalidateQueries({ queryKey: ["paper-bets"] });
      void client.invalidateQueries({ queryKey: ["paper-bet", bet.paperBetId] });
      void client.invalidateQueries({ queryKey: ["paper-metrics"] });
    },
  });
  const canSubmit = Boolean(reason.trim() && actor.trim()) && !settlement.isPending;
  const submit: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    if (canSubmit) settlement.mutate();
  };
  return (
    <Section aria-label="Règlement depuis OE">
      <h3 className="font-semibold">
        {correction
          ? "Vérifier une correction Oracle’s Elixir"
          : "Vérifier le résultat Oracle’s Elixir"}
      </h3>
      <p className="text-sm text-ink-secondary">
        Le résultat et le P&L sont calculés depuis la source validée et les règles du marché. Une
        preuve incomplète maintient la décision en revue.
      </p>
      <form aria-busy={settlement.isPending} className="grid max-w-3xl gap-4" onSubmit={submit}>
        <p className="text-xs text-ink-secondary" id={helpId}>
          L’auteur et le motif sont obligatoires.
        </p>
        <label className="ui-field">
          <span>Auteur</span>
          <Input
            aria-describedby={helpId}
            name="actor"
            readOnly={settlement.isPending}
            required
            value={actor}
            onChange={(event) => {
              setActor(event.currentTarget.value);
            }}
          />
        </label>
        <label className="ui-field">
          <span>{correction ? "Motif de correction" : "Motif de vérification"}</span>
          <Textarea
            aria-describedby={helpId}
            name="reason"
            readOnly={settlement.isPending}
            required
            rows={3}
            value={reason}
            onChange={(event) => {
              setReason(event.currentTarget.value);
            }}
          />
        </label>
        <Button className="justify-self-start" disabled={!canSubmit} type="submit">
          {settlement.isPending
            ? "Vérification…"
            : correction
              ? "Ajouter une révision vérifiée"
              : "Vérifier le règlement"}
        </Button>
      </form>
      {settlement.data ? (
        <ContextPanel
          role="status"
          tone={settlement.data.data.status === "pending_review" ? "warning" : "success"}
        >
          {settlement.data.data.status === "pending_review"
            ? "Revue requise"
            : "Résultat enregistré"}{" "}
          · {settlement.data.data.settlementReason} · P&L{" "}
          {settlement.data.data.profitLoss == null
            ? "non réalisé"
            : formatMoney(settlement.data.data.profitLoss, settlement.data.data.currency)}
        </ContextPanel>
      ) : null}
      {settlement.isError ? (
        <RemoteRecoverableErrorState
          compact
          description={settlement.error.message}
          retryDisabled={!canSubmit}
          onRetry={() => {
            settlement.mutate();
          }}
        />
      ) : null}
    </Section>
  );
}
