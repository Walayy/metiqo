import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { ContentTransition } from '@/components/ui/content-transition';
import { useDeferredValue, useEffect, useId, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Accordion, Collapsible, DropdownMenu } from 'radix-ui';
import {
  CalendarClock,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Ellipsis,
  History,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { clsx } from 'clsx';
import { SourceMark } from '@/components/ui/source-mark';
import { StatusDot } from '@/components/ui/status-dot';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { useDialogPresence } from '@/components/ui/use-dialog-presence';
import { Select } from '@/components/ui/select';
import { FieldFeedback } from '@/components/ui/field-feedback';
import { accountDate, scheduledDate, scheduledShortDate } from '@/lib/format';
import { sessionQuery } from '@/features/auth/api';
import { AdminError, adminRequest, scriptsQuery, useAdminAction, usersQuery } from './api';
import { previewSchema, runSchema, successSchema } from './contracts';
import type { AdminUser, Script, ScriptRun } from './contracts';
import { days, fromCron, scheduleLabel, toCron } from './schedule';
import type { Frequency } from './schedule';
import './admin.css';
import { StatusPanel } from '@/features/status/status-panel';
import { needsStatusScreen } from '@/lib/http-error';
const statuses: Record<ScriptRun['status'], string> = {
  queued: 'En attente',
  running: 'En cours',
  succeeded: 'Terminée',
  failed: 'Échec',
  interrupted: 'Interrompue',
};
const stakeStages: Record<string, string> = {
  browser_start: 'ouverture du navigateur',
  listing: 'lecture des rencontres',
  event_traversal: 'parcours de la rencontre',
  publication: 'publication des relevés',
};
const stakeDeferrals: Record<string, string> = {
  cycle_budget: 'Limite du passage atteinte ; les rencontres restantes seront reprises.',
  stop_requested: 'Arrêt du worker demandé pendant le passage.',
  request_budget: 'Budget de requêtes atteint ; reprise après le délai source.',
  cooldown: 'Source en attente du délai autorisé.',
};
const feedbackReserve = [
  'Cette planification a changé. Fermez puis rouvrez le formulaire.',
  'Utilisez un cron à cinq champs : minute, heure, jour, mois, semaine.',
  'Le worker de ce script est indisponible. Réessayez après son retour.',
];
function ErrorState({ error, retry, busy }: { error: Error; retry: () => void; busy: boolean }) {
  return <StatusPanel error={error} onRetry={retry} busy={busy} headingLevel={2} />;
}
function Loading({ users = false, count = 6 }: { users?: boolean; count?: number }) {
  return (
    <ContentTransition id="admin-loading">
      <div aria-busy="true" role="status" aria-label="Chargement de l’administration">
        {users ? (
          <div className="admin-users">
            <div className="admin-user-head" aria-hidden="true">
              <span>UTILISATEUR</span>
              <span>RÔLE</span>
              <span>STATUT</span>
              <span>SESSIONS</span>
              <span />
            </div>
            {Array.from({ length: count }, (_, id) => (
              <div className="admin-user-row" key={id} aria-hidden="true">
                <div className="admin-user-identity">
                  <span className="admin-avatar skeleton" />
                  <div>
                    <span className="skeleton skeleton-user-email" />
                    <span className="skeleton skeleton-medium" />
                  </div>
                </div>
                <span className="skeleton skeleton-short" />
                <span className="skeleton skeleton-short" />
                <span className="skeleton skeleton-short" />
                <span className="skeleton skeleton-admin-action" />
              </div>
            ))}
          </div>
        ) : (
          <div aria-hidden="true">
            <div className="scripts-toolbar">
              <span className="skeleton skeleton-medium" />
              <span className="skeleton skeleton-medium" />
            </div>
            <div className="script-families">
              {[0, 1, 2].map((family) => (
                <div className="script-family" key={family}>
                  <div className="script-family-heading">
                    <span className="skeleton skeleton-medium" />
                  </div>
                  <div className="script-list">
                    {[0, 1].map((script) => (
                      <div className="script-entry-skeleton" key={script}>
                        <span className="script-entry-identity">
                          <span className="script-entry-mark skeleton" />
                          <span className="script-entry-copy">
                            <span className="skeleton skeleton-medium" />
                            <span className="skeleton skeleton-short" />
                          </span>
                        </span>
                        <span className="skeleton skeleton-medium" />
                        <span className="skeleton skeleton-short" />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </ContentTransition>
  );
}
export function AdminPage({ userId, section }: { userId: string; section: 'scripts' | 'users' }) {
  return (
    <div className={clsx('admin-page', section === 'scripts' && 'admin-page--scripts')}>
      {section === 'scripts' ? (
        <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" />
                ADMINISTRATION
              </div>
              <h1>Scripts</h1>
              <p>Collectes et horaires.</p>
            </div>
          </div>
          <Scripts />
        </>
      ) : (
        <UserList userId={userId} />
      )}
    </div>
  );
}
function Scripts() {
  const familyHeadingId = useId();
  const query = useQuery(scriptsQuery);
  const loading = useMinimumLoading(query.isPending, 'scripts');
  const client = useQueryClient();
  const [editing, setEditing] = useState<Script | null>(null);
  const [history, setHistory] = useState<Script | null>(null);
  const shownEditing = useDialogPresence(editing);
  const shownHistory = useDialogPresence(history);
  const action = useAdminAction(runSchema);
  useEffect(() => {
    if (query.error instanceof AdminError && [401, 403].includes(query.error.status)) {
      void client.invalidateQueries({ queryKey: sessionQuery.queryKey });
    }
  }, [client, query.error]);
  if (!query.error && (loading || query.isPending)) return <Loading />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} busy={query.isFetching} />
    );
  if (needsStatusScreen(action.error))
    return (
      <StatusPanel
        error={action.error}
        headingLevel={2}
        retryLabel="Vérifier l’état des scripts"
        busy={query.isFetching}
        onRetry={() => {
          void query.refetch().then(() => action.reset());
        }}
        description={`${action.error.message} Vérifiez l’historique avant de demander un nouveau lancement : la première demande a pu être reçue.`}
      />
    );
  if (!query.data) return <Loading />;
  const { items, worker } = query.data;
  const historyScript = items.find((item) => item.id === shownHistory?.id) ?? shownHistory;
  const families = Array.from(
    items.reduce((groups, script) => {
      const scripts = groups.get(script.family) ?? [];
      scripts.push(script);
      groups.set(script.family, scripts);
      return groups;
    }, new Map<string, Script[]>()),
  ).sort(([left], [right]) => left.localeCompare(right, 'fr'));
  return (
    <ContentTransition id="scripts-ready">
      <div className="scripts-toolbar">
        <span>
          {items.length} scripts · {families.length} familles
        </span>
        <span className={clsx('worker-status', worker.online && 'is-online')}>
          <StatusDot tone={worker.online ? 'positive' : 'negative'} />
          {worker.online ? 'Worker connecté' : 'Worker indisponible'}
        </span>
      </div>
      {!worker.online && (
        <p className="admin-callout" role="status">
          Les planifications restent enregistrées. Les exécutions reprendront au retour du worker.
          {worker.lastSeenAt && ` Dernier contact : ${scheduledDate(worker.lastSeenAt)}.`}
        </p>
      )}
      <div className="admin-action-feedback" role="status" aria-live="polite">
        {action.error?.message ??
          (action.isSuccess ? 'Lancement demandé. Le worker prendra en charge la collecte.' : '')}
      </div>
      {!items.length ? (
        <div className="admin-empty">Aucun script configuré.</div>
      ) : (
        <Accordion.Root type="single" collapsible className="script-families">
          {families.map(([family, scripts], index) => (
            <section
              className="script-family"
              key={family}
              aria-labelledby={`${familyHeadingId}-${index}`}
            >
              <div className="script-family-heading">
                <div className="script-family-title">
                  <SourceMark source={family} decorative />
                  <h2 id={`${familyHeadingId}-${index}`}>{family}</h2>
                  <span className="script-family-count" aria-label={`${scripts.length} scripts`}>
                    {scripts.length}
                  </span>
                </div>
                <span className="script-column-label" aria-hidden="true">
                  Prochain passage
                </span>
                <span className="script-column-label script-column-state" aria-hidden="true">
                  État
                </span>
              </div>
              <div className="script-list">
                {scripts.map((script) => {
                  const last = script.runs[0];
                  const active = script.activeRun;
                  const state = active
                    ? statuses[active.status]
                    : !script.available
                      ? 'Indisponible'
                      : script.enabled
                        ? 'Actif'
                        : 'En pause';
                  const next = script.enabled ? script.nextRunAt : null;
                  const timezone = script.timezone === 'Europe/Paris' ? 'Paris' : 'UTC';
                  const shortName = script.name.startsWith(`${family} · `)
                    ? script.name.slice(family.length + 3)
                    : script.name;
                  const name = shortName.charAt(0).toLocaleUpperCase('fr-FR') + shortName.slice(1);
                  return (
                    <Accordion.Item className="script-entry" value={script.id} key={script.id}>
                      <Accordion.Header>
                        <Accordion.Trigger className="script-entry-trigger">
                          <span className="script-entry-identity">
                            <span className="script-entry-mark">
                              <SourceMark source={script.id} decorative />
                            </span>
                            <span className="script-entry-copy">
                              <span className="script-entry-name">{name}</span>
                              <span className="script-entry-schedule">
                                {scheduleLabel(script.cron)}
                              </span>
                            </span>
                          </span>
                          <span
                            className="script-entry-next"
                            role="group"
                            aria-label={
                              next
                                ? `Prochain passage : ${scheduledDate(next, script.timezone)} · ${timezone}`
                                : 'Aucun passage planifié'
                            }
                            title={
                              next
                                ? `${scheduledDate(next, script.timezone)} · ${timezone}`
                                : undefined
                            }
                          >
                            <span>Prochain passage</span>
                            <strong>
                              {next ? scheduledShortDate(next, script.timezone) : '—'}
                            </strong>
                          </span>
                          <span
                            className={clsx(
                              'script-entry-state',
                              active && 'is-running',
                              script.enabled && script.available && !active && 'is-active',
                            )}
                          >
                            <StatusDot
                              tone={
                                !script.available
                                  ? 'negative'
                                  : script.enabled || active
                                    ? 'positive'
                                    : 'muted'
                              }
                              active={!!active || !script.available || script.enabled}
                            />
                            {state}
                          </span>
                          <ChevronDown size={16} className="script-chevron" aria-hidden="true" />
                        </Accordion.Trigger>
                      </Accordion.Header>
                      <Accordion.Content className="ui-accordion-content script-entry-content">
                        <div className="script-entry-detail">
                          <p>{script.description}</p>
                          <div className="script-last-run">
                            <Clock3 size={14} aria-hidden="true" />
                            <span>Dernière exécution</span>
                            <strong>{last ? statuses[last.status] : 'Aucune'}</strong>
                            {last && (
                              <time
                                dateTime={last.finishedAt ?? last.startedAt ?? last.requestedAt}
                              >
                                {scheduledShortDate(
                                  last.finishedAt ?? last.startedAt ?? last.requestedAt,
                                  script.timezone,
                                )}{' '}
                                · {timezone}
                              </time>
                            )}
                          </div>
                          <div className="script-actions">
                            <Button
                              variant="ghost"
                              onClick={() => setHistory(script)}
                              aria-label={`Historique de ${script.name}`}
                            >
                              <History size={16} />
                              Historique
                            </Button>
                            <div className="script-actions-end">
                              <Button
                                onClick={() => setEditing(script)}
                                aria-label={`Planifier ${script.name}`}
                              >
                                <Settings2 size={16} />
                                Planifier
                              </Button>
                              <DropdownMenu.Root>
                                <DropdownMenu.Trigger asChild>
                                  <Button
                                    variant="ghost"
                                    iconOnly
                                    aria-label={`Autres actions pour ${script.name}`}
                                  >
                                    <Ellipsis size={19} />
                                  </Button>
                                </DropdownMenu.Trigger>
                                <DropdownMenu.Portal>
                                  <DropdownMenu.Content
                                    className="script-menu"
                                    align="end"
                                    sideOffset={6}
                                  >
                                    <DropdownMenu.Item
                                      className="script-menu-item"
                                      disabled={!script.available || !!active || action.isPending}
                                      onSelect={() =>
                                        action.mutate({ path: `/scripts/${script.id}/run` })
                                      }
                                    >
                                      <Play size={15} />
                                      {active ? statuses[active.status] : 'Lancer maintenant'}
                                    </DropdownMenu.Item>
                                  </DropdownMenu.Content>
                                </DropdownMenu.Portal>
                              </DropdownMenu.Root>
                            </div>
                          </div>
                        </div>
                      </Accordion.Content>
                    </Accordion.Item>
                  );
                })}
              </div>
            </section>
          ))}
        </Accordion.Root>
      )}
      {shownEditing && (
        <ScheduleEditor
          script={shownEditing}
          open={editing !== null}
          close={() => setEditing(null)}
        />
      )}
      {historyScript && (
        <Modal
          open={history !== null}
          onOpenChange={(open) => {
            if (!open) setHistory(null);
          }}
          title="Historique"
          description={historyScript.name}
          className="admin-dialog"
        >
          <div className="admin-dialog-body">
            <p className="admin-muted">
              Dernières exécutions · {historyScript.timezone === 'Europe/Paris' ? 'Paris' : 'UTC'}
            </p>
            {!historyScript.runs.length ? (
              <div className="admin-empty">Aucune exécution pour le moment.</div>
            ) : (
              <ol className="run-list">
                {historyScript.runs.map((run) => {
                  const summary = run.summary
                    ? [
                        run.summary.eventsCollected !== undefined &&
                          `${run.summary.eventsCollected} matchs`,
                        run.summary.markets !== undefined && `${run.summary.markets} marchés`,
                        run.summary.quotes !== undefined && `${run.summary.quotes} relevés`,
                        run.summary.eventsFailed !== undefined &&
                          `${run.summary.eventsFailed} erreurs`,
                      ]
                        .filter(Boolean)
                        .join(' · ')
                    : '';
                  return (
                    <li key={run.id}>
                      <Collapsible.Root className="run-entry">
                        <Collapsible.Trigger type="button" className="run-trigger">
                          <span className="run-identity">
                            <strong title={scheduledDate(run.requestedAt, historyScript.timezone)}>
                              {scheduledShortDate(run.requestedAt, historyScript.timezone)}
                            </strong>
                            <span>{run.trigger === 'manual' ? 'Manuelle' : 'Planifiée'}</span>
                            {run.status === 'succeeded' && run.complete === false && (
                              <span className="run-coverage">Couverture incomplète</span>
                            )}
                          </span>
                          <span
                            className={clsx(
                              'admin-status',
                              run.status === 'succeeded' && 'is-positive',
                              ['failed', 'interrupted'].includes(run.status) && 'is-error',
                            )}
                          >
                            {statuses[run.status]}
                          </span>
                          <ChevronDown size={15} className="run-chevron" aria-hidden="true" />
                        </Collapsible.Trigger>
                        <Collapsible.Content className="ui-disclosure-content">
                          <div className="run-detail">
                            <dl>
                              <div>
                                <dt>Début</dt>
                                <dd>
                                  {run.startedAt
                                    ? scheduledDate(run.startedAt, historyScript.timezone)
                                    : 'En attente'}
                                </dd>
                              </div>
                              <div>
                                <dt>Fin</dt>
                                <dd>
                                  {run.finishedAt
                                    ? scheduledDate(run.finishedAt, historyScript.timezone)
                                    : '—'}
                                </dd>
                              </div>
                            </dl>
                            {summary && <p>{summary}</p>}
                            {run.status === 'succeeded' && run.complete === false && (
                              <p className="run-coverage-note">
                                {run.summary?.snapshots
                                  ? 'La collecte a publié des relevés, mais le passage est incomplet.'
                                  : 'Le passage est incomplet ; aucune nouvelle cote publiée.'}
                              </p>
                            )}
                            {run.statusCorrection && (
                              <p className="run-coverage-note">
                                Statut historique corrigé grâce aux relevés conservés. L’ancienne
                                version ne détaillait pas les incidents de ce passage.
                                {run.statusCorrection.previousError &&
                                  ` Ancien diagnostic : ${run.statusCorrection.previousError}.`}
                              </p>
                            )}
                            {run.eventErrors && run.eventErrors.length > 0 && (
                              <div className="run-issues">
                                <strong>Rencontres non publiées</strong>
                                <ul>
                                  {run.eventErrors.map((issue, index) => (
                                    <li key={`${issue.eventId}-${index}`}>
                                      <span>Stake {issue.eventId}</span> · {issue.reason}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {run.interruption && (
                              <div className="run-issues">
                                <strong>
                                  {run.summary?.snapshots
                                    ? 'Arrêt technique après publication'
                                    : 'Arrêt technique'}
                                </strong>
                                <p>
                                  {run.interruption.kind} pendant{' '}
                                  {stakeStages[run.interruption.stage] ?? run.interruption.stage}
                                  {run.interruption.eventId &&
                                    ` · rencontre Stake ${run.interruption.eventId}`}
                                </p>
                                {run.interruption.frames.length > 0 && (
                                  <details>
                                    <summary>Trace technique</summary>
                                    <code>{run.interruption.frames.join(' → ')}</code>
                                  </details>
                                )}
                              </div>
                            )}
                            {run.deferredReason && (
                              <p className="run-coverage-note">
                                {stakeDeferrals[run.deferredReason] ??
                                  `Passage différé : ${run.deferredReason}`}
                              </p>
                            )}
                            {run.error && <p className="admin-error">{run.error}</p>}
                          </div>
                        </Collapsible.Content>
                      </Collapsible.Root>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </Modal>
      )}
    </ContentTransition>
  );
}
function ScheduleEditor({
  script,
  open,
  close,
}: {
  script: Script;
  open: boolean;
  close: () => void;
}) {
  const [form, setForm] = useState(() => fromCron(script.cron));
  const [timezone, setTimezone] = useState(script.timezone);
  const [enabled, setEnabled] = useState(script.enabled);
  const [attempted, setAttempted] = useState(false);
  const cron = toCron(form);
  const [draft, setDraft] = useState({ cron, timezone });
  useEffect(() => {
    const timer = setTimeout(() => setDraft({ cron, timezone }), 350);
    return () => clearTimeout(timer);
  }, [cron, timezone]);
  const preview = useQuery({
    queryKey: ['admin', 'preview', draft],
    retry: false,
    queryFn: ({ signal }) => adminRequest('/scripts/preview', previewSchema, signal, 'POST', draft),
  });
  const action = useAdminAction(successSchema, close);
  const pendingPreview = preview.isPending || draft.cron !== cron || draft.timezone !== timezone;
  const error = action.error?.message ?? (attempted ? preview.error?.message : undefined);
  const serviceError = needsStatusScreen(action.error)
    ? action.error
    : needsStatusScreen(preview.error)
      ? preview.error
      : null;
  return (
    <Modal
      open={open}
      onOpenChange={(open) => {
        if (!open && !action.isPending) close();
      }}
      title="Planification"
      description={script.name}
      className="admin-dialog"
    >
      {serviceError ? (
        <StatusPanel
          compact
          error={serviceError}
          busy={preview.isFetching}
          retryLabel={action.error ? 'Reprendre le formulaire' : 'Vérifier la planification'}
          onRetry={() => {
            if (action.error) action.reset();
            else void preview.refetch();
          }}
        />
      ) : (
        <form
          className="admin-dialog-body schedule-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            setAttempted(true);
            if (!pendingPreview && !preview.error)
              action.mutate({
                path: `/scripts/${script.id}`,
                method: 'PATCH',
                body: { cron, timezone, enabled, revision: script.revision },
              });
          }}
        >
          <label className="schedule-toggle">
            <input
              type="checkbox"
              checked={enabled}
              disabled={action.isPending}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>
              <strong>Exécution automatique</strong>
            </span>
          </label>
          <fieldset disabled={action.isPending}>
            <div className="admin-field">
              <span>Fréquence</span>
              <Select
                label="Fréquence"
                value={form.frequency}
                onChange={(value) => {
                  setForm({ ...form, frequency: value as Frequency });
                  action.reset();
                }}
                options={[
                  { value: 'minutes', label: 'Toutes les X minutes' },
                  { value: 'hours', label: 'Toutes les X heures' },
                  { value: 'daily', label: 'Chaque jour' },
                  { value: 'weekly', label: 'Chaque semaine' },
                  { value: 'custom', label: 'Cron personnalisé' },
                ]}
              />
            </div>
            <div className="schedule-fields">
              {form.frequency === 'minutes' && (
                <div className="admin-field">
                  <span>Intervalle</span>
                  <Select
                    label="Intervalle en minutes"
                    value={form.minutes}
                    onChange={(minutes) => setForm({ ...form, minutes })}
                    options={['1', '2', '3', '4', '5', '6', '10', '12', '15', '20', '30'].map(
                      (value) => ({
                        value,
                        label: `${value} minute${value === '1' ? '' : 's'}`,
                      }),
                    )}
                  />
                </div>
              )}
              {form.frequency === 'hours' && (
                <div className="admin-field">
                  <span>Intervalle</span>
                  <Select
                    label="Intervalle"
                    value={form.hours}
                    onChange={(hours) => setForm({ ...form, hours })}
                    options={['1', '2', '3', '4', '6', '8', '12'].map((value) => ({
                      value,
                      label: `${value} heure${value === '1' ? '' : 's'}`,
                    }))}
                  />
                </div>
              )}
              {form.frequency === 'weekly' && (
                <div className="admin-field">
                  <span>Jour</span>
                  <Select
                    label="Jour"
                    value={form.day}
                    onChange={(day) => setForm({ ...form, day })}
                    options={days}
                  />
                </div>
              )}
              {['daily', 'weekly'].includes(form.frequency) && (
                <label className="admin-field">
                  Heure
                  <input
                    aria-label="Heure"
                    type="time"
                    value={form.at}
                    onChange={(event) => {
                      setForm({ ...form, at: event.target.value });
                      action.reset();
                    }}
                    aria-describedby="schedule-feedback"
                  />
                </label>
              )}
              <div className="admin-field">
                <span>Fuseau horaire</span>
                <Select
                  label="Fuseau horaire"
                  value={timezone}
                  onChange={(value) => setTimezone(value as Script['timezone'])}
                  options={[
                    { value: 'Europe/Paris', label: 'Paris · été / hiver' },
                    { value: 'UTC', label: 'UTC' },
                  ]}
                />
              </div>
            </div>
            {form.frequency === 'custom' && (
              <label className="admin-field">
                Expression cron
                <input
                  value={form.custom}
                  maxLength={100}
                  onChange={(event) => {
                    setForm({ ...form, custom: event.target.value });
                    action.reset();
                  }}
                  aria-invalid={attempted && !!preview.error}
                  aria-describedby="schedule-feedback"
                  placeholder="0 4 * * *"
                  autoComplete="off"
                  spellCheck={false}
                />
                <small>
                  Minute · heure · jour du mois · mois · jour de semaine (0 = dimanche).
                </small>
              </label>
            )}
          </fieldset>
          <FieldFeedback
            id="schedule-feedback"
            message={error ?? (pendingPreview ? 'Vérification de la planification…' : '')}
            tone={error ? 'error' : 'hint'}
            reserve={feedbackReserve}
          />
          <div className="schedule-preview" aria-busy={pendingPreview}>
            <strong>
              <CalendarClock size={16} />
              {enabled ? 'Prochains passages' : 'Passages prévus après réactivation'}
            </strong>
            <ol>
              {[0, 1, 2].map((index) => (
                <li key={index}>
                  <span>{index + 1}</span>
                  {!pendingPreview && preview.data
                    ? preview.data.upcoming[index]
                      ? scheduledShortDate(preview.data.upcoming[index], timezone)
                      : '—'
                    : '—'}
                </li>
              ))}
            </ol>
          </div>
          <div className="admin-form-actions">
            <Button onClick={close} disabled={action.isPending}>
              Annuler
            </Button>
            <Button type="submit" variant="primary" disabled={action.isPending}>
              {action.isPending ? 'Enregistrement…' : 'Enregistrer'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
function UserList({ userId }: { userId: string }) {
  const [search, setSearch] = useState('');
  const deferred = useDeferredValue(search);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const shownEditing = useDialogPresence(editing);
  const query = useQuery(usersQuery(deferred, page));
  const loading = useMinimumLoading(query.isFetching, JSON.stringify([deferred, page]));
  return (
    <>
      <div className="page-heading admin-users-page-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            ADMINISTRATION
          </div>
          <h1 className="admin-users-title">
            <span>Utilisateurs</span>
            <span
              className="count-pill"
              aria-label={
                query.data
                  ? `${query.data.total} comptes`
                  : query.error
                    ? 'Nombre de comptes indisponible'
                    : 'Nombre de comptes en chargement'
              }
            >
              {query.data?.total ?? (query.error ? '—' : '…')}
            </span>
          </h1>
          <p>Gérez les accès et les sessions des comptes inscrits.</p>
        </div>
        <span className="admin-badge">
          <ShieldCheck size={16} />
          Administrateur
        </span>
      </div>
      <div className="admin-users-toolbar">
        <label className="search-field admin-search">
          <Search size={16} />
          <input
            placeholder="Rechercher un email…"
            aria-label="Rechercher un utilisateur"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </label>
      </div>
      <ContentTransition id={loading ? 'loading' : 'ready'}>
        {!query.error && (loading || query.isPending) ? (
          <Loading users count={query.data?.items.length || 6} />
        ) : query.error ? (
          <ErrorState
            error={query.error}
            retry={() => void query.refetch()}
            busy={query.isFetching}
          />
        ) : query.data ? (
          <>
            {!query.data.items.length ? (
              <div className="admin-empty">
                <Users size={26} />
                <h3>Aucun utilisateur trouvé</h3>
                <p>Essayez une autre adresse email.</p>
              </div>
            ) : (
              <div className="admin-users">
                <div className="admin-user-head" aria-hidden="true">
                  <span>UTILISATEUR</span>
                  <span>RÔLE</span>
                  <span>STATUT</span>
                  <span>SESSIONS</span>
                  <span />
                </div>
                {query.data.items.map((user) => (
                  <article className="admin-user-row" key={user.id} aria-label={user.email}>
                    <div className="admin-user-identity">
                      <span className="admin-avatar">{user.email.slice(0, 2).toUpperCase()}</span>
                      <div>
                        <strong>
                          {user.email}
                          {user.id === userId && <small>Vous</small>}
                        </strong>
                        <span>Inscrit le {accountDate(user.createdAt)}</span>
                      </div>
                    </div>
                    <span className="user-role">
                      {user.role === 'admin' && <ShieldCheck size={14} />}
                      {user.role === 'admin' ? 'Admin' : 'Utilisateur'}
                    </span>
                    <span className={clsx('admin-status', !user.disabled && 'is-positive')}>
                      {user.disabled ? 'Suspendu' : user.verified ? 'Actif' : 'À vérifier'}
                    </span>
                    <span className="user-sessions">
                      {user.sessions}
                      <span> session{user.sessions !== 1 ? 's' : ''}</span>
                    </span>
                    <Button
                      className="admin-user-action"
                      onClick={() => setEditing(user)}
                      aria-label={`Gérer ${user.email}`}
                    >
                      <Settings2 size={14} />
                      <span>Gérer</span>
                    </Button>
                  </article>
                ))}
              </div>
            )}
            <div className="table-footer">
              <span>
                Page {page} sur {Math.max(1, Math.ceil(query.data.total / query.data.pageSize))}
              </span>
              <div className="pagination">
                <Button
                  iconOnly
                  aria-label="Utilisateurs précédents"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={16} />
                </Button>
                <Button
                  iconOnly
                  aria-label="Utilisateurs suivants"
                  disabled={page * query.data.pageSize >= query.data.total}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={16} />
                </Button>
              </div>
            </div>
          </>
        ) : null}
      </ContentTransition>
      {shownEditing && (
        <UserEditor
          user={shownEditing}
          self={shownEditing.id === userId}
          open={editing !== null}
          close={() => setEditing(null)}
        />
      )}
    </>
  );
}
function UserEditor({
  user,
  self,
  open,
  close,
}: {
  user: AdminUser;
  self: boolean;
  open: boolean;
  close: () => void;
}) {
  const [role, setRole] = useState(user.role);
  const [disabled, setDisabled] = useState(user.disabled);
  const action = useAdminAction(successSchema, close);
  return (
    <Modal
      open={open}
      onOpenChange={(open) => {
        if (!open && !action.isPending) close();
      }}
      title="Gérer l’utilisateur"
      description={user.email}
      className="admin-dialog"
    >
      {needsStatusScreen(action.error) ? (
        <StatusPanel
          compact
          error={action.error}
          retryLabel="Reprendre le formulaire"
          onRetry={() => action.reset()}
        />
      ) : (
        <form
          className="admin-dialog-body"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            action.mutate({ path: `/users/${user.id}`, method: 'PATCH', body: { role, disabled } });
          }}
        >
          <dl className="admin-user-details">
            <div>
              <dt>Inscription</dt>
              <dd>{accountDate(user.createdAt)}</dd>
            </div>
            <div>
              <dt>Statut</dt>
              <dd>{user.disabled ? 'Suspendu' : user.verified ? 'Actif' : 'À vérifier'}</dd>
            </div>
            <div>
              <dt>Sessions</dt>
              <dd>{user.sessions}</dd>
            </div>
          </dl>
          <fieldset disabled={action.isPending || self}>
            <div className="admin-field">
              <span>Rôle</span>
              <Select
                disabled={self || action.isPending}
                label="Rôle de l’utilisateur"
                value={role}
                onChange={(value) => setRole(value as AdminUser['role'])}
                options={[
                  { value: 'user', label: 'Utilisateur' },
                  { value: 'admin', label: 'Administrateur' },
                ]}
              />
            </div>
            <label className="schedule-toggle">
              <input
                type="checkbox"
                checked={disabled}
                onChange={(event) => setDisabled(event.target.checked)}
              />
              <span>
                <strong>Suspendre l’accès</strong>
                <small>Empêche la connexion jusqu’à la réactivation du compte.</small>
              </span>
            </label>
          </fieldset>
          <p className="admin-callout">
            {self
              ? 'Votre propre accès administrateur est protégé.'
              : 'Un changement de rôle ou de statut déconnecte les sessions existantes.'}
          </p>
          <Button
            disabled={action.isPending || !user.sessions}
            onClick={() => action.mutate({ path: `/users/${user.id}/revoke-sessions` })}
          >
            Déconnecter toutes les sessions ({user.sessions})
          </Button>
          <FieldFeedback
            id="user-feedback"
            message={action.error?.message ?? ''}
            tone={action.error ? 'error' : 'hint'}
            reserve={feedbackReserve}
          />
          <div className="admin-form-actions">
            <Button onClick={close} disabled={action.isPending}>
              Fermer
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={
                self || action.isPending || (role === user.role && disabled === user.disabled)
              }
            >
              {action.isPending ? 'Enregistrement…' : 'Enregistrer'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
