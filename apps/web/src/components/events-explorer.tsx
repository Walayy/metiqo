"use client";

import type { Event, EventStatus, PageResponseEvent } from "@metiquo/contracts/types";
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
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Radio } from "lucide-react";
import Link from "next/link";

import { formatDateTime, formatTimeUntil } from "./opportunity-presenters";

const statusLabels = {
  cancelled: "Annulé",
  finished: "Terminé",
  live: "En direct",
  scheduled: "Planifié",
} satisfies Record<EventStatus, string>;

async function fetchEvents(signal: AbortSignal) {
  const response = await fetch("/api/backend/api/v1/events?offset=0&limit=100", {
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("La liste des événements n’est pas disponible");
  return (await response.json()) as PageResponseEvent;
}

function EventCard({ event, referenceTime }: Readonly<{ event: Event; referenceTime: string }>) {
  return (
    <Card aria-label={`${event.teamA} contre ${event.teamB}`}>
      <CardContent className="grid h-full gap-5 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
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
        <dl className="grid grid-cols-2 gap-4 border-y border-border-subtle py-4 text-sm">
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
            <dd className="mt-1 font-semibold">{formatTimeUntil(event.startsAt, referenceTime)}</dd>
          </div>
        </dl>
        <Button asChild className="mt-auto w-full" variant="outline">
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
  const eventsQuery = useQuery({
    queryFn: ({ signal }) => fetchEvents(signal),
    queryKey: ["events"],
  });

  return (
    <div className="grid gap-7">
      <header className="grid max-w-3xl gap-2">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
          <CalendarDays aria-hidden="true" className="size-4" />
          Calendrier canonique
        </p>
        <h1 className="text-title text-balance font-semibold tracking-tight">Événements</h1>
        <p className="text-body max-w-2xl text-ink-secondary">
          Participants, formats, marchés et historique des prix observés avant le début des matchs.
        </p>
      </header>

      <RemoteDataBoundary
        isLoading={eventsQuery.isPending}
        isRefetching={eventsQuery.isFetching && !eventsQuery.isPending}
        loadingFallback={<RemoteLoadingState label="Chargement des événements" rows={8} />}
      >
        {eventsQuery.isError ? (
          <RemoteRecoverableErrorState
            description="Le calendrier ne répond pas pour le moment."
            onRetry={() => void eventsQuery.refetch()}
          />
        ) : eventsQuery.data?.data.length === 0 ? (
          <RemoteEmptyState
            description="Aucun événement ne figure dans la fenêtre de données courante."
            title="Aucun événement"
          />
        ) : eventsQuery.data ? (
          <section aria-labelledby="events-title" className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold" id="events-title">
                  Matchs observés
                </h2>
                <p className="mt-1 text-xs text-ink-secondary">
                  {eventsQuery.data.page.total.toString()} événements
                </p>
              </div>
              <Badge className="border-accent bg-accent-soft text-ink-primary">
                <Radio aria-hidden="true" className="mr-1 size-3.5" />
                Données {eventsQuery.data.meta.dataMode}
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
          </section>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
