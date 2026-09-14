"use client";

import { QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend, requestBackend } from "../lib/backend";

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
  ContextPanel,
  InlineValues,
  Input,
  Radio,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
  Section,
  SelectionItem,
  TechnicalText,
  Textarea,
} from "@metiquo/ui";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
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
import { useEffect, useRef, useState } from "react";

import { formatDateTime, formatPercent } from "./opportunity-presenters";
import { PagedResults } from "./paged-results";

const MAPPINGS_PATH = "/api/backend/api/v1/admin/mappings";

async function getPending(offset: number, signal: AbortSignal): Promise<PageResponseMappingReview> {
  const response = await readBackend(
    `${MAPPINGS_PATH}/pending?offset=${String(offset)}&limit=100`,
    {
      headers: { accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) throw new Error("La file de mapping ne répond pas");
  return (await response.json()) as PageResponseMappingReview;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await requestBackend(`/api/backend/api/v1${path}`, {
    body: JSON.stringify(body),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
      "X-Metiquo-CSRF": "1",
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
  groupName,
  onSelect,
}: Readonly<{
  candidate: MappingCandidate;
  checked: boolean;
  groupName: string;
  onSelect: () => void;
}>) {
  const summary = `${candidate.label}, confiance ${formatPercent(Number(candidate.confidence))}`;
  return (
    <SelectionItem>
      <span className="flex items-start gap-3">
        <Radio
          aria-label={summary}
          checked={checked}
          name={groupName}
          onChange={onSelect}
          value={candidate.eventId}
        />
        <span className="min-w-0">
          <span className="block font-semibold">{candidate.label}</span>
          <TechnicalText className="mt-1 block">{candidate.eventId}</TechnicalText>
        </span>
      </span>
      <span aria-label={summary} className="grid gap-2" role="img">
        <span className="flex items-center justify-between text-xs">
          <span>Score global</span>
          <strong>{formatPercent(Number(candidate.confidence))}</strong>
        </span>
        <span className="ui-score-track">
          <span
            style={{
              width: `${Math.min(100, Math.max(0, Number(candidate.confidence) * 100)).toString()}%`,
            }}
          />
        </span>
      </span>
      <span className="grid gap-1">
        <span className="text-xs font-medium">Composantes du score</span>
        <span className="grid gap-1 text-xs leading-5 text-ink-secondary" role="list">
          {candidate.reasons.map((reason) => (
            <span key={reason} role="listitem">
              • {reason}
            </span>
          ))}
        </span>
      </span>
      {candidate.selectionsInverted ? (
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">
          Participants inversés : les sélections A/B seront remappées.
        </span>
      ) : null}
    </SelectionItem>
  );
}

function DecisionResult({ review }: Readonly<{ review: MappingReview }>) {
  return (
    <ContextPanel aria-live="polite" role="status" tone="success">
      <p className="flex items-center gap-2 font-semibold">
        <BadgeCheck aria-hidden="true" className="size-4" />
        Décision {review.status}
      </p>
      <p>
        {review.reviewer} · {review.reviewedAt ? formatDateTime(review.reviewedAt) : "date absente"}
      </p>
      <p className="text-xs text-ink-secondary">{review.decisionReason}</p>
    </ContextPanel>
  );
}

function AliasResult({ alias }: Readonly<{ alias: AliasRecord }>) {
  return (
    <ContextPanel aria-live="polite" role="status" tone="success">
      <p className="font-semibold">Alias créé et daté</p>
      <p className="mt-1">
        {alias.alias} → <TechnicalText>{alias.canonicalId}</TechnicalText>
      </p>
      <p className="mt-1 text-xs text-ink-secondary">Créé le {formatDateTime(alias.createdAt)}</p>
    </ContextPanel>
  );
}

function MappingReviewCard({ review }: Readonly<{ review: MappingReview }>) {
  const queryClient = useQueryClient();
  const [selectedEventId, setSelectedEventId] = useState(review.selectedEventId ?? "");
  const [reviewer, setReviewer] = useState("admin-local");
  const [reason, setReason] = useState("");
  const [alias, setAlias] = useState(review.rawParticipants[0] ?? "");
  const reasonInput = useRef<HTMLTextAreaElement>(null);
  const resultFocus = useRef<HTMLDivElement>(null);
  const selectedCandidate = review.candidates.find(
    (candidate) => candidate.eventId === selectedEventId,
  );
  const canonicalTeamId = selectedCandidate?.selectionsInverted
    ? selectedCandidate.teamBId
    : selectedCandidate?.teamAId;
  const canonicalTeamName = selectedCandidate?.selectionsInverted
    ? selectedCandidate.teamB
    : selectedCandidate?.teamA;
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
    onSuccess: async (response) => {
      queryClient.setQueryData<InfiniteData<PageResponseMappingReview, number>>(
        ["admin", "mappings", "pending"],
        (current) =>
          current
            ? {
                ...current,
                pages: current.pages.map((page) => ({
                  ...page,
                  data: page.data.map((item) =>
                    item.mappingReviewId === review.mappingReviewId ? response.data : item,
                  ),
                })),
              }
            : current,
      );
      await refreshAudit();
    },
  });
  const aliasMutation = useMutation({
    mutationFn: () => {
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
  const isBusy = decision.isPending || aliasMutation.isPending;
  const currentDecision = decision.data?.data ?? (review.status !== "pending" ? review : undefined);
  const canDecide = reviewer.trim().length > 0 && reason.trim().length > 0 && !isBusy;
  const canApprove = canDecide && Boolean(selectedCandidate);
  const canCreateAlias =
    alias.trim().length > 0 &&
    reviewer.trim().length > 0 &&
    Boolean(canonicalTeamId) &&
    !currentDecision &&
    !isBusy;

  useEffect(() => {
    if (decision.isSuccess) resultFocus.current?.focus();
  }, [decision.isSuccess]);

  return (
    <Card aria-label={`Mapping ${review.providerEventId}`} variant="flat">
      <CardContent className="grid gap-6 py-0">
        {currentDecision ? (
          <div
            className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus"
            ref={resultFocus}
            tabIndex={-1}
          >
            <DecisionResult review={currentDecision} />
          </div>
        ) : (
          <ContextPanel className="flex items-start gap-3" role="alert" tone="danger">
            <ShieldAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-semibold">Publication bloquée · décision explicite requise</p>
              <p>
                Choisissez un candidat puis justifiez votre décision pour lever cette ambiguïté.
              </p>
            </div>
          </ContextPanel>
        )}

        <section aria-labelledby={`raw-${review.mappingReviewId}`} className="grid gap-3">
          <h3
            className="flex items-center gap-2 font-semibold"
            id={`raw-${review.mappingReviewId}`}
          >
            <ListTree aria-hidden="true" className="size-4" />
            Événement brut
          </h3>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-ink-secondary">Provider / référence</dt>
              <dd className="mt-1 grid gap-1">
                <span className="font-medium">{review.provider}</span>
                <TechnicalText>{review.providerEventId}</TechnicalText>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-secondary">Compétition brute</dt>
              <dd className="mt-1 font-semibold">{review.rawCompetition}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-ink-secondary">Participants bruts</dt>
              <dd className="mt-1 font-semibold">
                <InlineValues items={review.rawParticipants} separator="—" />
              </dd>
            </div>
          </dl>
        </section>

        <fieldset className="grid min-w-0 gap-3" disabled={isBusy || Boolean(currentDecision)}>
          <legend className="flex items-center gap-2 font-semibold">
            <GitMerge aria-hidden="true" className="size-4" />
            Candidats canoniques
          </legend>
          {!currentDecision && review.candidates.length > 0 ? (
            <p className="text-xs text-ink-secondary">
              Comparez les candidats et sélectionnez celui à rapprocher. Aucun choix n’est fait
              automatiquement.
            </p>
          ) : null}
          <div className="grid min-w-0 gap-3 lg:grid-cols-2">
            {review.candidates.map((candidate) => (
              <CandidateCard
                candidate={candidate}
                checked={candidate.eventId === selectedEventId}
                groupName={`mapping-candidate-${review.mappingReviewId}`}
                key={candidate.eventId}
                onSelect={() => {
                  setSelectedEventId(candidate.eventId);
                  aliasMutation.reset();
                }}
              />
            ))}
          </div>
          {review.candidates.length === 0 ? (
            <p className="text-sm text-ink-secondary">
              Aucun candidat disponible. Vous pouvez rejeter ce mapping en indiquant un motif.
            </p>
          ) : null}
        </fieldset>

        <ContextPanel aria-label="Aperçu d’impact" role="region" tone="info">
          <p className="flex items-center gap-2 font-semibold">
            <Eye aria-hidden="true" className="size-4" />
            Aperçu d’impact
          </p>
          {selectedCandidate ? (
            <p>
              {currentDecision?.status === "approved"
                ? "Rapprochement approuvé de"
                : "Une approbation auditera le rapprochement de"}{" "}
              « {review.rawParticipants.join(" — ")} » vers « {selectedCandidate.label} ».{" "}
              {review.affectedSnapshotCount == null
                ? "Les observations existantes"
                : `${String(review.affectedSnapshotCount)} observation(s) existante(s)`}
              {currentDecision?.status === "approved"
                ? " sont consultables"
                : " deviendront consultables"}{" "}
              sous l’événement canonique ; aucune cote ni aucun signal historique ne sera réécrit.
            </p>
          ) : (
            <p>Aucun candidat sélectionné : l’approbation reste désactivée.</p>
          )}
        </ContextPanel>

        {!currentDecision ? (
          <Section aria-label="Créer un alias daté">
            <h3 className="flex items-center gap-2 font-semibold">
              <Link2 aria-hidden="true" className="size-4" />
              Alias provider
            </h3>
            <label className="ui-field max-w-xl" htmlFor={`alias-${review.mappingReviewId}`}>
              <span className="font-semibold">Alias brut</span>
              <Input
                id={`alias-${review.mappingReviewId}`}
                aria-describedby={`alias-help-${review.mappingReviewId}`}
                readOnly={isBusy}
                required
                onChange={(event) => {
                  setAlias(event.currentTarget.value);
                  aliasMutation.reset();
                }}
                value={alias}
              />
            </label>
            <p
              className="text-xs leading-5 text-ink-secondary"
              id={`alias-help-${review.mappingReviewId}`}
            >
              Destination équipe :{" "}
              {canonicalTeamName ? <strong>{canonicalTeamName} · </strong> : null}
              <TechnicalText>{canonicalTeamId ?? "aucune"}</TechnicalText>
              <span className="mt-1 block">
                La date et l’approbateur sont enregistrés par le serveur.
              </span>
              {!selectedCandidate ? (
                <span className="mt-1 block">
                  Sélectionnez un candidat ci-dessus pour choisir l’équipe de destination.
                </span>
              ) : !reviewer.trim() ? (
                <span className="mt-1 block">
                  Renseignez le relecteur ci-dessous pour créer cet alias.
                </span>
              ) : null}
            </p>
            <Button
              aria-busy={aliasMutation.isPending}
              className="justify-self-start"
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
                retryDisabled={!canCreateAlias}
                onRetry={() => {
                  aliasMutation.mutate();
                }}
              />
            ) : null}
            {aliasMutation.data ? <AliasResult alias={aliasMutation.data.data} /> : null}
          </Section>
        ) : aliasMutation.data ? (
          <AliasResult alias={aliasMutation.data.data} />
        ) : null}

        {!currentDecision ? (
          <Section aria-label="Décision de mapping">
            <div className="grid items-start gap-3 sm:grid-cols-2">
              <label className="ui-field" htmlFor={`reviewer-${review.mappingReviewId}`}>
                <span className="font-semibold">Relecteur</span>
                <Input
                  aria-describedby={`decision-help-${review.mappingReviewId}`}
                  id={`reviewer-${review.mappingReviewId}`}
                  readOnly={isBusy}
                  required
                  onChange={(event) => {
                    setReviewer(event.currentTarget.value);
                  }}
                  value={reviewer}
                />
              </label>
              <label className="ui-field" htmlFor={`reason-${review.mappingReviewId}`}>
                <span className="font-semibold">Motif obligatoire</span>
                <Textarea
                  aria-describedby={`decision-help-${review.mappingReviewId}`}
                  id={`reason-${review.mappingReviewId}`}
                  readOnly={isBusy}
                  ref={reasonInput}
                  required
                  rows={3}
                  onChange={(event) => {
                    setReason(event.currentTarget.value);
                  }}
                  placeholder="Justifier la décision"
                  value={reason}
                />
              </label>
            </div>
            <p
              className="text-xs text-ink-secondary"
              id={`decision-help-${review.mappingReviewId}`}
            >
              Le relecteur et le motif sont obligatoires pour enregistrer une décision.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                aria-busy={decision.isPending && decision.variables === "approve"}
                disabled={!canApprove}
                onClick={() => {
                  decision.mutate("approve");
                }}
              >
                <BadgeCheck aria-hidden="true" className="size-4" />
                {decision.isPending && decision.variables === "approve"
                  ? "Approbation…"
                  : "Approuver le candidat"}
              </Button>
              <Button
                aria-busy={decision.isPending && decision.variables === "reject"}
                disabled={!canDecide}
                onClick={() => {
                  decision.mutate("reject");
                }}
                variant="outline"
              >
                <Ban aria-hidden="true" className="size-4" />
                {decision.isPending && decision.variables === "reject"
                  ? "Rejet…"
                  : "Rejeter le mapping"}
              </Button>
            </div>
          </Section>
        ) : null}

        {decision.isError ? (
          <RemoteRecoverableErrorState
            compact
            description={decision.error.message}
            onRetry={() => {
              decision.reset();
              reasonInput.current?.focus();
            }}
            retryLabel="Corriger la saisie"
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MappingReviewQueue() {
  const mappings = useInfiniteQuery({
    initialPageParam: 0,
    getNextPageParam: (lastPage: PageResponseMappingReview, pages: PageResponseMappingReview[]) => {
      const loaded = pages.flatMap((page) => page.data);
      // Resolved reviews leave the server's pending queue; exclude them from the next offset.
      const next = loaded.filter((review) => review.status === "pending").length;
      return lastPage.data.length > 0 && loaded.length < (pages[0]?.page.total ?? 0)
        ? next
        : undefined;
    },
    queryFn: ({ signal, pageParam }) => getPending(pageParam, signal),
    queryKey: ["admin", "mappings", "pending"],
    select: ({ pages }) =>
      ({ ...pages[0], data: pages.flatMap((page) => page.data) }) as PageResponseMappingReview,
  });
  const pendingCount = mappings.data
    ? Math.max(
        0,
        mappings.data.page.total -
          mappings.data.data.filter((review) => review.status !== "pending").length,
      )
    : 0;

  return (
    <Card aria-label="File de mapping">
      <CardContent className="grid gap-4">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="text-ink-secondary">
            <GitMerge className="size-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">File de mapping</h2>
            <p className="mt-1 text-xs text-ink-secondary">
              {mappings.isPending
                ? "Chargement des ambiguïtés…"
                : mappings.data
                  ? `${String(pendingCount)} ambiguïté${pendingCount > 1 ? "s" : ""} en attente`
                  : "Nombre d’ambiguïtés indisponible"}
            </p>
          </div>
        </div>
        <QueryRecovery queries={[mappings]} />
        {mappings.isError && !canReadPrevious(mappings) ? (
          <RemoteRecoverableErrorState
            description="La file reste inchangée ; rechargez-la avant toute décision."
            onRetry={() => void mappings.refetch()}
            retryDisabled={mappings.isFetching}
          />
        ) : (
          <RemoteDataBoundary
            isLoading={mappings.isPending}
            isRefetching={mappings.isFetching && !mappings.isPending}
            loadingFallback={<RemoteLoadingState minHeight="20rem" rows={6} />}
          >
            {mappings.data?.data.length ? (
              <div className="grid gap-6 divide-y divide-border-subtle">
                {mappings.data.data.map((review) => (
                  <MappingReviewCard key={review.mappingReviewId} review={review} />
                ))}
              </div>
            ) : (
              <RemoteEmptyState description="Aucune ambiguïté de mapping n’attend de décision." />
            )}
          </RemoteDataBoundary>
        )}
        <PagedResults label="de mappings" query={mappings} />
        <p className="flex items-start gap-2 text-xs leading-5 text-ink-secondary">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Approbations, rejets et alias sont enregistrés dans le journal d’audit.
        </p>
      </CardContent>
    </Card>
  );
}
