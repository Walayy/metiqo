import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { useClockText } from '@/hooks/use-clock-text';
import { Countdown } from './time-label';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { useId, useDeferredValue, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Accordion } from 'radix-ui';
import {
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CirclePercent,
  Minus,
  Search,
  Swords,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import type { Catalog } from '@/domain/schemas';
import type { EsportMatch } from '@/domain/matches';
import { matchWinnerId, seriesScore } from '@/domain/matches';
import { normalize, time } from '@/lib/format';
import { catalogQuery, matchesQuery } from '@/lib/api';
import { HttpError } from '@/lib/http-error';
import { Button } from '@/components/ui/button';
import { StatusDot } from '@/components/ui/status-dot';
import { Logo } from '@/components/ui/logo';
import { StatusPanel } from '@/features/status/status-panel';
import { LeagueFilters, RefreshValues } from '@/features/values/league-filters';
import { boundedDay, dayKey, dayLabel, shiftDay } from './calendar';
import { MatchDetail } from './match-detail';
import { compareMatches, matchesStatus, matchStatuses, statusCounts } from './presentation';
import type { MatchFilter } from './presentation';
import { UpdatedValue } from './updated-value';
import { MatchScore } from './match-score';
import { matchesPollInterval } from './polling';
import './matches.css';
export function LiveBadge({ count }: { count?: number }) {
  return (
    <span className="live-badge">
      <StatusDot tone="live" />
      <UpdatedValue value={count != null ? `${count} en direct` : 'En direct'} />
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
  const statusSelectionId = useId();
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
  const today = useClockText((now) => dayKey(new Date(now)));
  const retrySeconds = useClockText((now) =>
    query.error instanceof HttpError && query.error.retryAt > now
      ? String(Math.ceil((query.error.retryAt - now) / 1000))
      : '',
  );
  const [league, setLeague] = useState('all');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<MatchFilter>('all');
  const [openedDays, setOpenedDays] = useState<Record<string, string[]>>({});
  const [resultsHeight, setResultsHeight] = useState(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<EsportMatch | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const deferredSearch = useDeferredValue(search);
  const selectedDay = boundedDay(day, today);
  const loading = useMinimumLoading(dataPending || refreshing, selectedDay);
  const opened = openedDays[selectedDay] ?? [];
  useLayoutEffect(() => {
    const element = resultsRef.current;
    if (!element || loading) return;
    const observer = new ResizeObserver(() =>
      setResultsHeight(element.getBoundingClientRect().height),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [loading]);
  const selectedButton = useRef<HTMLButtonElement>(null);
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
  const accessError =
    visibleError instanceof HttpError && [401, 403, 423].includes(visibleError.status);
  const refreshError =
    visibleError && query.data && !invalid && !accessError
      ? matchesPollInterval(false, visibleError) === false
        ? 'Actualisation interrompue. Les dernières données restent affichées ; réessayez depuis la liste.'
        : retrySeconds
          ? `Actualisation en attente (${retrySeconds} s). Les dernières données restent affichées.`
          : 'Actualisation momentanément indisponible. Les dernières données restent affichées ; reprise automatique.'
      : null;
  if ((visibleError && !refreshError) || invalid)
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
  const dayMatches = items.filter((item) => dayKey(item.startsAt) === selectedDay);
  const leagueCounts = Object.fromEntries(
    catalog.leagues.map((l) => [l.id, dayMatches.filter((m) => m.leagueId === l.id).length]),
  );
  const filtered = dayMatches.filter((item) => {
    if (league !== 'all' && item.leagueId !== league) return false;
    const teams = catalog.teams.filter((t) => [item.homeId, item.awayId].includes(t.id));
    const competition = catalog.leagues.find((l) => l.id === item.leagueId);
    return normalize(
      `${teams.map((t) => `${t.name} ${t.code}`).join(' ')} ${competition?.name}`,
    ).includes(normalize(deferredSearch));
  });
  const counts = statusCounts(filtered);
  const matches = filtered.filter((m) => matchesStatus(m, status)).sort(compareMatches);
  const groups = catalog.leagues
    .map((competition) => ({
      competition,
      matches: matches.filter((m) => m.leagueId === competition.id),
    }))
    .filter((group) => group.matches.length)
    .sort(
      (a, b) =>
        compareMatches(a.matches[0]!, b.matches[0]!) ||
        a.competition.name.localeCompare(b.competition.name, 'fr'),
    );
  return (
    <div className="matches-page">
      {refreshError && (
        <p className="match-refresh-notice" role="status">
          {refreshError}
        </p>
      )}
      <div className="page-heading matches-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            LEAGUE OF LEGENDS
          </div>
          <h1>Matchs</h1>
        </div>
        <RefreshValues
          mobile
          onRefresh={() => void refresh()}
          refreshing={refreshing || query.isFetching}
        />
      </div>
      <section className="match-calendar" aria-label="Choisir une journée">
        <div className="calendar-controls">
          <div className="calendar-heading">
            <h2>{dayLabel(selectedDay)}</h2>
            <p>Heure de Paris</p>
          </div>
          <div className="calendar-actions">
            <Button
              iconOnly
              aria-label="Jour précédent avec des matchs"
              disabled={!previous || dataPending}
              onClick={() => previous && onDay(previous)}
            >
              <ChevronLeft size={18} />
            </Button>
            <Button
              className="calendar-today"
              aria-label="Aujourd’hui"
              title="Aujourd’hui"
              disabled={selectedDay === today || !populated.has(today) || dataPending}
              onClick={() => onDay(today)}
            >
              <CalendarDays size={18} aria-hidden="true" />
              <span>Aujourd’hui</span>
            </Button>
            <Button
              iconOnly
              aria-label="Jour suivant avec des matchs"
              disabled={!next || dataPending}
              onClick={() => next && onDay(next)}
            >
              <ChevronRight size={18} />
            </Button>
          </div>
        </div>
        <div className="calendar-days" role="group" aria-label="Journées disponibles">
          {days.map((date) => (
            <button
              key={date}
              ref={date === selectedDay ? selectedButton : undefined}
              type="button"
              className={clsx(
                'calendar-day',
                date === selectedDay && 'is-selected',
                date === today && 'is-today',
              )}
              aria-pressed={date === selectedDay}
              aria-current={date === today ? 'date' : undefined}
              aria-label={`${dayLabel(date)}${date === today ? ', aujourd’hui' : ''}${!populated.has(date) && !dataPending ? ', aucun match' : ''}`}
              disabled={dataPending || date === selectedDay || !populated.has(date)}
              onClick={() => onDay(date)}
            >
              {date === selectedDay && <SelectionIndicator id={selectionId} />}
              <span>{dayLabel(date, true).split(' ')[0]}</span>
              <strong>{Number(date.slice(-2))}</strong>
              <small>
                {date === today
                  ? 'Auj.'
                  : date.endsWith('-01')
                    ? dayLabel(date, true).split(' ').slice(2).join(' ')
                    : ''}
              </small>
            </button>
          ))}
        </div>
      </section>
      <LeagueFilters
        leagues={catalog.leagues}
        selectedLeague={league}
        onSelect={setLeague}
        loading={dataPending}
        error={null}
        onRefresh={() => void refresh()}
        refreshing={refreshing || query.isFetching}
        context="matches"
        matchCounts={leagueCounts}
      />
      <div className="matches-tools">
        <div
          className="match-status-filters"
          role="group"
          aria-label="Filtrer les matchs par statut"
        >
          {matchStatuses
            .filter(
              (option) => option.id !== 'changed' || counts.changed > 0 || status === 'changed',
            )
            .map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={status === option.id}
                className={clsx('match-status-filter', option.id === 'live' && 'is-live')}
                onClick={() => {
                  setStatus(option.id);
                  if (option.id === 'live')
                    setOpenedDays((current) => ({
                      ...current,
                      [selectedDay]: [
                        ...new Set(
                          filtered.filter((m) => m.status === 'live').map((m) => m.leagueId),
                        ),
                      ],
                    }));
                }}
              >
                {status === option.id && <SelectionIndicator id={statusSelectionId} />}
                <span className="match-status-label">{option.label}</span>
                <span className="match-status-count">{counts[option.id]}</span>
              </button>
            ))}
        </div>
        <div className="match-search">
          <label className="search-field">
            <Search size={17} aria-hidden="true" />
            <input
              aria-label="Rechercher un match"
              aria-describedby="match-search-scope"
              placeholder="Équipe ou ligue du jour"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          {search && (
            <button
              type="button"
              aria-label="Effacer la recherche de match"
              onClick={() => setSearch('')}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>
      <div className="match-results-caption">
        <p role="status">
          {loading
            ? 'Chargement des rencontres…'
            : `${matches.length} match${matches.length > 1 ? 's' : ''} · ${groups.length} ligue${groups.length > 1 ? 's' : ''}`}
        </p>
        <span id="match-search-scope">Recherche dans cette journée</span>
      </div>
      <div
        className="match-results"
        ref={resultsRef}
        aria-busy={loading}
        style={loading && resultsHeight ? { minHeight: resultsHeight } : undefined}
      >
        {loading ? (
          <div className="league-skeletons" role="status" aria-label="Chargement des rencontres">
            {(groups.length
              ? groups.map((g) => ({
                  id: g.competition.id,
                  rows: opened.includes(g.competition.id) ? g.matches : [],
                }))
              : [
                  { id: 'loading', rows: [] },
                  { id: 'loading-2', rows: [] },
                ]
            ).map((group) => (
              <div key={group.id} className="league-accordion" aria-hidden="true">
                <div className="league-trigger">
                  <span className="skeleton league-loading-logo" />
                  <span className="league-title">
                    <span className="skeleton league-loading-name" />
                    <span className="skeleton league-loading-count" />
                  </span>
                  <span className="league-timing skeleton league-loading-time" />
                </div>
                {group.rows.length > 0 && (
                  <div className="league-matches">
                    {group.rows.map((match) => (
                      <div className="fixture-item" key={match.id}>
                        <div className="fixture-skeleton">
                          <span className="skeleton" />
                          <span className="skeleton" />
                          <span className="skeleton" />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : !matches.length ? (
          <div className="empty-state matches-empty">
            <span className="empty-icon">
              <Swords size={26} />
            </span>
            <h3>Aucun match dans cette sélection.</h3>
            <p>
              {search
                ? `Aucun résultat pour « ${search} » dans cette journée.`
                : status !== 'all'
                  ? 'Aucune rencontre avec ce statut pour les filtres choisis.'
                  : league !== 'all'
                    ? 'Cette ligue n’a pas de rencontre publiée pour cette journée.'
                    : 'Aucune rencontre publiée pour cette journée.'}
            </p>
            <div className="empty-actions">
              {search && <Button onClick={() => setSearch('')}>Effacer la recherche</Button>}
              {status !== 'all' && (
                <Button onClick={() => setStatus('all')}>Tous les statuts</Button>
              )}
              {league !== 'all' && (
                <Button onClick={() => setLeague('all')}>Toutes les ligues</Button>
              )}
              {!search && status === 'all' && league === 'all' && next && (
                <Button onClick={() => onDay(next)}>Prochaine journée avec des matchs</Button>
              )}
            </div>
          </div>
        ) : (
          <Accordion.Root
            type="multiple"
            className="league-accordions"
            value={opened}
            onValueChange={(value) =>
              setOpenedDays((current) => ({ ...current, [selectedDay]: value }))
            }
          >
            {groups.map(({ competition, matches: rows }) => {
              const summary = statusCounts(rows);
              const upcoming = rows.find((m) => m.status === 'scheduled');
              return (
                <Accordion.Item
                  key={competition.id}
                  value={competition.id}
                  className="league-accordion"
                >
                  <Accordion.Header>
                    <Accordion.Trigger className="league-trigger">
                      <Logo src={competition.image} name={competition.name} league />
                      <span className="league-title">
                        <strong>{competition.name}</strong>
                        <small>
                          {[
                            summary.live && `${rows.length} match${rows.length > 1 ? 's' : ''}`,
                            summary.scheduled && `${summary.scheduled} à venir`,
                            summary.finished &&
                              `${summary.finished} terminé${summary.finished > 1 ? 's' : ''}`,
                            summary.changed &&
                              `${summary.changed} reporté${summary.changed > 1 ? 's' : ''} / annulé${summary.changed > 1 ? 's' : ''}`,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </small>
                      </span>
                      <span className="league-timing">
                        {summary.live ? (
                          <LiveBadge count={summary.live} />
                        ) : upcoming ? (
                          <span className="match-countdown">
                            <Countdown startsAt={upcoming.startsAt} />
                          </span>
                        ) : null}
                      </span>
                      <ChevronDown size={18} className="accordion-chevron" />
                    </Accordion.Trigger>
                  </Accordion.Header>
                  <Accordion.Content className="league-content">
                    <div className="league-matches">
                      {rows.map((match) => (
                        <Fixture
                          key={match.id}
                          match={match}
                          catalog={catalog}
                          onSelect={() => {
                            setSelected(match);
                            setDetailOpen(true);
                          }}
                        />
                      ))}
                    </div>
                  </Accordion.Content>
                </Accordion.Item>
              );
            })}
          </Accordion.Root>
        )}
      </div>
      {selected && (
        <MatchDetail
          match={items.find((m) => m.id === selected.id) ?? selected}
          catalog={catalog}
          open={detailOpen}
          refreshError={refreshError}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </div>
  );
}
function Fixture({
  match,
  catalog,
  onSelect,
}: {
  match: EsportMatch;
  catalog: Catalog;
  onSelect: () => void;
}) {
  const home = catalog.teams.find((t) => t.id === match.homeId)!;
  const away = catalog.teams.find((t) => t.id === match.awayId)!;
  const winnerId = matchWinnerId(match);
  const hasScore =
    Boolean(match.seriesScore || match.currentScore) || match.maps.some((m) => m.winnerId);
  const liveMap = match.maps.find((m) => m.status === 'live');
  const score =
    match.status === 'scheduled'
      ? 'vs'
      : hasScore
        ? `${seriesScore(match, home.id)} : ${seriesScore(match, away.id)}`
        : '—';
  return (
    <div className="fixture-item">
      <button
        type="button"
        className={clsx('fixture-row', match.status === 'live' && 'fixture-live')}
        onClick={onSelect}
        aria-label={`${home.name} contre ${away.name}, ${match.status === 'live' ? 'en direct' : time(match.startsAt)}, ${score}${winnerId ? `, victoire ${winnerId === home.id ? home.name : away.name}` : ''}${match.oddsMarkets?.length ? ', cotes consultables dans le détail' : ''}, voir le match`}
      >
        <span className="fixture-time">
          <time dateTime={match.startsAt}>
            <UpdatedValue value={time(match.startsAt)} />
          </time>
          <small>
            <UpdatedValue value={match.format ?? 'Format inconnu'} />
          </small>
        </span>
        <span className={clsx('fixture-team home', winnerId === home.id && 'is-winner')}>
          <span className="fixture-team-copy">
            <UpdatedValue value={home.name} />
          </span>
          <FixtureTeamMark team={home} winnerId={winnerId} />
        </span>
        <span className={clsx('fixture-score', match.status === 'scheduled' && 'fixture-vs')}>
          <MatchScore match={match} fallback={match.status === 'scheduled' ? 'vs' : '—'} />
        </span>
        <span className={clsx('fixture-team away', winnerId === away.id && 'is-winner')}>
          <FixtureTeamMark team={away} winnerId={winnerId} />
          <span className="fixture-team-copy">
            <UpdatedValue value={away.name} />
          </span>
        </span>
        <span className="fixture-status">
          <UpdatedValue value={`${match.status}:${liveMap?.number ?? ''}`}>
            {match.status === 'live' ? (
              <span
                className="fixture-live-stack"
                role="img"
                aria-label={`En direct${liveMap ? `, carte ${liveMap.number}` : ''}`}
              >
                <StatusDot tone="live" />
                {liveMap && <span>Carte {liveMap.number}</span>}
              </span>
            ) : match.status === 'finished' ? (
              <span>Terminé</span>
            ) : match.status === 'cancelled' ? (
              <span>Annulé</span>
            ) : match.status === 'postponed' ? (
              <span>Reporté / interrompu</span>
            ) : (
              <span>
                <Countdown startsAt={match.startsAt} />
              </span>
            )}
          </UpdatedValue>
          {!!match.oddsMarkets?.length && (
            <span
              className="fixture-odds-indicator"
              role="img"
              aria-label="Cotes Stake consultables dans le détail"
              title="Cotes Stake consultables dans le détail"
            >
              <CirclePercent size={15} aria-hidden="true" />
            </span>
          )}
        </span>
        <ChevronRight size={17} className="fixture-arrow" aria-hidden="true" />
      </button>
    </div>
  );
}
function FixtureTeamMark({
  team,
  winnerId,
}: {
  team: Catalog['teams'][number];
  winnerId: string | null;
}) {
  const won = winnerId === team.id;
  return (
    <span className="fixture-team-mark">
      <Logo src={team.image} name={team.name} />
      {winnerId && (
        <span
          className={clsx('fixture-outcome', won && 'is-winner')}
          role="img"
          aria-label={won ? 'Victoire' : 'Défaite'}
          title={won ? 'Victoire' : 'Défaite'}
        >
          <UpdatedValue value={won ? 'win' : 'loss'}>
            {won ? <Check size={10} strokeWidth={2.5} /> : <Minus size={10} />}
          </UpdatedValue>
        </span>
      )}
    </span>
  );
}
