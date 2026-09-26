import { Fragment, useEffect, useId, useRef, useState } from 'react';
import { Collapsible } from 'radix-ui';
import { AlertCircle, AlertTriangle, ChevronDown, Filter, Info, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
import { StatusDot } from '@/components/ui/status-dot';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { decimal, scheduledDate, scheduledShortDate } from '@/lib/format';
import { workerLogsRequest } from './api';
import type { ScriptRun, WorkerLogEntry, WorkerLogs, WorkerService } from './contracts';
import './worker-log-reader.css';

type Level = 'all' | 'warning' | 'error';
const statusNames: Record<ScriptRun['status'], string> = {
  queued: 'En attente',
  running: 'En cours',
  succeeded: 'Terminée',
  failed: 'Échec',
  interrupted: 'Interrompue',
};
const levelNames = { info: 'Information', warning: 'Avertissement', error: 'Erreur' };
const contextNames: Record<string, string> = {
  snapshots: 'Rencontres',
  quotes: 'Relevés',
  markets: 'Marchés',
  eventsFailed: 'Rencontres écartées',
  kind: 'Type',
  status: 'État',
  retryAt: 'Reprise',
  frames: 'Trace technique',
  step: 'Étape',
  pages: 'Pages',
  leagues: 'Ligues',
  teams: 'Équipes',
  imported: 'Fichiers importés',
  unchanged: 'Fichiers inchangés',
  published: 'Rencontres publiées',
  created: 'Rencontres créées',
  knownEvents: 'Rencontres connues',
  pendingDetails: 'Détails en attente',
  errors: 'Erreurs',
  unavailableFeeds: 'Flux indisponibles',
  cacheAgeSeconds: 'Âge du cache (secondes)',
  sourceState: 'État source',
  resource: 'Document source',
  examined: 'Sélections examinées',
  changed: 'Résultats modifiés',
  pending: 'En attente',
  won: 'Gagnées',
  lost: 'Perdues',
  void: 'Annulées',
};
const timeFormat = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});
const dayFormat = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function sameEntries(old: WorkerLogEntry[], fresh: WorkerLogEntry[]) {
  const seen = new Set(old.map((entry) => entry.id));
  return fresh.filter((entry) => !seen.has(entry.id));
}

function FilterControls({
  level,
  setLevel,
  search,
  setSearch,
}: {
  level: Level;
  setLevel: (level: Level) => void;
  search: string;
  setSearch: (search: string) => void;
}) {
  const indicatorId = useId();
  return (
    <div className="log-filters">
      <div className="log-filter-levels" role="group" aria-label="Gravité">
        {(
          [
            ['all', 'Tout'],
            ['warning', 'Alertes'],
            ['error', 'Erreurs'],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={level === value ? 'is-selected' : ''}
            aria-pressed={level === value}
            onClick={() => setLevel(value)}
          >
            {level === value && <SelectionIndicator id={indicatorId} />}
            <span>{label}</span>
          </button>
        ))}
      </div>
      <label className="log-search">
        <Search size={17} aria-hidden="true" />
        <span className="sr-only">Rechercher dans les journaux</span>
        <input
          value={search}
          maxLength={80}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Rechercher…"
        />
      </label>
    </div>
  );
}

