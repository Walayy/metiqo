"use client";

import { requestBackend } from "../lib/backend";

import type { ItemResponsePaperBet, PaperBet } from "@metiquo/contracts/types";
import { Button, RemoteRecoverableErrorState } from "@metiquo/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

export function RealPaperSettlement({ bet }: Readonly<{ bet: PaperBet }>) {
  const [reason, setReason] = useState("");
  const [actor, setActor] = useState("admin-local");
  const identity = useRef({ payload: "", key: "" });
  const client = useQueryClient();
  const correction = !["open", "pending_review"].includes(bet.status);
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
        const error = (await response.json()) as { detail?: string };
        throw new Error(error.detail ?? "Vérification du règlement impossible");
      }
      return (await response.json()) as ItemResponsePaperBet;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["paper-bets"] });
      void client.invalidateQueries({ queryKey: ["paper-bet", bet.paperBetId] });
    },
  });
  return (
    <section aria-label="Règlement depuis OE" className="grid gap-3 rounded-lg border p-4">
      <h3 className="font-semibold">
        {correction ? "Vérifier une correction OE" : "Vérifier le résultat OE"}
      </h3>
      <p className="text-sm text-ink-secondary">
        Le résultat et le P&L sont calculés depuis la source validée et les règles du marché. Une
        preuve incomplète maintient la décision en revue.
      </p>
      <label className="grid gap-1 text-sm">
        <span>Auteur</span>
        <input
          className="min-h-11 rounded-md border bg-surface-raised px-3"
          value={actor}
          onChange={(event) => {
            setActor(event.currentTarget.value);
          }}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span>{correction ? "Motif de correction" : "Motif de vérification"}</span>
        <input
          className="min-h-11 rounded-md border bg-surface-raised px-3"
          value={reason}
          onChange={(event) => {
            setReason(event.currentTarget.value);
          }}
        />
      </label>
      <Button
        disabled={!reason.trim() || !actor.trim() || settlement.isPending}
        onClick={() => {
          settlement.mutate();
        }}
      >
        {settlement.isPending
          ? "Vérification…"
          : correction
            ? "Ajouter une révision vérifiée"
            : "Vérifier le règlement"}
      </Button>
      {settlement.data ? (
        <p role="status" className="text-sm">
          {settlement.data.data.status === "pending_review"
            ? "Revue requise"
            : "Résultat enregistré"}{" "}
          · {settlement.data.data.settlementReason} · P&L{" "}
          {settlement.data.data.profitLoss ?? "non réalisé"}
        </p>
      ) : null}
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
