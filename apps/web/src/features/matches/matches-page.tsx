import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { ContentTransition } from '@/components/ui/content-transition';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { useId, useDeferredValue, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Accordion } from 'radix-ui';
import { ChevronDown, ChevronLeft, ChevronRight, Search, Swords, ArrowUpRight } from 'lucide-react';
import { clsx } from 'clsx';
import type { Catalog } from '@/domain/schemas';
import type { EsportMatch } from '@/domain/matches';
import { countdown, matchWinnerId, seriesScore } from '@/domain/matches';
import { normalize, time } from '@/lib/format';
import { catalogQuery, matchesQuery } from '@/lib/api';
import { HttpError } from '@/lib/http-error';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/ui/logo';
import { StatusPanel } from '@/features/status/status-panel';
import { LeagueFilters, RefreshValues } from '@/features/values/league-filters';
import { boundedDay, dayKey, dayLabel, shiftDay } from './calendar';
import { MatchDetail } from './match-detail';
import './matches.css';

export function LiveBadge() {
  return (
    <span className="live-badge">
      <span aria-hidden="true" />
      En direct
    </span>
  );
}
export function MatchesPage({
  catalog,
  day,
  onDay,
  loading: catalogLoading,
}: {
  catalog: Catalog;
  day: string;
  onDay: (day: string) => void;
  loading: boolean;
}) {
  const query = useQuery(matchesQuery);
  const queryClient = useQueryClient();
  const [catalogCheckedAt, setCatalogCheckedAt] = useState(0);
  const missingIdentities = Boolean(
    query.data?.items.some(
      (item) =>
        !catalog.leagues.some((l) => l.id === item.leagueId) ||
        [item.homeId, item.awayId].some((id) => !catalog.teams.some((t) => t.id === id)),
    ),
  );
  const reconcilingCatalog = missingIdentities && catalogCheckedAt !== query.dataUpdatedAt;
  useEffect(() => {
    if (!reconcilingCatalog || catalogLoading) return;
    let active = true;
    const observedAt = query.dataUpdatedAt;
    void queryClient
      .fetchQuery({ ...catalogQuery, staleTime: 0 })
      .catch(() => undefined)
      .finally(() => {
        if (active) setCatalogCheckedAt(observedAt);
      });
    return () => {
      active = false;
    };
  }, [reconcilingCatalog, catalogLoading, query.dataUpdatedAt, queryClient]);
  const items = query.data?.items ?? [];
  const [stickyError, setStickyError] = useState<Error | null>(null);
  const selectionId = useId();
  const [refreshing, setRefreshing] = useState(false);
  async function refresh() {
    setRefreshing(true);
    try {
      await query.refetch();
    } finally {
      setRefreshing(false);
    }
  }
  const dataPending = query.isPending || catalogLoading || reconcilingCatalog;
  const [now, setNow] = useState(() => Date.now());
  const today = dayKey(new Date(now));
  const [league, setLeague] = useState('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<EsportMatch | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const deferredSearch = useDeferredValue(search);
  const selectedDay = boundedDay(day, today);
  const loading = useMinimumLoading(
    dataPending || refreshing,
    JSON.stringify([selectedDay, league, deferredSearch]),
  );
  const selectedButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (day && day !== selectedDay) onDay(selectedDay);
  }, [day, selectedDay, onDay]);
  useLayoutEffect(() => {
    const button = selectedButton.current;
    const rail = button?.parentElement;
    if (!button || !rail) return;
    const reveal = () => {
      rail.scrollTo({
        left: button.offsetLeft - (rail.clientWidth - button.clientWidth) / 2,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
      });
    };
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(rail);
    return () => observer.disconnect();
  }, [selectedDay, dataPending]);
  const invalid =
    !loading &&
    items.some(
      (item) =>
        !catalog.leagues.some((l) => l.id === item.leagueId) ||
        [item.homeId, item.awayId].some((id) => !catalog.teams.some((t) => t.id === id)),
    );
  const invalidError = invalid ? new HttpError(0, { kind: 'invalid-response' }) : null;
  function retry() {
    const currentError = query.error ?? invalidError;
    if (currentError) setStickyError(currentError);
    void query.refetch().then((result) => {
      setStickyError(result.error ?? null);
    });
  }
  const visibleError = query.error ?? invalidError ?? (query.isFetching ? stickyError : null);
  if (visibleError || invalid)
    return (
      <StatusPanel
        error={visibleError ?? new HttpError(0, { kind: 'invalid-response' })}
        onRetry={retry}
        busy={query.isFetching}
      />
    );
  const days = Array.from({ length: 15 }, (_, i) => shiftDay(today, i - 7));
  const populated = new Set(items.map((item) => dayKey(item.startsAt)));
  const previous = days.filter((date) => date < selectedDay && populated.has(date)).at(-1);
  const next = days.find((date) => date > selectedDay && populated.has(date));
  const matches = items
    .filter((item) => {
      if (dayKey(item.startsAt) !== selectedDay || (league !== 'all' && item.leagueId !== league))
        return false;
      const teams = catalog.teams.filter((t) => [item.homeId, item.awayId].includes(t.id));
      const competition = catalog.leagues.find((l) => l.id === item.leagueId);
      return normalize(
        `${teams.map((t) => `${t.name} ${t.code}`).join(' ')} ${competition?.name}`,
      ).includes(normalize(deferredSearch));
    })
    .sort((a, b) => Date.parse(a.startsAt) - Date.parse(b.startsAt) || a.id.localeCompare(b.id));
  const groups = catalog.leagues
    .map((competition) => ({
      competition,
      matches: matches.filter((m) => m.leagueId === competition.id),
    }))
    .filter((group) => group.matches.length)
    .sort((a, b) => {
      const liveOrder =
        Number(b.matches.some((m) => m.status === 'live')) -
        Number(a.matches.some((m) => m.status === 'live'));
      return (
        liveOrder ||
        Date.parse(
          a.matches.find((m) => m.status === 'scheduled')?.startsAt ?? a.matches[0]!.startsAt,
        ) -
          Date.parse(
            b.matches.find((m) => m.status === 'scheduled')?.startsAt ?? b.matches[0]!.startsAt,
          )
      );
    });
  return (
    <div className="matches-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            LEAGUE OF LEGENDS
          </div>
          <h1>Chaque jour, ses matchs.</h1>
          <p>Le programme, les scores et toute l’action, carte par carte.</p>
        </div>
        <RefreshValues
          mobile
          onRefresh={() => void refresh()}
          refreshing={refreshing || query.isFetching}
        />
      </div>
      <section className="match-calendar" aria-label="Choisir une journée">
        <div className="calendar-controls">
          <Button
            iconOnly
            aria-label="Jour précédent avec des matchs"
            disabled={!previous || dataPending}
            onClick={() => previous && onDay(previous)}
          >
            <ChevronLeft size={19} />
          </Button>
          <ContentTransition id={selectedDay} className="calendar-selected">
            {dayLabel(selectedDay, true)}
          </ContentTransition>
          <Button
            iconOnly
            aria-label="Jour suivant avec des matchs"
            disabled={!next || dataPending}
            onClick={() => next && onDay(next)}
          >
            <ChevronRight size={19} />
          </Button>
          <Button
            className="calendar-today"
            disabled={selectedDay === today || !populated.has(today) || dataPending}
            onClick={() => onDay(today)}
          >
            Aujourd’hui
          </Button>
        </div>
        <div className="calendar-days" role="group" aria-label="Journées disponibles">
          {days.map((date) => (
            <button
              key={date}
              ref={date === selectedDay ? selectedButton : undefined}
              type="button"
              className={clsx('calendar-day', date === selectedDay && 'is-selected')}
              aria-pressed={date === selectedDay}
              aria-label={`${dayLabel(date)}${!populated.has(date) && !dataPending ? ', aucun match' : ''}`}
              disabled={dataPending || date === selectedDay || !populated.has(date)}
              onClick={() => onDay(date)}
            >
              {date === selectedDay && <SelectionIndicator id={selectionId} />}
              <span>{date === today ? 'Aujourd’hui' : dayLabel(date, true).split(' ')[0]}</span>
              <strong>{Number(date.slice(-2))}</strong>
              <small>{dayLabel(date, true).split(' ').slice(2).join(' ')}</small>
            </button>
          ))}
        </div>
        <p className="calendar-caption">7 jours avant et après aujourd’hui · Heure de Paris</p>
      </section>
      <LeagueFilters
        leagues={catalog.leagues}
        selectedLeague={league}
        onSelect={setLeague}
        loading={dataPending}
        error={null}
        onRefresh={() => void refresh()}
        refreshing={refreshing || query.isFetching}
      />
      <div className="matches-tools">
        <div>
          <h2>{dayLabel(selectedDay)}</h2>
          <p role="status">
            {loading
              ? 'Chargement des rencontres…'
              : `${matches.length} match${matches.length > 1 ? 's' : ''} · ${groups.length} ligue${groups.length > 1 ? 's' : ''}`}
          </p>
        </div>
        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="Rechercher un match"
            placeholder="Une équipe, une ligue…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div aria-busy={loading}>
        <ContentTransition id={loading ? 'loading' : 'ready'}>
          {loading ? (
            <div className="league-skeletons" role="status" aria-label="Chargement des rencontres">
              {Array.from({ length: groups.length || 3 }, (_, i) => (
                <div key={i} className="league-accordion" aria-hidden="true">
                  <div className="league-trigger">
                    <span className="skeleton league-loading-logo" />
                    <span className="league-title">
                      <span className="skeleton league-loading-name" />
                      <span className="skeleton league-loading-count" />
                    </span>
                    <span className="league-timing skeleton league-loading-time" />
                    <span className="skeleton league-loading-chevron" />
                  </div>
                </div>
              ))}
            </div>
          ) : !matches.length ? (
            <div className="empty-state">
              <span className="empty-icon">
                <Swords size={28} />
              </span>
              <h3>Aucun match dans cette sélection.</h3>
              <p>Choisissez une autre journée ou élargissez vos filtres.</p>
              {(search || league !== 'all') && (
                <Button
                  onClick={() => {
                    setSearch('');
                    setLeague('all');
                  }}
                >
                  Effacer la sélection
                </Button>
              )}
            </div>
          ) : (
            <Accordion.Root key={selectedDay} type="multiple" className="league-accordions">
              {groups.map(({ competition, matches: rows }) => {
                const live = rows.filter((m) => m.status === 'live');
                const upcoming = rows.find((m) => m.status === 'scheduled');
                return (
                  <Accordion.Item
                    key={competition.id}
                    value={competition.id}
                    className="league-accordion"
                  >
                    <Accordion.Header>
                      <Accordion.Trigger className="league-trigger">
                        <Logo
                          src={competition.image}
                          name={competition.name}
                          code={competition.name}
                          league
                        />
                        <span className="league-title">
                          <strong>{competition.name}</strong>
                          <small>
                            {rows.length} match{rows.length > 1 ? 's' : ''}
                          </small>
                        </span>
                        <span className="league-timing">
                          {live.length ? (
                            <LiveBadge />
                          ) : upcoming ? (
                            <span
                              className={clsx(
                                'match-countdown',
                                Date.parse(upcoming.startsAt) - now < 3600000 && 'is-soon',
                              )}
                            >
                              {countdown(upcoming.startsAt, now)}
                            </span>
                          ) : (
                            <span className="match-finished">
                              {rows.every((m) => m.status === 'finished')
                                ? 'Terminés'
                                : 'Programme modifié'}
                            </span>
                          )}
                        </span>
                        <ChevronDown size={18} className="accordion-chevron" />
                      </Accordion.Trigger>
                    </Accordion.Header>
                    <Accordion.Content className="league-content">
                      <div className="league-matches">
                        {rows.map((match) => {
                          const home = catalog.teams.find((t) => t.id === match.homeId)!;
                          const away = catalog.teams.find((t) => t.id === match.awayId)!;
                          const hasMapScore =
                            Boolean(match.seriesScore) || match.maps.some((map) => map.winnerId);
                          const winnerId = matchWinnerId(match);
                          const homeIsWinner = winnerId === home.id;
                          const awayIsWinner = winnerId === away.id;
                          return (
                            <button
                              key={match.id}
                              type="button"
                              className="fixture-row"
                              onClick={() => {
                                setSelected(match);
                                setDetailOpen(true);
                              }}
                              aria-label={`${home.name} contre ${away.name}, ${match.status === 'live' ? 'en direct' : time(match.startsAt)}, voir le match`}
                            >
                              <span className="fixture-time">
                                <time dateTime={match.startsAt}>{time(match.startsAt)}</time>
                                <small>{match.format}</small>
                              </span>
                              <span
                                className={clsx(
                                  'fixture-team home',
                                  homeIsWinner && 'is-winner',
                                  winnerId && !homeIsWinner && 'is-loser',
                                )}
                              >
                                <span className="fixture-team-copy">
                                  <span>{home.name}</span>
                                  {winnerId && (
                                    <small>{homeIsWinner ? 'Gagnant' : 'Perdant'}</small>
                                  )}
                                </span>
                                <Logo src={home.image} name={home.name} code={home.code} />
                              </span>
                              <span className="fixture-score">
                                {match.status === 'scheduled' ? (
                                  <span className="fixture-vs">vs</span>
                                ) : hasMapScore ? (
                                  <>
                                    {seriesScore(match, home.id)}
                                    <span>:</span>
                                    {seriesScore(match, away.id)}
                                  </>
                                ) : match.currentScore ? (
                                  <>
                                    {match.currentScore.home}
                                    <span>:</span>
                                    {match.currentScore.away}
                                  </>
                                ) : (
                                  <span>—</span>
                                )}
                              </span>
                              <span
                                className={clsx(
                                  'fixture-team away',
                                  awayIsWinner && 'is-winner',
                                  winnerId && !awayIsWinner && 'is-loser',
                                )}
                              >
                                <Logo src={away.image} name={away.name} code={away.code} />
                                <span className="fixture-team-copy">
                                  <span>{away.name}</span>
                                  {winnerId && (
                                    <small>{awayIsWinner ? 'Gagnant' : 'Perdant'}</small>
                                  )}
                                </span>
                              </span>
                              <span className="fixture-status">
                                {match.status === 'live' ? (
                                  <LiveBadge />
                                ) : match.status === 'finished' ? (
                                  <span>Terminé</span>
                                ) : match.status === 'cancelled' || match.status === 'postponed' ? (
                                  <span>
                                    {match.status === 'cancelled'
                                      ? 'Annulé'
                                      : 'Reporté / interrompu'}
                                  </span>
                                ) : (
                                  <span>{countdown(match.startsAt, now)}</span>
                                )}
                              </span>
                              <ArrowUpRight size={17} className="fixture-arrow" />
                            </button>
                          );
                        })}
                      </div>
                    </Accordion.Content>
                  </Accordion.Item>
                );
              })}
            </Accordion.Root>
          )}
        </ContentTransition>
      </div>
      {selected && (
        <MatchDetail
          match={items.find((m) => m.id === selected.id) ?? selected}
          catalog={catalog}
          open={detailOpen}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </div>
  );
}
