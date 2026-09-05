"use client";

import type {
  AliasRecord,
  ItemResponseAliasRecord,
  ItemResponseMappingReview,
  MappingCandidate,
  MappingReview,
  PageResponseMappingReview,
} from "@metiquo/contracts/types";
import {
  Button,
  Card,
  CardContent,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Ban,
  CircleAlert,
  Eye,
  GitMerge,
  Link2,
  ListTree,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";

import { formatDateTime, formatPercent } from "./opportunity-presenters";

const MAPPINGS_PATH = "/api/backend/api/v1/admin/mappings";

async function getPending(signal: AbortSignal): Promise<PageResponseMappingReview> {
  const response = await fetch(`${MAPPINGS_PATH}/pending?offset=0&limit=100`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La file de mapping ne répond pas");
  return (await response.json()) as PageResponseMappingReview;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api/backend/api/v1${path}`, {
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
    throw new Error(problem?.detail ?? "La décision n’a pas pu être enregistrée");
  }
  return (await response.json()) as T;
}

function CandidateCard({
  candidate,
  checked,
  onSelect,
}: Readonly<{ candidate: MappingCandidate; checked: boolean; onSelect: () => void }>) {
  const summary = `${candidate.label}, confiance ${formatPercent(Number(candidate.confidence))}`;
  return (
    <label className="grid cursor-pointer gap-3 rounded-lg border border-border-subtle p-4 transition-colors duration-interaction hover:border-accent has-[:checked]:border-accent has-[:checked]:bg-accent-soft motion-reduce:transition-none">
      <span className="flex items-start gap-3">
        <input checked={checked} name="mapping-candidate" onChange={onSelect} type="radio" />
        <span className="min-w-0">
          <span className="block font-semibold">{candidate.label}</span>
          <span className="mt-1 block break-all text-xs text-ink-secondary">
            {candidate.eventId}
          </span>
        </span>
      </span>
      <span aria-label={summary} className="grid gap-2" role="img">
        <span className="flex items-center justify-between text-xs">
          <span>Score global</span>
          <strong>{formatPercent(Number(candidate.confidence))}</strong>
        </span>
        <span className="h-2 overflow-hidden rounded-full bg-surface-muted">
          <span
            className="block h-full rounded-full bg-accent"
            style={{ width: `${(Number(candidate.confidence) * 100).toString()}%` }}
          />
        </span>
      </span>
      <span className="text-xs font-semibold">Composantes du score</span>
      <ul className="grid gap-1 text-xs leading-5 text-ink-secondary">
        {candidate.reasons.map((reason) => (
          <li key={reason}>• {reason}</li>
        ))}
      </ul>
      {candidate.selectionsInverted ? (
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">
          Participants inversés : les sélections A/B seront remappées.
        </span>
      ) : null}
    </label>
  );
}

function DecisionResult({ review }: Readonly<{ review: MappingReview }>) {
  return (
    <div
      aria-live="polite"
      className="grid gap-2 rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/30"
      role="status"
    >
      <p className="flex items-center gap-2 font-semibold">
        <BadgeCheck aria-hidden="true" className="size-4" />
        Décision {review.status}
      </p>
      <p>
        {review.reviewer} · {review.reviewedAt ? formatDateTime(review.reviewedAt) : "date absente"}
      </p>
      <p className="text-xs text-ink-secondary">{review.decisionReason}</p>
    </div>
  );
}

function AliasResult({ alias }: Readonly<{ alias: AliasRecord }>) {
  return (
    <div
      aria-live="polite"
      className="rounded-lg border border-emerald-300 bg-emerald-50/80 p-4 text-sm dark:border-emerald-900 dark:bg-emerald-950/30"
      role="status"
    >
      <p className="font-semibold">Alias créé et daté</p>
      <p className="mt-1">
        {alias.alias} → {alias.canonicalId}
      </p>
      <p className="mt-1 text-xs text-ink-secondary">Créé le {formatDateTime(alias.createdAt)}</p>
    </div>
  );
}

function MappingReviewCard({ review }: Readonly<{ review: MappingReview }>) {
  const queryClient = useQueryClient();
  const [selectedEventId, setSelectedEventId] = useState(review.candidates[0]?.eventId ?? "");
  const [reviewer, setReviewer] = useState("admin-local");
  const [reason, setReason] = useState("");
  const [alias, setAlias] = useState(review.rawParticipants[0] ?? "");
  const selectedCandidate = review.candidates.find(
    (candidate) => candidate.eventId === selectedEventId,
  );
  const refreshAudit = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] });
  };
  const decision = useMutation({
    mutationFn: async (action: "approve" | "reject") => {
      return postJson<ItemResponseMappingReview>(
        `/admin/mappings/${review.mappingReviewId}/${action}`,
        {
          candidateEventId: action === "approve" ? selectedCandidate?.eventId : undefined,
          reason: reason.trim(),
          reviewer: reviewer.trim(),
        },
      );
    },
    onSuccess: refreshAudit,
  });
  const aliasMutation = useMutation({
    mutationFn: () => {
      const canonicalTeamId = selectedCandidate?.selectionsInverted
        ? selectedCandidate.teamBId
        : selectedCandidate?.teamAId;
      return postJson<ItemResponseAliasRecord>("/admin/aliases", {
        alias: alias.trim(),
        canonicalId: canonicalTeamId,
        entityType: "team",
        provider: review.provider,
        reason: reason.trim() || "Alias créé pendant la revue du mapping",
        reviewer: reviewer.trim(),
      });
    },
    onSuccess: refreshAudit,
  });
  const canDecide = reviewer.trim().length > 0 && reason.trim().length > 0 && !decision.isPending;
  const canApprove = canDecide && selectedEventId.length > 0;
  const canCreateAlias =
    alias.trim().length > 0 &&
    reviewer.trim().length > 0 &&
    Boolean(selectedCandidate?.teamAId && selectedCandidate.teamBId) &&
    !aliasMutation.isPending;

  return (
    <Card aria-label={`Mapping ${review.providerEventId}`}>
      <CardContent className="grid gap-5 p-5 sm:p-6">
        {decision.data ? (
          <DecisionResult review={decision.data.data} />
        ) : (
          <div
            className="flex items-start gap-3 rounded-lg border border-red-300 bg-red-50/80 p-4 text-sm leading-6 text-red-950 dark:border-red-900 dark:bg-red-950/30 dark:text-red-100"
            role="alert"
          >
            <ShieldAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-semibold">Publication bloquée · décision explicite requise</p>
              <p>Cette ambiguïté reste bloquante tant qu’elle est en statut pending.</p>
            </div>
          </div>
        )}

        <section aria-labelledby={`raw-${review.mappingReviewId}`} className="grid gap-3">
          <h3
            className="flex items-center gap-2 font-semibold"
            id={`raw-${review.mappingReviewId}`}
          >
            <ListTree aria-hidden="true" className="size-4" />
            Événement brut
          </h3>
          <dl className="grid gap-3 rounded-lg bg-surface-muted p-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-ink-secondary">Provider / référence</dt>
              <dd className="mt-1 break-all font-semibold">
                {review.provider} · {review.providerEventId}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-secondary">Compétition brute</dt>
              <dd className="mt-1 font-semibold">{review.rawCompetition}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-ink-secondary">Participants bruts</dt>
              <dd className="mt-1 font-semibold">{review.rawParticipants.join(" — ")}</dd>
            </div>
          </dl>
        </section>

        <fieldset className="grid gap-3">
          <legend className="flex items-center gap-2 font-semibold">
            <GitMerge aria-hidden="true" className="size-4" />
            Candidats canoniques
          </legend>
          <div className="grid gap-3 lg:grid-cols-2">
            {review.candidates.map((candidate) => (
              <CandidateCard
                candidate={candidate}
                checked={candidate.eventId === selectedEventId}
                key={candidate.eventId}
                onSelect={() => {
                  setSelectedEventId(candidate.eventId);
                }}
              />
            ))}
          </div>
        </fieldset>

        <section
          aria-label="Aperçu d’impact"
          className="grid gap-2 rounded-lg border border-accent bg-accent-soft p-4 text-sm leading-6"
        >
          <p className="flex items-center gap-2 font-semibold">
            <Eye aria-hidden="true" className="size-4" />
            Aperçu d’impact
          </p>
          {selectedCandidate ? (
            <p>
              Une approbation auditera le rapprochement de « {review.rawParticipants.join(" — ")} »
              vers « {selectedCandidate.label} ». {review.affectedSnapshotCount} observation(s)
              existante(s) deviendront consultables sous l’événement canonique ; aucune cote ni
              aucun signal historique ne sera réécrit.
            </p>
          ) : (
            <p>Aucun candidat sélectionné : l’approbation reste désactivée.</p>
          )}
        </section>

        <section aria-label="Créer un alias daté" className="grid gap-3 rounded-lg border p-4">
          <h3 className="flex items-center gap-2 font-semibold">
            <Link2 aria-hidden="true" className="size-4" />
            Alias provider
          </h3>
          <label className="grid gap-1 text-sm" htmlFor={`alias-${review.mappingReviewId}`}>
            <span className="font-semibold">Alias brut</span>
            <input
              className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
              id={`alias-${review.mappingReviewId}`}
              onChange={(event) => {
                setAlias(event.currentTarget.value);
              }}
              value={alias}
            />
          </label>
          <p className="break-all text-xs text-ink-secondary">
            Destination équipe :{" "}
            {(selectedCandidate?.selectionsInverted
              ? selectedCandidate.teamBId
              : selectedCandidate?.teamAId) ?? "aucune"}
            . La date et l’approbateur sont enregistrés par le serveur.
          </p>
          <Button
            disabled={!canCreateAlias}
            onClick={() => {
              aliasMutation.mutate();
            }}
            variant="outline"
          >
            <Link2 aria-hidden="true" className="size-4" />
            {aliasMutation.isPending ? "Création…" : "Créer l’alias daté"}
          </Button>
          {aliasMutation.isError ? (
            <RemoteRecoverableErrorState
              compact
              description={aliasMutation.error.message}
              onRetry={() => {
                aliasMutation.mutate();
              }}
            />
          ) : null}
          {aliasMutation.data ? <AliasResult alias={aliasMutation.data.data} /> : null}
        </section>

        {!decision.data ? (
          <section aria-label="Décision de mapping" className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm" htmlFor={`reviewer-${review.mappingReviewId}`}>
                <span className="font-semibold">Relecteur</span>
                <input
                  className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
                  id={`reviewer-${review.mappingReviewId}`}
                  onChange={(event) => {
                    setReviewer(event.currentTarget.value);
                  }}
                  value={reviewer}
                />
              </label>
              <label className="grid gap-1 text-sm" htmlFor={`reason-${review.mappingReviewId}`}>
                <span className="font-semibold">Motif obligatoire</span>
                <input
                  className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3"
                  id={`reason-${review.mappingReviewId}`}
                  onChange={(event) => {
                    setReason(event.currentTarget.value);
                  }}
                  placeholder="Justifier la décision"
                  value={reason}
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={!canApprove}
                onClick={() => {
                  decision.mutate("approve");
                }}
              >
                <BadgeCheck aria-hidden="true" className="size-4" />
                Approuver le candidat
              </Button>
              <Button
                disabled={!canDecide}
                onClick={() => {
                  decision.mutate("reject");
                }}
                variant="outline"
              >
                <Ban aria-hidden="true" className="size-4" />
                Rejeter le mapping
              </Button>
            </div>
          </section>
        ) : null}

        {decision.isError ? (
          <RemoteRecoverableErrorState
            compact
            description={decision.error.message}
            onRetry={() => {
              decision.reset();
            }}
            retryLabel="Corriger la saisie"
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MappingReviewQueue() {
  const mappings = useQuery({
    queryFn: ({ signal }) => getPending(signal),
    queryKey: ["admin", "mappings", "pending"],
  });

  return (
    <Card aria-label="File de mapping">
      <CardContent className="grid gap-4 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="grid size-9 place-items-center rounded-lg bg-surface-muted text-ink-secondary"
          >
            <GitMerge className="size-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">File de mapping</h2>
            <p className="mt-1 text-xs text-ink-secondary">
              {mappings.data?.page.total ?? 0} ambiguïté en attente
            </p>
          </div>
        </div>
        {mappings.isError ? (
          <RemoteRecoverableErrorState
            description="La file reste inchangée ; rechargez-la avant toute décision."
            onRetry={() => void mappings.refetch()}
          />
        ) : (
          <RemoteDataBoundary
            isLoading={mappings.isPending}
            isRefetching={mappings.isFetching && !mappings.isPending}
            loadingFallback={<RemoteLoadingState minHeight="20rem" rows={6} />}
          >
            {mappings.data?.data.length ? (
              <div className="grid gap-4">
                {mappings.data.data.map((review) => (
                  <MappingReviewCard key={review.mappingReviewId} review={review} />
                ))}
              </div>
            ) : (
              <RemoteEmptyState description="Aucune ambiguïté de mapping n’attend de décision." />
            )}
          </RemoteDataBoundary>
        )}
        <p className="flex items-start gap-2 text-xs leading-5 text-ink-secondary">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Approbations, rejets et alias sont enregistrés dans le journal d’audit.
        </p>
      </CardContent>
    </Card>
  );
}