function LogLine({
  entry,
  scriptName,
  onSelectRun,
  onInspect,
}: {
  entry: WorkerLogEntry;
  scriptName?: string;
  onSelectRun?: (runId: string) => void;
  onInspect: () => void;
}) {
  const detail = Object.entries(entry.context);
  const LevelIcon =
    entry.level === 'error' ? AlertCircle : entry.level === 'warning' ? AlertTriangle : Info;
  return (
    <li className={`log-line log-line--${entry.level}`}>
      <Collapsible.Root
        onOpenChange={(expanded) => {
          if (expanded) onInspect();
        }}
      >
        <Collapsible.Trigger className="log-line-trigger">
          <time dateTime={entry.recordedAt} title={scheduledDate(entry.recordedAt)}>
            {timeFormat.format(new Date(entry.recordedAt))}
          </time>
          <span className="log-level" title={levelNames[entry.level]}>
            <LevelIcon size={15} aria-hidden="true" />
            <span className="sr-only">{levelNames[entry.level]} : </span>
          </span>
          <span className="log-message">{entry.message}</span>
          <ChevronDown size={14} className="script-chevron" aria-hidden="true" />
        </Collapsible.Trigger>
        <Collapsible.Content className="ui-disclosure-content">
          <div className="log-line-detail">
            <dl className="log-context">
              <div>
                <dt>Date</dt>
                <dd>{scheduledDate(entry.recordedAt)}</dd>
              </div>
              {entry.scriptId && (
                <div>
                  <dt>Script</dt>
                  <dd>{scriptName ?? entry.scriptId}</dd>
                </div>
              )}
              <div>
                <dt>Niveau</dt>
                <dd>{levelNames[entry.level]}</dd>
              </div>
              <div>
                <dt>Étape</dt>
                <dd>{entry.stage}</dd>
              </div>
              {entry.eventId && (
                <div>
                  <dt>Rencontre</dt>
                  <dd>{entry.eventId}</dd>
                </div>
              )}
              {detail.map(([key, value]) => (
                <div key={key}>
                  <dt>{contextNames[key] ?? key}</dt>
                  <dd>
                    {Array.isArray(value) ? (
                      <code>{value.join(' → ')}</code>
                    ) : key === 'status' && typeof value === 'string' && value in statusNames ? (
                      statusNames[value as ScriptRun['status']]
                    ) : typeof value === 'object' ? (
                      JSON.stringify(value)
                    ) : (
                      String(value)
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            {entry.runId && onSelectRun && (
              <Button variant="ghost" onClick={() => onSelectRun(entry.runId!)}>
                Voir cette exécution
              </Button>
            )}
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </li>
  );
}

export function WorkerLogReader({
  worker,
  initialRunId,
  onClose,
  onRestoreFocus,
}: {
  worker: WorkerService;
  initialRunId?: string;
  onClose: () => void;
  onRestoreFocus: () => void;
}) {
  const [runId, setRunId] = useState<string | undefined>(initialRunId);
  const [level, setLevel] = useState<Level>('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [data, setData] = useState<WorkerLogs | null>(null);
  const [entries, setEntries] = useState<WorkerLogEntry[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState(false);
  const [follow, setFollow] = useState(true);
  const [newLines, setNewLines] = useState(0);
  const [critical, setCritical] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const showLoading = useMinimumLoading(
    loading,
    `${worker.id}-${runId}-${level}-${query}-${retryKey}`,
  );
  const listRef = useRef<HTMLDivElement>(null);
  const lastId = useRef(0);
  const requestId = useRef(0);
  const polling = useRef(false);
  const olderRequest = useRef<AbortController | null>(null);
  const followRef = useRef(true);
  const initializingScroll = useRef(true);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const current = ++requestId.current;
    const controller = new AbortController();
    olderRequest.current?.abort();
    lastId.current = 0;
    followRef.current = true;
    initializingScroll.current = true;
    queueMicrotask(() => {
      if (controller.signal.aborted || requestId.current !== current) return;
      setLoading(true);
      setError(null);
      setRefreshError(false);
      setLoadingOlder(false);
      setIssuesOpen(false);
      setEntries([]);
      setHasOlder(false);
      setNewLines(0);
      setFollow(true);
    });
    workerLogsRequest({ workerId: worker.id, runId, level, q: query }, controller.signal)
      .then((response) => {
        if (requestId.current !== current) return;
        setData(response);
        setEntries(response.items);
        setHasOlder(response.hasMore);
        lastId.current = response.items.at(-1)?.id ?? 0;
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted && requestId.current === current) {
          setError(cause instanceof Error ? cause.message : 'Journaux indisponibles.');
        }
      })
      .finally(() => {
        if (requestId.current === current) setLoading(false);
      });
    return () => {
      controller.abort();
      olderRequest.current?.abort();
    };
  }, [worker.id, runId, level, query, retryKey]);

  useEffect(() => {
    if (showLoading) return;
    // Wait for the skeleton to leave before positioning the real list.
    const frame = window.requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
      initializingScroll.current = false;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [showLoading]);

  const ready = data !== null && !loading && !error && open;
  useEffect(() => {
    if (!ready) return;
    const current = requestId.current;
    let disposed = false;
    const controllers = new Set<AbortController>();
    const poll = async () => {
      if (disposed || document.hidden || polling.current) return;
      polling.current = true;
      const controller = new AbortController();
      controllers.add(controller);
      try {
        const response = await workerLogsRequest(
          { workerId: worker.id, runId, level, q: query, after: lastId.current },
          controller.signal,
        );
        if (disposed || requestId.current !== current) return;
        setRefreshError(false);
        setData(response);
        if (response.items.length) {
          lastId.current = response.items.at(-1)!.id;
          setEntries((previous) => [...previous, ...sameEntries(previous, response.items)]);
          const nearEnd = listRef.current
            ? listRef.current.scrollHeight -
                listRef.current.scrollTop -
                listRef.current.clientHeight <
              88
            : true;
          if (followRef.current && nearEnd) {
            initializingScroll.current = true;
            window.requestAnimationFrame(() => {
              if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
              window.requestAnimationFrame(() => {
                initializingScroll.current = false;
              });
            });
          } else {
            followRef.current = false;
            setFollow(false);
            setNewLines((count) => count + response.items.length);
          }
          if (response.items.some((entry) => entry.level === 'error')) {
            setCritical('Un nouvel incident critique est disponible dans le journal.');
          }
        }
      } catch {
        // Keep the last lines and resume from the last received ID on reconnect.
        if (!disposed && requestId.current === current && !controller.signal.aborted)
          setRefreshError(true);
      } finally {
        controllers.delete(controller);
        polling.current = false;
      }
    };
    const timer = window.setInterval(() => void poll(), 4_000);
    const visible = () => void poll();
    document.addEventListener('visibilitychange', visible);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
      controllers.forEach((controller) => controller.abort());
    };
  }, [ready, worker.id, runId, level, query]);

  const loadOlder = async () => {
    const oldest = entries[0]?.id;
    if (!oldest || loadingOlder) return;
    const current = requestId.current;
    const controller = new AbortController();
    olderRequest.current = controller;
    setLoadingOlder(true);
    const height = listRef.current?.scrollHeight ?? 0;
    try {
      const response = await workerLogsRequest(
        { workerId: worker.id, runId, level, q: query, before: oldest },
        controller.signal,
      );
      if (requestId.current !== current) return;
      setEntries((previous) => [...sameEntries(previous, response.items), ...previous]);
      setHasOlder(response.hasMore);
      window.requestAnimationFrame(() => {
        if (listRef.current) listRef.current.scrollTop += listRef.current.scrollHeight - height;
      });
    } catch (cause) {
      if (!controller.signal.aborted && requestId.current === current)
        setError(cause instanceof Error ? cause.message : 'Chargement impossible.');
    } finally {
      if (requestId.current === current) setLoadingOlder(false);
    }
  };

  const jumpToLive = () => {
    followRef.current = true;
    setFollow(true);
    setNewLines(0);
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  };
  const run = data?.run && data.run.id === runId ? data.run : null;
  const summary = run?.summary;
  const summaryParts = [
    summary?.eventsCollected !== undefined &&
      `${decimal(summary.eventsCollected, 0)} rencontre${summary.eventsCollected > 1 ? 's publiées' : ' publiée'}`,
    summary?.quotes !== undefined &&
      `${decimal(summary.quotes, 0)} relevé${summary.quotes > 1 ? 's' : ''}`,
    summary?.eventsFailed !== undefined &&
      `${decimal(summary.eventsFailed, 0)} rencontre${summary.eventsFailed > 1 ? 's non publiées' : ' non publiée'}`,
  ].filter(Boolean);
  const runIssues = [
    ...(run?.eventErrors?.map(
      (issue) =>
        `Événement ${issue.eventId} — ${
          issue.reason === 'Ambiguous source market identity'
            ? 'identité de marché ambiguë'
            : issue.reason
        }`,
    ) ?? []),
    ...(run?.interruption ? [`Arrêt technique : ${run.interruption.kind}`] : []),
    ...(run?.error && !run.interruption ? [run.error] : []),
  ];
  const issues = runIssues.length
    ? runIssues
    : (data?.incidents ?? []).map(
        (entry) => `${entry.eventId ? `Événement ${entry.eventId} — ` : ''}${entry.message}`,
      );

  const filtered = level !== 'all' || search.trim().length > 0;
  const runs = data?.recentRuns ?? [];
  const runOptions = [
    { value: 'service', label: 'Tout le service' },
    ...runs.map((recent) => ({
      value: recent.id,
      label: `${scheduledShortDate(recent.requestedAt)} · ${recent.name}`,
    })),
  ];
  if (runId && !runs.some((recent) => recent.id === runId)) {
    runOptions.push({ value: runId, label: 'Exécution sélectionnée' });
  }

  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      title={worker.name}
      description={
        <span className="log-service-status">
          <StatusDot tone={worker.online ? 'positive' : 'negative'} active={worker.online} />
          {worker.online ? 'Disponible' : 'Indisponible'}
          <span title={worker.lastSeenAt ? scheduledDate(worker.lastSeenAt) : undefined}>
            {worker.lastSeenAt
              ? ` · contact ${scheduledShortDate(worker.lastSeenAt)}`
              : ' · aucun contact'}
          </span>
        </span>
      }
      className="log-reader"
      onRestoreFocus={() => {
        onClose();
        onRestoreFocus();
      }}
    >
      <div className="log-reader-body">
        <Collapsible.Root open={filtersOpen} onOpenChange={setFiltersOpen} className="log-controls">
          <div className="log-toolbar">
            <Select
              label="Exécution"
              value={runId ?? 'service'}
              onChange={(value) => setRunId(value === 'service' ? undefined : value)}
              options={runOptions}
              className="log-run-picker"
            />
            <Collapsible.Trigger asChild>
              <Button
                variant={filtered ? 'primary' : 'secondary'}
                aria-label={filtered ? 'Filtres actifs' : 'Filtres'}
              >
                <Filter size={16} aria-hidden="true" />
                <span>
                  Filtres
                  {filtered
                    ? ` · ${Number(level !== 'all') + Number(search.trim().length > 0)}`
                    : ''}
                </span>
              </Button>
            </Collapsible.Trigger>
          </div>
          <Collapsible.Content className="ui-disclosure-content">
            <FilterControls
              level={level}
              setLevel={setLevel}
              search={search}
              setSearch={setSearch}
            />
            {filtered && (
              <button
                type="button"
                className="log-reset"
                onClick={() => {
                  setLevel('all');
                  setSearch('');
                }}
              >
                Effacer les filtres
              </button>
            )}
          </Collapsible.Content>
        </Collapsible.Root>
        {!loading && !error && data && (run || issues.length > 0) && (
          <section className="log-summary" aria-label="Résumé du journal">
            {run && (
              <div className="log-run-summary">
                <span className={`log-run-status log-run-status--${run.status}`}>
                  {statusNames[run.status]}
                </span>
                {run.complete === false && (
                  <span className="log-coverage">Couverture incomplète</span>
                )}
                {summaryParts.length > 0 && <p>{summaryParts.join(' · ')}</p>}
              </div>
            )}
            {(issues.length > 0 || run?.statusCorrection) && (
              <button
                type="button"
                className="log-issues-trigger"
                aria-expanded={issuesOpen}
                aria-controls="log-issues-detail"
                onClick={() => {
                  setIssuesOpen((value) => !value);
                  followRef.current = false;
                  setFollow(false);
                  if (listRef.current) listRef.current.scrollTop = 0;
                }}
              >
                <AlertTriangle size={15} aria-hidden="true" />
                <span>
                  {issues.length
                    ? `${issues.length} incident${issues.length > 1 ? 's' : ''}${run ? '' : ' récent' + (issues.length > 1 ? 's' : '')}`
                    : 'Statut corrigé'}
                </span>
                <ChevronDown size={14} className="script-chevron" aria-hidden="true" />
              </button>
            )}
          </section>
        )}
        <div
          className="log-lines-scroll"
          ref={listRef}
          aria-busy={showLoading}
          onScroll={() => {
            if (!listRef.current || !followRef.current || initializingScroll.current) return;
            if (
              listRef.current.scrollHeight -
                listRef.current.scrollTop -
                listRef.current.clientHeight >
              88
            ) {
              followRef.current = false;
              setFollow(false);
            }
          }}
        >
          <Collapsible.Root open={issuesOpen}>
            <Collapsible.Content className="ui-disclosure-content" id="log-issues-detail">
              <div className="log-important">
                <strong>À examiner</strong>
                <ul>
                  {issues.map((issue, index) => (
                    <li key={`${index}-${issue}`}>{issue}</li>
                  ))}
                </ul>
                {run?.statusCorrection && (
                  <p>
                    Statut historique corrigé à partir des relevés conservés ; détails anciens
                    indisponibles.
                  </p>
                )}
              </div>
            </Collapsible.Content>
          </Collapsible.Root>
          {error && (
            <div className="log-empty" role="alert">
              <p>{error}</p>
              <Button onClick={() => setRetryKey((value) => value + 1)}>Réessayer</Button>
            </div>
          )}
          {showLoading && !error ? (
            <div className="log-skeleton" role="status" aria-label="Chargement des journaux">
              {Array.from({ length: 8 }, (_, index) => (
                <div key={index} aria-hidden="true">
                  <span className="skeleton skeleton-short" />
                  <span className="skeleton" />
                </div>
              ))}
            </div>
          ) : (
            <>
              {hasOlder && (
                <Button variant="ghost" onClick={() => void loadOlder()} disabled={loadingOlder}>
                  {loadingOlder ? 'Chargement…' : 'Afficher les lignes précédentes'}
                </Button>
              )}
              {!error && !entries.length && (
                <p className="log-empty">
                  {filtered ? 'Aucun événement pour ces filtres.' : 'Aucun journal pour le moment.'}
                </p>
              )}
              <ol className="log-lines" aria-live="off">
                {entries.map((entry, index) => (
                  <Fragment key={entry.id}>
                    {(index === 0 ||
                      dayFormat.format(new Date(entries[index - 1]!.recordedAt)) !==
                        dayFormat.format(new Date(entry.recordedAt))) && (
                      <li className="log-day">
                        <time dateTime={entry.recordedAt}>
                          {dayFormat.format(new Date(entry.recordedAt))}
                        </time>
                      </li>
                    )}
                    <LogLine
                      entry={entry}
                      scriptName={runs.find((recent) => recent.scriptId === entry.scriptId)?.name}
                      onSelectRun={runId ? undefined : setRunId}
                      onInspect={() => {
                        followRef.current = false;
                        setFollow(false);
                      }}
                    />
                  </Fragment>
                ))}
              </ol>
            </>
          )}
        </div>
        {(run?.status === 'running' || newLines > 0 || refreshError) && (
          <footer className="log-reader-footer">
            {refreshError && (
              <span role="status">Actualisation indisponible · dernières lignes conservées</span>
            )}
            {run?.status === 'running' && (
              <label className="log-follow">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(event) => {
                    followRef.current = event.target.checked;
                    setFollow(event.target.checked);
                    if (event.target.checked) jumpToLive();
                  }}
                />
                Suivre en direct
              </label>
            )}
            {newLines > 0 && (
              <Button variant="ghost" onClick={jumpToLive}>
                {newLines} nouvelle{newLines > 1 ? 's' : ''} · Revenir au direct
              </Button>
            )}
          </footer>
        )}
        <span className="sr-only" aria-live="polite">
          {critical}
        </span>
      </div>
    </Modal>
  );
}
