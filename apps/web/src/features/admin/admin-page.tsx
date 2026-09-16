import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { ContentTransition } from '@/components/ui/content-transition';
import { useDeferredValue, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CalendarClock,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  History,
  Pause,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Terminal,
  Users,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
import { FieldFeedback } from '@/components/ui/field-feedback';
import { accountDate, scheduledDate } from '@/lib/format';
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
          <>
            <div className="admin-section-heading">
              <div>
                <h2>Scripts de collecte</h2>
                <p>Planifiez les mises à jour ou lancez une collecte à la demande.</p>
              </div>
              <span className="skeleton skeleton-medium" />
            </div>
            <div className="admin-action-feedback" />
            <div className="script-grid">
              {[0, 1, 2].map((id) => (
                <div className="script-card" key={id} aria-hidden="true">
                  <div className="script-top">
                    <span className="script-icon skeleton" />
                    <span className="skeleton skeleton-short" />
                  </div>
                  <h3>
                    <span className="skeleton skeleton-medium" />
                  </h3>
                  <p className="script-description">
                    <span className="skeleton skeleton-medium" />
                  </p>
                  <div className="script-schedule">
                    <CalendarClock size={17} />
                    <div>
                      <strong className="skeleton skeleton-copy">Tous les jours</strong>
                      <span className="skeleton skeleton-copy">Heure de Paris</span>
                    </div>
                  </div>
                  <div className="script-next">
                    <span>PROCHAINE EXÉCUTION</span>
                    <strong className="skeleton skeleton-copy">00 septembre à 00:00</strong>
                    <small>
                      <span className="skeleton skeleton-medium" />
                    </small>
                  </div>
                  <div className="script-last">
                    <span className="skeleton skeleton-medium" />
                  </div>
                  <div className="script-actions">
                    <span className="skeleton skeleton-admin-action" />
                    <span className="skeleton skeleton-admin-action" />
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </ContentTransition>
  );
}
export function AdminPage({ userId, section }: { userId: string; section: 'scripts' | 'users' }) {
  return (
    <div className="admin-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            ADMINISTRATION
          </div>
          <h1>{section === 'users' ? 'Utilisateurs' : 'Scripts & planifications'}</h1>
          <p>
            {section === 'users'
              ? 'Gérez les accès et les sessions de vos utilisateurs.'
              : 'Pilotez les collectes et leurs prochaines exécutions.'}
          </p>
        </div>
        <span className="admin-badge">
          <ShieldCheck size={16} />
          Administrateur
        </span>
      </div>
      {section === 'scripts' ? <Scripts /> : <UserList userId={userId} />}
    </div>
  );
}

function Scripts() {
  const query = useQuery(scriptsQuery);
  const loading = useMinimumLoading(query.isPending, 'scripts');
  const client = useQueryClient();
  const [editing, setEditing] = useState<Script | null>(null);
  const [history, setHistory] = useState<Script | null>(null);
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
  const historyScript = items.find((item) => item.id === history?.id) ?? history;
  return (
    <ContentTransition id="scripts-ready">
      <div className="admin-section-heading">
        <div>
          <h2>Scripts de collecte</h2>
          <p>Planifiez les mises à jour ou lancez une collecte à la demande.</p>
        </div>
        <span className={clsx('worker-status', worker.online && 'is-online')}>
          <span />
          {worker.online ? 'Worker connecté' : 'Worker indisponible'}
        </span>
      </div>
      {!worker.online && (
        <p className="admin-callout" role="status">
          Les planifications restent enregistrées. Les exécutions reprendront au retour du worker.
          {worker.lastSeenAt && ` Dernier contact : ${scheduledDate(worker.lastSeenAt)}.`}
        </p>
      )}
      <div className="admin-action-feedback" role="status">
        {action.error?.message ??
          (action.isSuccess ? 'Lancement demandé. Le worker prendra en charge la collecte.' : '')}
      </div>
      {!items.length ? (
        <div className="admin-empty">Aucun script configuré.</div>
      ) : (
        <div className="script-grid">
          {items.map((script) => {
            const last = script.runs[0];
            return (
              <article className="script-card" key={script.id} aria-label={script.name}>
                <div className="script-top">
                  <span className="script-icon">
                    <Terminal size={21} />
                  </span>
                  <span className={clsx('admin-status', script.enabled && 'is-positive')}>
                    {script.enabled ? <Check size={13} /> : <Pause size={13} />}
                    {script.enabled ? 'Planifié' : 'En pause'}
                  </span>
                </div>
                <h3>{script.name}</h3>
                <p className="script-description">{script.description}</p>
                <div className="script-schedule">
                  <CalendarClock size={17} />
                  <div>
                    <strong>{scheduleLabel(script.cron)}</strong>
                    <span>
                      {script.timezone === 'Europe/Paris' ? 'Heure de Paris' : 'Heure UTC'}
                    </span>
                  </div>
                </div>
                <div className="script-next">
                  <span>PROCHAINE EXÉCUTION</span>
                  <strong>
                    {script.nextRunAt
                      ? scheduledDate(script.nextRunAt, script.timezone)
                      : 'Planification en pause'}
                  </strong>
                  <small>
                    {!script.available
                      ? 'En attente du worker'
                      : script.activeRun
                        ? `${statuses[script.activeRun.status]} · ${script.activeRun.trigger === 'manual' ? 'lancement manuel' : 'planification'}`
                        : 'Prise en charge automatique par le worker'}
                  </small>
                </div>
                <div className="script-last">
                  <Clock3 size={14} />
                  <span>
                    {last ? (
                      <>
                        {statuses[last.status]} ·{' '}
                        {scheduledDate(last.startedAt ?? last.requestedAt, script.timezone)}
                      </>
                    ) : (
                      'Aucune exécution depuis l’activation'
                    )}
                  </span>
                </div>
                <div className="script-actions">
                  <Button
                    onClick={() => setEditing(script)}
                    aria-label={`Planifier ${script.name}`}
                  >
                    <Settings2 size={15} />
                    Planifier
                  </Button>
                  <Button
                    variant="primary"
                    disabled={!script.available || !!script.activeRun || action.isPending}
                    onClick={() => action.mutate({ path: `/scripts/${script.id}/run` })}
                    aria-label={`Lancer ${script.name}`}
                  >
                    <Play size={14} />
                    {script.activeRun ? statuses[script.activeRun.status] : 'Lancer'}
                  </Button>
                  <Button
                    iconOnly
                    variant="ghost"
                    onClick={() => setHistory(script)}
                    aria-label={`Historique de ${script.name}`}
                  >
                    <History size={17} />
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      <p className="admin-footnote">
        <Clock3 size={14} />
        Une planification en pause autorise toujours le lancement manuel. Une collecte en cours va
        jusqu’à son terme.
      </p>
      {editing && <ScheduleEditor script={editing} close={() => setEditing(null)} />}
      {historyScript && (
        <Modal
          open
          onOpenChange={(open) => {
            if (!open) setHistory(null);
          }}
          title="Historique des exécutions"
          description={historyScript.name}
          className="admin-dialog"
        >
          <div className="admin-dialog-body">
            <p className="admin-muted">Les 8 dernières exécutions depuis l’espace Admin.</p>
            {!historyScript.runs.length ? (
              <div className="admin-empty">Aucune exécution pour le moment.</div>
            ) : (
              <ol className="run-list">
                {historyScript.runs.map((run) => (
                  <li key={run.id}>
                    <div>
                      <span
                        className={clsx(
                          'admin-status',
                          run.status === 'succeeded' && 'is-positive',
                          ['failed', 'interrupted'].includes(run.status) && 'is-error',
                        )}
                      >
                        {statuses[run.status]}
                      </span>
                      <span>{run.trigger === 'manual' ? 'Manuelle' : 'Planifiée'}</span>
                    </div>
                    <strong>{scheduledDate(run.requestedAt, historyScript.timezone)}</strong>
                    <p>
                      {run.startedAt
                        ? `Début : ${scheduledDate(run.startedAt, historyScript.timezone)}`
                        : 'En attente de prise en charge'}
                      {run.finishedAt &&
                        ` · Fin : ${scheduledDate(run.finishedAt, historyScript.timezone)}`}
                    </p>
                    {run.error && <p className="admin-error">{run.error}</p>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Modal>
      )}
    </ContentTransition>
  );
}

function ScheduleEditor({ script, close }: { script: Script; close: () => void }) {
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
      open
      onOpenChange={(open) => {
        if (!open && !action.isPending) close();
      }}
      title="Planifier le script"
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
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>
              <strong>Exécution automatique</strong>
              <small>
                {enabled
                  ? 'Le script suivra la fréquence ci-dessous.'
                  : 'En pause. Vous pourrez toujours le lancer manuellement.'}
              </small>
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
                  { value: 'hours', label: 'Toutes les X heures' },
                  { value: 'daily', label: 'Chaque jour' },
                  { value: 'weekly', label: 'Chaque semaine' },
                  { value: 'custom', label: 'Cron personnalisé' },
                ]}
              />
            </div>
            <div className="schedule-fields">
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
            message={
              error ??
              (pendingPreview
                ? 'Vérification de la planification…'
                : 'Les horaires tiennent compte du fuseau sélectionné.')
            }
            tone={error ? 'error' : 'hint'}
            reserve={feedbackReserve}
          />
          <div className="schedule-preview" aria-busy={pendingPreview}>
            <strong>
              <CalendarClock size={16} />
              {enabled ? 'Les 3 prochaines exécutions' : 'Aperçu si vous réactivez le script'}
            </strong>
            <ol>
              {[0, 1, 2].map((index) => (
                <li key={index}>
                  <span>{index + 1}</span>
                  {!pendingPreview && preview.data
                    ? preview.data.upcoming[index]
                      ? scheduledDate(preview.data.upcoming[index], timezone)
                      : '—'
                    : '—'}
                </li>
              ))}
            </ol>
            <code>{cron || 'Horaire à compléter'}</code>
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
  const query = useQuery(usersQuery(deferred, page));
  const loading = useMinimumLoading(query.isFetching, JSON.stringify([deferred, page]));
  return (
    <>
      <div className="admin-section-heading">
        <div>
          <h2>
            Utilisateurs {query.data && <span className="count-pill">{query.data.total}</span>}
          </h2>
          <p>Gérez les accès et les sessions des comptes inscrits.</p>
        </div>
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
                    <Button onClick={() => setEditing(user)} aria-label={`Gérer ${user.email}`}>
                      <Settings2 size={14} />
                      Gérer
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
      {editing && (
        <UserEditor user={editing} self={editing.id === userId} close={() => setEditing(null)} />
      )}
    </>
  );
}

function UserEditor({ user, self, close }: { user: AdminUser; self: boolean; close: () => void }) {
  const [role, setRole] = useState(user.role);
  const [disabled, setDisabled] = useState(user.disabled);
  const action = useAdminAction(successSchema, close);
  return (
    <Modal
      open
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
