"use client";

import { QueryRecovery } from "./query-recovery";

import { canReadPrevious, readBackend } from "../lib/backend";

import type { Event, EventStatus, PageResponseEvent } from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Select,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemotePageLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Radio } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { formatDateTime, formatTimeUntil } from "./opportunity-presenters";

const statusLabels = {
  cancelled: "Annulé",
  finished: "Terminé",
  live: "En direct",
  scheduled: "Planifié",
} satisfies Record<EventStatus, string>;

async function fetchEvents(parameters: string, signal: AbortSignal) {
  const response = await readBackend(`/api/backend/api/v1/events?${parameters}`, {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La liste des événements n’est pas disponible");
  return (await response.json()) as PageResponseEvent;
}

function EventCard({ event, referenceTime }: Readonly<{ event: Event; referenceTime: string }>) {
  return (
    <Card aria-label={`${event.teamA} contre ${event.teamB}`}>
      <CardContent className="grid h-full gap-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-secondary">
              {event.competition}
            </p>
            <h2 className="mt-2 text-xl font-semibold tracking-tight">
              {event.teamA} <span className="text-ink-secondary">vs</span> {event.teamB}
            </h2>
          </div>
          <Badge className="border-border-strong bg-surface-muted text-ink-primary">
            {statusLabels[event.status]}
          </Badge>
        </div>
        <dl className="grid grid-cols-2 gap-3 border-t border-border-subtle pt-3 text-sm">
          <div>
            <dt className="text-xs text-ink-secondary">Début</dt>
            <dd className="mt-1 font-semibold">{formatDateTime(event.startsAt)}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-secondary">Format</dt>
            <dd className="mt-1 font-semibold">Best of {event.bestOf.toString()}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-ink-secondary">Échéance</dt>
            <dd className="mt-1 font-semibold">
              {event.status === "scheduled"
                ? formatTimeUntil(event.startsAt, referenceTime)
                : statusLabels[event.status]}
            </dd>
          </div>
        </dl>
        <Button asChild className="mt-auto w-fit" variant="outline">
          <Link href={`/events/${encodeURIComponent(event.eventId)}`}>
            Ouvrir la fiche
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export function EventsExplorer() {
  const router = useRouter();
  const searchParameters = useSearchParams();
  const competition = searchParameters.get("competition")?.trim() ?? "";
  const team = searchParameters.get("team")?.trim() ?? "";
  const rawStatus = searchParameters.get("status") ?? "";
  const status = Object.hasOwn(statusLabels, rawStatus) ? rawStatus : "";
  const rawOffset = Number(searchParameters.get("offset") ?? 0);
  const offset =
    Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? Math.floor(rawOffset / 100) * 100 : 0;
  const [draft, setDraft] = useState({ competition, team, status });
  useEffect(() => {
    setDraft({ competition, team, status });
  }, [competition, team, status]);
  const filters = new URLSearchParams({ offset: String(offset), limit: "100" });
  if (competition) filters.set("competition", competition);
  if (team) filters.set("team", team);
  if (status) filters.set("status", status);
  const parameters = filters.toString();
  const hasFilters = Boolean(competition || team || status);
  const setOffset = (nextOffset: number) => {
    const next = new URLSearchParams(searchParameters.toString());
    if (nextOffset) next.set("offset", String(nextOffset));
    else next.delete("offset");
    router.push(`/events${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
  };
  const eventsQuery = useQuery({
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => fetchEvents(parameters, signal),
    queryKey: ["events", parameters],
  });

  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-2">
        <p className="flex items-center gap-2 ui-eyebrow">
          <CalendarDays aria-hidden="true" className="size-4" />
          Calendrier canonique
        </p>
        <h1 className="ui-page-title">Événements</h1>
        <p className="text-body max-w-2xl text-ink-secondary">
          Participants, formats, marchés et historique des prix observés avant le début des matchs.
        </p>
      </header>

      <Card aria-label="Filtrer les événements">
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_auto_auto] xl:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              const next = new URLSearchParams();
              for (const [key, value] of Object.entries(draft)) {
                if (value.trim()) next.set(key, value.trim());
              }
              router.push(`/events${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
            }}
          >
            <label className="ui-field" htmlFor="events-competition">
              Ligue
              <Input
                id="events-competition"
                value={draft.competition}
                placeholder="Ex. Ligue Démo 02"
                onChange={(event) => {
                  setDraft({ ...draft, competition: event.currentTarget.value });
                }}
              />
            </label>
            <label className="ui-field" htmlFor="events-team">
              Équipe
              <Input
                id="events-team"
                value={draft.team}
                placeholder="Ex. Aurore"
                onChange={(event) => {
                  setDraft({ ...draft, team: event.currentTarget.value });
                }}
              />
            </label>
            <label className="ui-field" htmlFor="events-status">
              Statut
              <Select
                id="events-status"
                value={draft.status}
                onValueChange={(value) => {
                  setDraft({ ...draft, status: value });
                }}
              >
                <option value="">Tous les statuts</option>
                {Object.entries(statusLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </label>
            <Button type="submit">Appliquer</Button>
            <Button asChild variant="ghost">
              <Link href="/events" scroll={false}>
                Effacer
              </Link>
            </Button>
          </form>
        </CardContent>
      </Card>

      <RemoteDataBoundary
        isLoading={eventsQuery.isPending}
        isRefetching={eventsQuery.isFetching && !eventsQuery.isPending}
        loadingFallback={<RemotePageLoadingState label="Chargement des événements" rows={8} />}
      >
        <QueryRecovery queries={[eventsQuery]} />
        {eventsQuery.isError && !canReadPrevious(eventsQuery) ? (
          <RemoteRecoverableErrorState
            description="Le calendrier ne répond pas pour le moment."
            onRetry={() => void eventsQuery.refetch()}
            retryDisabled={eventsQuery.isFetching}
          />
        ) : eventsQuery.data?.data.length === 0 ? (
          <RemoteEmptyState
            action={
              offset > 0 ? (
                <Button
                  onClick={() => {
                    setOffset(0);
                  }}
                  variant="outline"
                  size="small"
                >
                  Revenir à la première page
                </Button>
              ) : hasFilters ? (
                <Button asChild variant="outline" size="small">
                  <Link href="/events" scroll={false}>
                    Réinitialiser les filtres
                  </Link>
                </Button>
              ) : (
                <Button asChild variant="outline" size="small">
                  <Link href="/data">Vérifier les sources de données</Link>
                </Button>
              )
            }
            description={
              offset > 0
                ? "Cette page est vide. Revenez à la première page pour retrouver les événements disponibles."
                : hasFilters
                  ? "Aucun événement ne correspond aux filtres sélectionnés. Modifiez vos critères ou réinitialisez les filtres."
                  : "Aucun événement ne figure dans la fenêtre de données courante. Vérifiez les sources pour alimenter le calendrier."
            }
            title={hasFilters ? "Aucun événement correspondant" : "Aucun événement"}
          />
        ) : eventsQuery.data ? (
          <section aria-labelledby="events-title" className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="ui-section-title" id="events-title">
                  Matchs observés
                </h2>
                <p className="mt-1 text-xs text-ink-secondary" role="status">
                  {eventsQuery.data.page.total.toString()} événement
                  {eventsQuery.data.page.total === 1 ? "" : "s"}
                </p>
              </div>
              <Badge className="border-border-subtle bg-accent-soft text-ink-primary">
                <Radio aria-hidden="true" className="mr-1 size-3.5" />
                Données {eventsQuery.data.meta.dataMode === "mock" ? "simulées" : "réelles"}
              </Badge>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {eventsQuery.data.data.map((event) => (
                <EventCard
                  event={event}
                  key={event.eventId}
                  referenceTime={eventsQuery.data.meta.computedAt}
                />
              ))}
            </div>
            {eventsQuery.data.page.total > 100 || offset > 0 ? (
              <nav
                aria-label="Pagination des événements"
                className="flex flex-wrap items-center justify-between gap-3"
              >
                <Button
                  disabled={offset === 0 || eventsQuery.isFetching}
                  onClick={() => {
                    setOffset(Math.max(0, offset - 100));
                  }}
                  variant="outline"
                >
                  Page précédente
                </Button>
                <p className="text-sm text-ink-secondary" role="status">
                  Page {Math.floor(eventsQuery.data.page.offset / 100) + 1} sur{" "}
                  {Math.max(1, Math.ceil(eventsQuery.data.page.total / 100))}
                </p>
                <Button
                  disabled={offset + 100 >= eventsQuery.data.page.total || eventsQuery.isFetching}
                  onClick={() => {
                    setOffset(offset + 100);
                  }}
                  variant="outline"
                >
                  Page suivante
                </Button>
              </nav>
            ) : null}
          </section>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
