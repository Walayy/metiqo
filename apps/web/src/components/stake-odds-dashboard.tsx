"use client";

import type {
  ItemResponseStakeCollectionStatus,
  PageResponseStakePublicEvent,
  StakePublicEvent,
} from "@metiquo/contracts/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteSkeleton,
} from "@metiquo/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { canReadPrevious, readBackend } from "../lib/backend";
import { formatDateTime } from "./opportunity-presenters";
import { QueryFailure, QueryRecovery } from "./query-recovery";

const states = {
  disabled: "Collecte désactivée",
  never_collected: "Première collecte en attente",
  operational: "Collecte active",
  partial: "Collecte partielle",
  blocked: "Accès bloqué par Stake",
  failed: "Échec de collecte",
  stale: "Collecte en retard",
};
const collectionDescriptions = {
  disabled: "La collecte automatique des pages Stake n’est pas activée dans cet environnement.",
  never_collected:
    "La collecte est activée. Les premiers matchs apparaîtront après une lecture réussie.",
  operational:
    "Les pages publiques sont collectées automatiquement. Chaque prix conserve sa date d’observation.",
  partial: "Certains matchs ou marchés n’ont pas pu être lus. La collecte reste incomplète.",
  blocked:
    "Stake refuse actuellement l’accès du collecteur. Les anciennes observations conservent leur date.",
  failed:
    "La dernière collecte a échoué. Les prix déjà enregistrés restent consultables avec leur date d’observation.",
  stale: "Aucune observation récente n’a été reçue. Vérifiez la date de capture de chaque marché.",
};
const freshnessLabels = {
  fresh: "Observation récente",
  stale: "Cotes périmées",
  degraded: "Collecte dégradée",
  failed: "Observation indisponible",
  quarantined: "Observation en quarantaine",
};

function marketTabLabel(tab: string) {
  if (tab === "tab-main") return "Match et série";
  return /^tab-map-\d+$/.test(tab) ? `Carte ${tab.replace("tab-map-", "")}` : "Autres marchés";
}

const MARKETS_PER_PAGE = 8;

function normalizeMarketName(value: string) {
  return value
    .trim()
    .toLocaleLowerCase("fr-FR")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

async function fetchStake<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await readBackend(`/api/backend/api/v1/odds/stake/${path}`, { signal });
  if (!response.ok) throw new Error("La collecte Stake ne répond pas");
  return (await response.json()) as T;
}

