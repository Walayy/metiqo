import { useEffect, useRef, useState } from 'react';
import { Dialog } from 'radix-ui';
import { ChevronLeft, Filter, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { scheduledDate, scheduledShortDate } from '@/lib/format';
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
  examined: 'Sélections examinées',
  changed: 'Résultats modifiés',
  pending: 'En attente',
  won: 'Gagnées',
  lost: 'Perdues',
  void: 'Annulées',
};
const timeFormat = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
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
  return (
    <div className="log-filters">
      <div className="log-filter-levels" role="group" aria-label="Gravité">
        {(
          [
            ['error', 'Erreurs'],
            ['warning', 'Avertissements'],
            ['all', 'Tout'],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={level === value ? 'is-selected' : ''}
            aria-pressed={level === value}
            onClick={() => setLevel(value)}
          >
            {label}
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
          placeholder="Rencontre, étape, message…"
        />
      </label>
    </div>
  );
}

function LogLine({
  entry,
  scriptName,
  onSelectRun,
}: {
  entry: WorkerLogEntry;
  scriptName?: string;
  onSelectRun?: (runId: string) => void;
}) {
  const detail = Object.entries(entry.context);
  return (
    <li className={`log-line log-line--${entry.level}`}>
      <div className="log-line-primary">
        <time dateTime={entry.recordedAt} title={scheduledDate(entry.recordedAt)}>
          {timeFormat.format(new Date(entry.recordedAt))}
        </time>
        <span className="log-level">{levelNames[entry.level]}</span>
        <span className="log-stage">{entry.stage}</span>
      </div>
      <div className="log-line-content">
        {entry.scriptId && (
          <strong className="log-line-script">{scriptName ?? entry.scriptId}</strong>
        )}
        <p>{entry.message}</p>
        {entry.eventId && <span className="log-event-id">Rencontre {entry.eventId}</span>}
        {entry.runId && onSelectRun && (
          <button type="button" className="log-line-run" onClick={() => onSelectRun(entry.runId!)}>
            Voir cette exécution
          </button>
        )}
        {detail.length > 0 && (
          <details>
            <summary>Contexte</summary>
            <dl>
              {detail.map(([key, value]) => (
                <div key={key}>
                  <dt>{contextNames[key] ?? key}</dt>
                  <dd>{Array.isArray(value) ? <code>{value.join(' → ')}</code> : String(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
      </div>
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
  const [filterSheet, setFilterSheet] = useState(false);
  const [data, setData] = useState<WorkerLogs | null>(null);
  const [entries, setEntries] = useState<WorkerLogEntry[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const [newLines, setNewLines] = useState(0);
  const [critical, setCritical] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const lastId = useRef(0);
  const requestId = useRef(0);
  const polling = useRef(false);
  const followRef = useRef(true);
  const initializingScroll = useRef(true);

  useEffect(() => {
    const desktopFilters = window.matchMedia('(min-width: 641px)');
    const closeMobileFilters = () => {
      if (desktopFilters.matches) setFilterSheet(false);
    };
    desktopFilters.addEventListener('change', closeMobileFilters);
    return () => desktopFilters.removeEventListener('change', closeMobileFilters);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const current = ++requestId.current;
    const controller = new AbortController();
    lastId.current = 0;
    followRef.current = true;
    initializingScroll.current = true;
    queueMicrotask(() => {
      if (controller.signal.aborted || requestId.current !== current) return;
      setLoading(true);
      setError(null);
      setData(null);
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
        window.requestAnimationFrame(() => {
          if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
          window.requestAnimationFrame(() => {
            initializingScroll.current = false;
          });
        });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted && requestId.current === current) {
          setError(cause instanceof Error ? cause.message : 'Journaux indisponibles.');
        }
      })
      .finally(() => {
        if (requestId.current === current) setLoading(false);
      });
    return () => controller.abort();
  }, [worker.id, runId, level, query, retryKey]);

  const ready = data !== null && !loading;
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
      setError(cause instanceof Error ? cause.message : 'Chargement impossible.');
    } finally {
      setLoadingOlder(false);
    }
  };

  const jumpToLive = () => {
    followRef.current = true;
    setFollow(true);
    setNewLines(0);
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  };
  const run = data?.run;
  const summary = run?.summary;
  const summaryParts = [
    summary?.eventsCollected !== undefined && `${summary.eventsCollected} rencontres publiées`,
    summary?.quotes !== undefined && `${summary.quotes} relevés`,
    summary?.eventsFailed !== undefined && `${summary.eventsFailed} rencontres non publiées`,
  ].filter(Boolean);
  const runIssues = [
    ...(run?.eventErrors
      ?.slice(0, 4)
      .map(
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

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="log-reader-overlay" />
        <Dialog.Content
          className="log-reader"
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            onRestoreFocus();
          }}
        >
          <header className="log-reader-header">
            <div>
              <span className="log-reader-eyebrow">JOURNAL D’EXPLOITATION</span>
              <Dialog.Title>{worker.name}</Dialog.Title>
              <p>
                {worker.online ? 'Service connecté' : 'Service indisponible'} · Dernier contact :{' '}
                {worker.lastSeenAt ? scheduledDate(worker.lastSeenAt) : 'inconnu'}
              </p>
            </div>
            <Dialog.Close asChild>
              <Button iconOnly aria-label="Fermer les journaux">
                <X size={20} />
              </Button>
            </Dialog.Close>
          </header>
          <div className="log-reader-layout">
            <nav className="log-run-nav" aria-label="Exécutions du worker">
              <strong>Exécutions</strong>
              <button
                type="button"
                className={!runId ? 'is-selected' : ''}
                onClick={() => setRunId(undefined)}
              >
                Tout le service
              </button>
              {(data?.recentRuns ?? []).map((recent) => (
                <button
                  type="button"
                  key={recent.id}
                  className={runId === recent.id ? 'is-selected' : ''}
                  onClick={() => setRunId(recent.id)}
                >
                  <span>{recent.name}</span>
                  <small>
                    {scheduledShortDate(recent.requestedAt)} · {statusNames[recent.status]}
                  </small>
                </button>
              ))}
            </nav>
            <div className="log-reader-main">
              <label className="log-run-picker">
                Exécution
                <select
                  value={runId ?? ''}
                  onChange={(event) => setRunId(event.target.value || undefined)}
                >
                  <option value="">Tout le service</option>
                  {(data?.recentRuns ?? []).map((recent) => (
                    <option key={recent.id} value={recent.id}>
                      {recent.name} · {scheduledShortDate(recent.requestedAt)}
                    </option>
                  ))}
                </select>
              </label>
              <section className="log-summary" aria-label="Résumé du journal">
                <div className="log-summary-heading">
                  <div>
                    <h3>
                      {runId && run
                        ? `${data?.recentRuns.find((item) => item.id === runId)?.name ?? run.scriptId} · ${scheduledShortDate(run.requestedAt)}`
                        : 'Tous les événements du service'}
                    </h3>
                    {run && (
                      <span>
                        {statusNames[run.status]}
                        {run.complete === false ? ' · couverture incomplète' : ''}
                      </span>
                    )}
                  </div>
                  {runId && (
                    <button type="button" onClick={() => setRunId(undefined)}>
                      <ChevronLeft size={16} aria-hidden="true" /> Tout le service
                    </button>
                  )}
                </div>
                {summaryParts.length > 0 && <p>{summaryParts.join(' · ')}</p>}
                {issues.length > 0 && (
                  <div className="log-important">
                    <strong>À examiner</strong>
                    <ul>
                      {issues.map((issue, index) => (
                        <li key={`${index}-${issue}`}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {run?.statusCorrection && (
                  <p>
                    Statut historique corrigé à partir des relevés conservés ; détails anciens
                    indisponibles.
                  </p>
                )}
              </section>
              <div className="log-filter-desktop">
                <FilterControls
                  level={level}
                  setLevel={setLevel}
                  search={search}
                  setSearch={setSearch}
                />
              </div>
              <div className="log-filter-mobile">
                <Button onClick={() => setFilterSheet(true)}>
                  <Filter size={16} aria-hidden="true" /> Filtres
                  {level !== 'all' || query ? ' actifs' : ''}
                </Button>
              </div>
              <div
                className="log-lines-scroll"
                ref={listRef}
                onScroll={() => {
                  if (!listRef.current || !followRef.current || initializingScroll.current) return;
                  const away =
                    listRef.current.scrollHeight -
                      listRef.current.scrollTop -
                      listRef.current.clientHeight >
                    88;
                  if (away) {
                    followRef.current = false;
                    setFollow(false);
                  }
                }}
              >
                {hasOlder && (
                  <Button onClick={() => void loadOlder()} disabled={loadingOlder}>
                    {loadingOlder ? 'Chargement…' : 'Afficher les lignes précédentes'}
                  </Button>
                )}
                {loading && (
                  <p className="log-empty" role="status">
                    Chargement des journaux…
                  </p>
                )}
                {error && (
                  <p className="log-empty" role="alert">
                    {error}{' '}
                    <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
                      Réessayer
                    </button>
                  </p>
                )}
                {!loading && !error && !entries.length && (
                  <p className="log-empty">
                    {level !== 'all' || query
                      ? 'Aucune ligne pour ces filtres.'
                      : 'Aucun journal conservé pour cette sélection.'}
                  </p>
                )}
                <ol className="log-lines" aria-live="off">
                  {entries.map((entry) => (
                    <LogLine
                      key={entry.id}
                      entry={entry}
                      scriptName={
                        data?.recentRuns.find((recent) => recent.scriptId === entry.scriptId)?.name
                      }
                      onSelectRun={runId ? undefined : setRunId}
                    />
                  ))}
                </ol>
              </div>
              <footer className="log-reader-footer">
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
                  <Button onClick={jumpToLive}>
                    {newLines} nouvelles lignes · Revenir au direct
                  </Button>
                )}
                <span className="sr-only" aria-live="polite">
                  {critical}
                </span>
              </footer>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
      <Dialog.Root open={filterSheet} onOpenChange={setFilterSheet}>
        <Dialog.Portal>
          <Dialog.Overlay className="log-filter-overlay" />
          <Dialog.Content className="log-filter-sheet" aria-describedby={undefined}>
            <div className="log-filter-sheet-header">
              <Dialog.Title>Filtrer les journaux</Dialog.Title>
              <Dialog.Close asChild>
                <Button iconOnly aria-label="Fermer les filtres">
                  <X size={18} />
                </Button>
              </Dialog.Close>
            </div>
            <FilterControls
              level={level}
              setLevel={setLevel}
              search={search}
              setSearch={setSearch}
            />
            <Button variant="primary" onClick={() => setFilterSheet(false)}>
              Afficher les résultats
            </Button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </Dialog.Root>
  );
}