function StakeEventCard({ value }: { value: StakePublicEvent }) {
  const id = useId();
  const [tab, setTab] = useState("tab-main");
  const [marketSearch, setMarketSearch] = useState("");
  const [visibleMarketCount, setVisibleMarketCount] = useState(MARKETS_PER_PAGE);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, []);
  const expired =
    value.freshness === "stale" || (now !== null && now > Date.parse(value.expiresAt));
  const capture = value.capture;
  const tabs = [...new Set(capture.markets.map((m) => m.tab))];
  const activeTab = tabs.includes(tab) ? tab : tabs[0];
  const markets = capture.markets.filter((m) => m.tab === activeTab);
  const search = normalizeMarketName(marketSearch);
  const filteredMarkets = markets.filter((market) =>
    normalizeMarketName(market.label).includes(search),
  );
  const visibleMarkets = filteredMarkets.slice(0, visibleMarketCount);
  const hasMoreMarkets = visibleMarkets.length < filteredMarkets.length;
  return (
    <Card aria-label={`Marchés de ${capture.event.participants.join(" contre ")}`}>
      <CardContent className="grid min-w-0 gap-4">
        <p className="ui-eyebrow">Stake · {capture.event.competition}</p>
        <h3 className="break-words text-xl font-semibold">
          {capture.event.participants.join(" vs ")}
        </h3>
        <p className="text-sm text-ink-secondary">
          {formatDateTime(capture.event.startsAt)} · Format{" "}
          {capture.event.bestOf ? `BO${String(capture.event.bestOf)}` : "non confirmé"}
        </p>
        <div className="flex flex-wrap gap-2">
          <Badge>
            {expired && value.freshness === "fresh"
              ? "Cotes périmées"
              : freshnessLabels[value.freshness]}
          </Badge>
          <Badge>Information uniquement</Badge>
          <span className="text-sm text-ink-secondary">
            Âge au dernier contrôle : {value.ageSeconds} s
          </span>
        </div>
        {capture.warnings.length > 0 ? (
          <p className="ui-inline-notice">Certains marchés n’ont pas pu être lus entièrement.</p>
        ) : null}
        {tabs.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-semibold">
              Marchés de {capture.event.participants.join(" – ")}
              <select
                className="metiquo-input w-full"
                value={activeTab}
                onChange={(event) => {
                  setTab(event.target.value);
                  setVisibleMarketCount(MARKETS_PER_PAGE);
                }}
              >
                {tabs.map((id) => (
                  <option key={id} value={id}>
                    {marketTabLabel(id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-semibold" htmlFor={`${id}-market-search`}>
              Rechercher un marché
              <Input
                id={`${id}-market-search`}
                type="search"
                aria-label={`Rechercher un marché pour ${capture.event.participants.join(" contre ")}`}
                aria-controls={`${id}-markets`}
                value={marketSearch}
                placeholder="Ex. handicap, total, vainqueur"
                onChange={(event) => {
                  setMarketSearch(event.target.value);
                  setVisibleMarketCount(MARKETS_PER_PAGE);
                }}
              />
            </label>
          </div>
        ) : (
          <p className="ui-inline-notice" role="status">
            Aucun marché lisible pour ce match. Une prochaine collecte pourra compléter cette
            observation.
          </p>
        )}
        {tabs.length > 0 ? (
          <p className="text-sm text-ink-secondary" role="status" aria-atomic="true">
            {visibleMarkets.length} marché{visibleMarkets.length === 1 ? "" : "s"} affiché
            {visibleMarkets.length === 1 ? "" : "s"} sur {filteredMarkets.length}
            {search
              ? ` correspondant${filteredMarkets.length === 1 ? "" : "s"} à votre recherche`
              : ` · ${marketTabLabel(activeTab ?? "tab-main")}`}
          </p>
        ) : null}
        <div className="grid gap-3" id={`${id}-markets`}>
          {visibleMarkets.map((market, index) => (
            <details
              key={`${market.tab}:${market.label}`}
              className="min-w-0 rounded border border-border-subtle p-3"
              open={index === 0}
            >
              <summary className="cursor-pointer break-words py-1 font-semibold">
                {market.label}{" "}
                <span className="font-normal text-ink-secondary">({market.outcomes.length})</span>
              </summary>
              <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                {market.outcomes.map((outcome, index) => (
                  <li
                    key={`${outcome.label}:${String(index)}`}
                    className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded bg-surface-muted p-3"
                  >
                    <span className="min-w-0 break-words">{outcome.label}</span>
                    <span className="shrink-0 font-bold tabular-nums">
                      {outcome.status !== "open"
                        ? outcome.status === "suspended"
                          ? "Suspendu"
                          : "Indisponible"
                        : outcome.decimalOdds === null ||
                            !Number.isFinite(Number(outcome.decimalOdds))
                          ? "Cote indisponible"
                          : Number(outcome.decimalOdds).toLocaleString("fr-FR", {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 8,
                            })}
                    </span>
                  </li>
                ))}
              </ul>
              {market.outcomes.length === 0 ? (
                <p>Les sélections de ce marché ne sont pas disponibles.</p>
              ) : null}
              <p className="mt-3 text-xs text-ink-secondary">
                Observé le {formatDateTime(market.capturedAt)}
              </p>
            </details>
          ))}
          {markets.length > 0 && filteredMarkets.length === 0 ? (
            <div className="grid justify-items-start gap-3">
              <p className="text-sm text-ink-secondary">
                Aucun marché ne correspond à « {marketSearch.trim()} » dans cette période.
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  setMarketSearch("");
                  setVisibleMarketCount(MARKETS_PER_PAGE);
                  document.getElementById(`${id}-market-search`)?.focus();
                }}
              >
                Effacer la recherche
              </Button>
            </div>
          ) : null}
        </div>
        {filteredMarkets.length > MARKETS_PER_PAGE || visibleMarketCount > MARKETS_PER_PAGE ? (
          <Button
            className="justify-self-start"
            variant="outline"
            aria-controls={`${id}-markets`}
            aria-disabled={!hasMoreMarkets}
            onClick={() => {
              if (!hasMoreMarkets) return;
              setVisibleMarketCount((count) => count + MARKETS_PER_PAGE);
            }}
          >
            {hasMoreMarkets ? "Afficher plus de marchés" : "Tous les marchés sont affichés"}
          </Button>
        ) : null}
        <a className="text-sm underline" href={capture.sourceUrl} target="_blank" rel="noreferrer">
          Voir la page source sur Stake
          <span className="sr-only"> (nouvel onglet)</span>
        </a>
      </CardContent>
    </Card>
  );
}

export function StakeOddsDashboard() {
  const [offset, setOffset] = useState(0);
  const [includePast, setIncludePast] = useState(false);
  const status = useQuery({
    queryKey: ["stake-status"],
    queryFn: ({ signal }) => fetchStake<ItemResponseStakeCollectionStatus>("status", signal),
    refetchInterval: 15_000,
  });
  const events = useQuery({
    queryKey: ["stake-events", offset, includePast],
    queryFn: ({ signal }) =>
      fetchStake<PageResponseStakePublicEvent>(
        `events?offset=${String(offset)}&limit=5${includePast ? "" : `&startsFrom=${encodeURIComponent(new Date().toISOString())}`}`,
        signal,
      ),
    refetchInterval: 15_000,
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[2] === includePast ? previousData : undefined,
  });
  const current = canReadPrevious(status) ? status.data?.data : undefined;
  const statusUnavailable = status.isError && !canReadPrevious(status);
  const eventsUnavailable = events.isError && !canReadPrevious(events);
  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-2">
        <h2 className="ui-section-title">Marchés Stake</h2>
        <p className="text-body text-ink-secondary">
          Matchs et marchés lus sur les pages publiques de Stake. Ces prix sont présentés à titre
          informatif ; leur date de capture indique leur ancienneté.
        </p>
      </header>
      <label className="flex min-h-10 cursor-pointer items-center gap-3 text-sm">
        <input
          type="checkbox"
          className="h-4 w-4 shrink-0"
          checked={includePast}
          onChange={(event) => {
            setIncludePast(event.target.checked);
            setOffset(0);
          }}
        />
        Inclure les matchs déjà commencés
      </label>
      {canReadPrevious(status) && canReadPrevious(events) ? (
        <QueryRecovery queries={[status, events]} />
      ) : (
        <>
          <QueryRecovery queries={[status]} />
          <QueryRecovery queries={[events]} />
        </>
      )}
      {statusUnavailable ? (
        <QueryFailure
          description={
            eventsUnavailable
              ? "L’état du collecteur et les marchés enregistrés sont indisponibles."
              : "L’état du collecteur est indisponible."
          }
          missingTitle="Collecteur indisponible"
          missingDescription="L’état de ce collecteur n’est plus disponible."
          queries={eventsUnavailable ? [status, events] : [status]}
        />
      ) : null}
      {current || status.isPending ? (
        <Card aria-label="État de la collecte Stake" aria-busy={status.isFetching}>
          <CardContent className="grid gap-2">
            {current ? (
              <>
                <h3 className="font-semibold">{states[current.state]}</h3>
                <p className="min-h-15 text-sm text-ink-secondary sm:min-h-5">
                  {collectionDescriptions[current.state]}
                </p>
                {current.checkedAt ? (
                  <p className="text-sm text-ink-secondary">
                    Dernière tentative : {formatDateTime(current.checkedAt)}
                  </p>
                ) : null}
                {current.lastSuccessAt ? (
                  <p className="text-sm text-ink-secondary">
                    Dernière observation : {formatDateTime(current.lastSuccessAt)}
                  </p>
                ) : null}
                {current.enabled && current.nextAttemptAt ? (
                  <p className="text-sm text-ink-secondary">
                    Prochaine tentative au plus tôt : {formatDateTime(current.nextAttemptAt)}
                  </p>
                ) : null}
              </>
            ) : (
              <div className="grid gap-2" role="status" aria-label="Vérification de la collecte">
                <RemoteSkeleton height="1.5rem" width="min(100%, 14rem)" />
                <RemoteSkeleton className="min-h-15 sm:min-h-5" height="1.25rem" width="100%" />
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-ink-secondary">
          Lecture automatique toutes les 15 secondes. Actualiser l’affichage relit les données
          enregistrées et ne déclenche pas de collecte sur Stake.
        </p>
        <div className="flex flex-wrap gap-2">
          {offset > 0 ? (
            <Button
              variant="outline"
              disabled={events.isFetching}
              onClick={() => {
                setOffset(0);
              }}
            >
              Première page
            </Button>
          ) : null}
          <Button
            variant="outline"
            disabled={events.isFetching || status.isFetching}
            onClick={() => {
              void events.refetch();
              void status.refetch();
            }}
          >
            {(events.isFetching && !events.isPending) || (status.isFetching && !status.isPending)
              ? "Actualisation…"
              : "Actualiser l’affichage"}
          </Button>
        </div>
      </div>
      <RemoteDataBoundary
        isLoading={events.isPending}
        loadingFallback={
          <RemoteLoadingState label="Chargement des marchés Stake" minHeight="12rem" rows={3} />
        }
        isRefetching={events.isFetching && !events.isPending}
        refetchLabel="Actualisation des marchés Stake"
      >
        {eventsUnavailable ? (
          statusUnavailable ? null : (
            <QueryFailure
              description="Les marchés collectés sont indisponibles."
              missingTitle="Marchés indisponibles"
              missingDescription="Cette page de marchés n’est plus disponible."
              queries={[events]}
            />
          )
        ) : events.data?.data.length === 0 ? (
          <RemoteEmptyState
            title={offset > 0 ? "Aucun match sur cette page" : "Aucun match collecté"}
            description={
              offset > 0
                ? "Les résultats ont changé. Revenez à la première page pour consulter les matchs disponibles."
                : includePast
                  ? "Les matchs apparaîtront ici après une collecte réussie des pages publiques."
                  : "Aucun match à venir n’a été collecté. Vous pouvez aussi consulter les observations des matchs déjà commencés."
            }
            action={
              offset === 0 && !includePast ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    setIncludePast(true);
                  }}
                >
                  Inclure les matchs déjà commencés
                </Button>
              ) : undefined
            }
          />
        ) : events.data ? (
          <section className="grid gap-5" aria-label="Marchés Stake">
            <p className="text-sm text-ink-secondary" role="status">
              {events.data.page.total} match{events.data.page.total === 1 ? "" : "s"}{" "}
              {includePast ? "enregistré" : "à venir"}
              {includePast && events.data.page.total !== 1 ? "s" : ""}
            </p>
            {events.data.data.map((value) => (
              <StakeEventCard key={value.capture.event.providerEventId} value={value} />
            ))}
          </section>
        ) : null}
        {events.data &&
        events.data.data.length > 0 &&
        canReadPrevious(events) &&
        (offset > 0 || events.data.page.total > 5) ? (
          <nav
            className="mt-5 flex flex-wrap items-center gap-3"
            aria-label="Pagination des matchs Stake"
          >
            <Button
              variant="outline"
              disabled={offset === 0 || events.isFetching}
              onClick={() => {
                setOffset(Math.max(0, offset - 5));
              }}
            >
              Précédents
            </Button>
            <span className="text-sm" role="status">
              Page {Math.floor(offset / 5) + 1} sur{" "}
              {Math.max(1, Math.ceil(events.data.page.total / 5))}
            </span>
            <Button
              variant="outline"
              disabled={offset + 5 >= events.data.page.total || events.isFetching}
              onClick={() => {
                setOffset(offset + 5);
              }}
            >
              Suivants
            </Button>
          </nav>
        ) : null}
      </RemoteDataBoundary>
    </div>
  );
}
