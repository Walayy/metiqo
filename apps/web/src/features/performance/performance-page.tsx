import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { ContentTransition } from '@/components/ui/content-transition';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { motion, useReducedMotion } from 'motion/react';
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Popover } from 'radix-ui';
import {
  ChartNoAxesCombined,
  ChevronDown,
  RotateCcw,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import type { Catalog } from '@/domain/schemas';
import { expectedValue, marketLabel } from '@/domain/value';
import { compactEuro, dateTime, decimal, normalize, shortDate, signedDecimal } from '@/lib/format';
import { performanceQuery } from '@/lib/api';
import { HttpError } from '@/lib/http-error';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { FieldFeedback } from '@/components/ui/field-feedback';
import { StatusPanel } from '@/features/status/status-panel';
import { simulate } from './simulation';
import type { SimulationFilters } from './simulation';
import './performance.css';

const defaults: SimulationFilters = {
  minValue: 0,
  league: 'all',
  teams: [],
  market: 'all',
  days: 30,
};
const feedback = ['Mise comprise entre 0,01 et 100 000 €.', 'Seuil compris entre 0 et 100 %.'];
export function PerformancePage({
  catalog,
  loading: catalogLoading,
}: {
  catalog: Catalog;
  loading: boolean;
}) {
  const query = useQuery(performanceQuery);
  const records = query.data?.items ?? [];
  const dataPending = query.isPending || catalogLoading;
  const periodId = useId();
  const [filters, setFilters] = useState<SimulationFilters>(defaults);
  const [stake, setStake] = useState(10);
  const [stakeInput, setStakeInput] = useState('10');
  const [thresholdInput, setThresholdInput] = useState('0');
  const [submitted, setSubmitted] = useState(false);
  const [teamSearch, setTeamSearch] = useState('');
  const formId = useId();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);
  const parsedStake = Number(stakeInput.replace(',', '.'));
  const parsedThreshold = Number(thresholdInput.replace(',', '.'));
  const stakeError =
    !stakeInput.trim() ||
    !Number.isFinite(parsedStake) ||
    parsedStake < 0.01 ||
    parsedStake > 100000
      ? feedback[0]!
      : '';
  const thresholdError =
    !thresholdInput.trim() ||
    !Number.isFinite(parsedThreshold) ||
    parsedThreshold < 0 ||
    parsedThreshold > 100
      ? feedback[1]!
      : '';
  const loading = useMinimumLoading(dataPending, JSON.stringify([filters, stake]));
  const simulation = simulate(records, filters, stake, now);
  const availableTeams = catalog.teams.filter((team) => records.some((r) => r.pickId === team.id));
  const invalid =
    !loading &&
    records.some(
      (r) =>
        !catalog.leagues.some((l) => l.id === r.leagueId) ||
        [r.homeId, r.awayId, r.pickId].some((id) => !catalog.teams.some((t) => t.id === id)),
    );
  function reset() {
    setFilters(defaults);
    setStake(10);
    setStakeInput('10');
    setThresholdInput('0');
    setSubmitted(false);
    setTeamSearch('');
  }
  if (query.error || invalid)
    return (
      <StatusPanel
        error={query.error ?? new HttpError(0, { kind: 'invalid-response' })}
        onRetry={() => void query.refetch()}
        busy={query.isFetching}
      />
    );
  return (
    <div className="performance-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            VOTRE SIMULATION
          </div>
          <h1>Et si vous aviez suivi les values ?</h1>
          <p>Une mise constante. Vos critères. L’évolution du résultat dans le temps.</p>
        </div>
      </div>
      <section className="simulation-controls" aria-label="Paramètres de la simulation">
        <form
          className="simulation-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(true);
            if (stakeError || thresholdError) return;
            setStake(Math.round(parsedStake * 100) / 100);
            setFilters({ ...filters, minValue: parsedThreshold });
          }}
        >
          <div className="simulation-field">
            <label htmlFor={`${formId}-stake`}>
              Mise par value <span>€</span>
            </label>
            <input
              id={`${formId}-stake`}
              type="text"
              inputMode="decimal"
              value={stakeInput}
              onChange={(event) => setStakeInput(event.target.value)}
              aria-invalid={submitted && !!stakeError}
              aria-describedby={`${formId}-stake-feedback`}
            />
            <FieldFeedback
              id={`${formId}-stake-feedback`}
              message={submitted ? stakeError : ''}
              tone="error"
              reserve={[feedback[0]!]}
            />
          </div>
          <div className="simulation-field">
            <label htmlFor={`${formId}-value`}>
              Value supérieure à <span>%</span>
            </label>
            <input
              id={`${formId}-value`}
              type="text"
              inputMode="decimal"
              value={thresholdInput}
              onChange={(event) => setThresholdInput(event.target.value)}
              aria-invalid={submitted && !!thresholdError}
              aria-describedby={`${formId}-value-feedback`}
            />
            <FieldFeedback
              id={`${formId}-value-feedback`}
              message={submitted ? thresholdError : ''}
              tone="error"
              reserve={[feedback[1]!]}
            />
          </div>
          <Button type="submit" variant="primary">
            <SlidersHorizontal size={15} />
            Appliquer
          </Button>
        </form>
        <div className="simulation-filters">
          <Select
            label="Ligue simulée"
            value={filters.league}
            onChange={(league) => setFilters({ ...filters, league })}
            options={[
              { value: 'all', label: 'Toutes les ligues' },
              ...catalog.leagues
                .filter((l) => records.some((r) => r.leagueId === l.id))
                .map((l) => ({ value: l.id, label: l.name })),
            ]}
          />
          <Popover.Root>
            <Popover.Trigger asChild>
              <Button className="team-filter-trigger">
                {filters.teams.length
                  ? `${filters.teams.length} équipe${filters.teams.length > 1 ? 's' : ''} sélectionnée${filters.teams.length > 1 ? 's' : ''}`
                  : 'Toutes les équipes'}
                <ChevronDown size={15} />
              </Button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                className="team-filter-popover"
                sideOffset={6}
                collisionPadding={12}
                aria-label="Équipes sur lesquelles miser"
              >
                <h3>Équipes sélectionnées</h3>
                <p>La value doit porter sur l’une de ces équipes.</p>
                <label className="search-field">
                  <Search size={15} />
                  <input
                    value={teamSearch}
                    onChange={(e) => setTeamSearch(e.target.value)}
                    placeholder="Rechercher une équipe"
                    aria-label="Rechercher une équipe à simuler"
                  />
                </label>
                <div className="team-filter-options">
                  {availableTeams
                    .filter((t) => normalize(`${t.name} ${t.code}`).includes(normalize(teamSearch)))
                    .map((team) => (
                      <label key={team.id}>
                        <input
                          type="checkbox"
                          checked={filters.teams.includes(team.id)}
                          onChange={(e) =>
                            setFilters({
                              ...filters,
                              teams: e.target.checked
                                ? [...filters.teams, team.id]
                                : filters.teams.filter((id) => id !== team.id),
                            })
                          }
                        />
                        <span>{team.name}</span>
                        <small>{team.code}</small>
                      </label>
                    ))}
                  {!availableTeams.some((t) =>
                    normalize(`${t.name} ${t.code}`).includes(normalize(teamSearch)),
                  ) && <p>Aucune équipe trouvée.</p>}
                </div>
                <Button
                  onClick={() => setFilters({ ...filters, teams: [] })}
                  disabled={!filters.teams.length}
                >
                  Toutes les équipes
                </Button>
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
          <Select
            label="Marché simulé"
            value={filters.market}
            onChange={(market) => setFilters({ ...filters, market })}
            options={[
              { value: 'all', label: 'Tous les marchés' },
              { value: 'winner', label: 'Vainqueur du match' },
              { value: 'map1', label: 'Vainqueur · carte 1' },
            ]}
          />
          <Button variant="ghost" onClick={reset}>
            <RotateCcw size={14} />
            Réinitialiser
          </Button>
        </div>
      </section>
      <section
        className="simulation-chart-card"
        aria-label="Évolution de la simulation"
        aria-busy={loading}
      >
        <div className="simulation-chart-heading">
          <div>
            <span>Gain net simulé</span>
            <strong className={simulation.profit < 0 ? 'is-loss' : ''}>
              {loading ? (
                <span className="skeleton simulation-profit-skeleton" />
              ) : (
                <ContentTransition id={JSON.stringify([filters, stake])}>
                  {signedDecimal(simulation.profit)} €
                </ContentTransition>
              )}
            </strong>
            <p>
              {decimal(stake)} € par value · value &gt; {decimal(filters.minValue, 1)} %
            </p>
          </div>
          <div className="simulation-periods" role="group" aria-label="Période de règlement">
            {[
              { value: 7, label: '7 j' },
              { value: 30, label: '30 j' },
              { value: 90, label: '90 j' },
              { value: 0, label: 'Tout' },
            ].map((period) => (
              <button
                key={period.value}
                type="button"
                aria-pressed={filters.days === period.value}
                disabled={dataPending}
                onClick={() => setFilters({ ...filters, days: period.value })}
              >
                {filters.days === period.value && <SelectionIndicator id={periodId} />}
                <span>{period.label}</span>
              </button>
            ))}
          </div>
        </div>
        <ContentTransition id={loading ? 'loading' : 'ready'}>
          {loading ? (
            <ProfitChartSkeleton />
          ) : simulation.rows.length ? (
            <ProfitChart
              key={JSON.stringify([filters, stake])}
              simulation={simulation}
              catalog={catalog}
            />
          ) : (
            <div className="simulation-empty">
              <ChartNoAxesCombined size={32} />
              <h2>
                {records.length ? 'Aucune value avec ces critères.' : 'L’historique se construit.'}
              </h2>
              <p>
                {records.length
                  ? 'Élargissez la période, les équipes ou le seuil de value.'
                  : 'La courbe apparaîtra lorsque des values et leurs résultats seront disponibles.'}
              </p>
              {records.length > 0 && <Button onClick={reset}>Réinitialiser les critères</Button>}
            </div>
          )}
        </ContentTransition>
        <dl className="simulation-summary">
          <div>
            <dt>Rendement simulé</dt>
            <dd>
              {loading ? (
                <span className="skeleton simulation-stat-skeleton" />
              ) : !simulation.count ? (
                '—'
              ) : (
                `${signedDecimal(simulation.roi, 1)} %`
              )}
            </dd>
          </div>
          <div>
            <dt>Total misé</dt>
            <dd>
              {loading ? (
                <span className="skeleton simulation-stat-skeleton" />
              ) : (
                `${decimal(simulation.invested)} €`
              )}
            </dd>
          </div>
          <div>
            <dt>Values gagnantes</dt>
            <dd>
              {loading ? (
                <span className="skeleton simulation-stat-skeleton" />
              ) : (
                `${simulation.wins} / ${simulation.count}`
              )}
            </dd>
          </div>
        </dl>
      </section>
      <p className="simulation-note">
        Simulation historique, sans pari réel. Une mise fixe sur chaque marché retenu, à la cote et
        à la probabilité enregistrées avant le match. Gain net après déduction des mises ; les
        annulations sont remboursées et exclues du rendement. Les pertes sont possibles, les
        performances passées ne garantissent pas les suivantes.
      </p>
      {!loading && simulation.rows.length > 0 && (
        <details className="simulation-ledger">
          <summary>
            Détail des {simulation.rows.length} values <ChevronDown size={16} />
          </summary>
          <div className="ledger-list">
            {simulation.rows
              .slice()
              .reverse()
              .map(({ record, profit }) => (
                <article key={record.id}>
                  <div>
                    <strong>{catalog.teams.find((t) => t.id === record.pickId)?.name}</strong>
                    <span>
                      {catalog.teams.find((t) => t.id === record.homeId)?.code} –{' '}
                      {catalog.teams.find((t) => t.id === record.awayId)?.code} ·{' '}
                      {marketLabel(record.market)}
                    </span>
                    <small>{dateTime(record.settledAt)}</small>
                  </div>
                  <dl>
                    <div>
                      <dt>Cote retenue</dt>
                      <dd>{decimal(record.odds)}</dd>
                    </div>
                    <div>
                      <dt>Value initiale</dt>
                      <dd>{signedDecimal(expectedValue(record.probability, record.odds), 1)} %</dd>
                    </div>
                    <div>
                      <dt>
                        {record.result === 'void'
                          ? 'Remboursée'
                          : record.result === 'won'
                            ? 'Gagnée'
                            : 'Perdue'}
                      </dt>
                      <dd className={profit < 0 ? 'is-loss' : 'is-profit'}>
                        {signedDecimal(profit)} €
                      </dd>
                    </div>
                  </dl>
                </article>
              ))}
          </div>
        </details>
      )}
    </div>
  );
}
function ProfitChart({
  simulation,
  catalog,
}: {
  simulation: ReturnType<typeof simulate>;
  catalog: Catalog;
}) {
  const id = useId();
  const reduced = useReducedMotion();
  const cursorTransition = reduced
    ? { duration: 0 }
    : { type: 'spring' as const, stiffness: 440, damping: 40 };
  const [container, width] = useChartWidth();
  const points = [
    { at: simulation.rows[0]!.record.observedAt, value: 0 },
    ...simulation.rows.map((row) => ({ at: row.record.settledAt, value: row.cumulative })),
  ];
  const [cursor, setCursor] = useState(points.length - 1);
  const values = points.map((p) => p.value);
  const min = Math.min(0, ...values),
    max = Math.max(0, ...values);
  const padding = Math.max(0.01, (max - min) * 0.12);
  const low = min - padding,
    high = max + padding;
  const first = Date.parse(points[0]!.at),
    last = Date.parse(points.at(-1)!.at);
  const endX = width - 16;
  const x = (i: number) =>
    64 + ((Date.parse(points[i]!.at) - first) / Math.max(1, last - first)) * (endX - 64);
  const y = (v: number) => 18 + ((high - v) / (high - low)) * 224;
  const line = points.map((point, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(point.value)}`).join(' ');
  const current = Math.min(cursor, points.length - 1);
  const point = points[current]!;
  const row = current ? simulation.rows[current - 1] : null;
  return (
    <div className="profit-chart" ref={container}>
      <svg
        viewBox={`0 0 ${width} 278`}
        role="img"
        aria-labelledby={`${id}-title ${id}-desc`}
        onPointerMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const target = ((event.clientX - bounds.left) / bounds.width) * width;
          let nearest = 0;
          for (let i = 1; i < points.length; i++)
            if (Math.abs(x(i) - target) < Math.abs(x(nearest) - target)) nearest = i;
          setCursor(nearest);
        }}
      >
        <title id={`${id}-title`}>Évolution du gain net simulé</title>
        <desc id={`${id}-desc`}>
          De zéro à {decimal(simulation.profit)} euros pour {simulation.rows.length} values.
          Utilisez le curseur sous le graphique pour consulter chaque résultat.
        </desc>
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[high, (high + low) / 2, low].map((v, i) => (
          <g key={i}>
            <line
              x1="64"
              x2={endX}
              y1={y(v)}
              y2={y(v)}
              stroke="var(--border)"
              strokeDasharray="3 5"
            />
            <text x="52" y={y(v) + 4} textAnchor="end">
              {compactEuro(v)}
            </text>
          </g>
        ))}
        <motion.path
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.12 }}
          d={`${line} L ${x(points.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`}
          fill={`url(#${id}-fill)`}
        />
        <line x1="64" x2={endX} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" />
        <motion.path
          initial={reduced ? false : { pathLength: 0, opacity: 0.4 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
          d={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <motion.line
          initial={false}
          animate={{ x1: x(current), x2: x(current) }}
          transition={cursorTransition}
          y1="18"
          y2="242"
          stroke="var(--muted)"
          strokeDasharray="3 5"
        />
        <motion.circle
          initial={false}
          animate={{ cx: x(current), cy: y(point.value) }}
          transition={cursorTransition}
          r="12"
          fill="var(--accent)"
          fillOpacity="0.1"
        />
        <motion.circle
          initial={false}
          animate={{ cx: x(current), cy: y(point.value) }}
          transition={cursorTransition}
          r="5"
          fill="var(--accent)"
          stroke="var(--surface)"
          strokeWidth="2"
        />
        <text x="64" y="270">
          {shortDate(points[0]!.at)}
        </text>
        <text x={endX} y="270" textAnchor="end">
          {shortDate(points.at(-1)!.at)}
        </text>
      </svg>
      <label className="chart-scrubber">
        <span className="sr-only">Explorer les résultats de la simulation</span>
        <input
          type="range"
          min={0}
          max={points.length - 1}
          value={current}
          onChange={(event) => setCursor(Number(event.target.value))}
          aria-valuetext={`${dateTime(point.at)}, gain cumulé ${decimal(point.value)} euros`}
        />
      </label>
      <div className="chart-inspection" aria-live="off">
        <div>
          <strong>
            {row
              ? `${catalog.teams.find((t) => t.id === row.record.homeId)?.code} – ${catalog.teams.find((t) => t.id === row.record.awayId)?.code}`
              : 'Début de la simulation'}
          </strong>
          <span>
            {dateTime(point.at)}
            {row
              ? ` · ${row.record.result === 'won' ? 'Gagnée' : row.record.result === 'lost' ? 'Perdue' : 'Remboursée'}`
              : ''}
          </span>
        </div>
        <div>
          <strong>{signedDecimal(point.value)} €</strong>
          <span>gain cumulé</span>
        </div>
      </div>
    </div>
  );
}

function useChartWidth() {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(888);
  useLayoutEffect(() => {
    const node = container.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(240, entry.contentRect.width));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [container, width] as const;
}

function ProfitChartSkeleton() {
  const [container, width] = useChartWidth();
  return (
    <div
      className="profit-chart profit-chart-skeleton"
      ref={container}
      role="status"
      aria-label="Chargement de l’historique"
    >
      <svg viewBox={`0 0 ${width} 278`} aria-hidden="true">
        {[18, 130, 242].map((y) => (
          <g key={y}>
            <rect x="12" y={y - 4} width="40" height="8" rx="4" />
            <line x1="64" x2={width - 16} y1={y} y2={y} />
          </g>
        ))}
        <rect x="64" y="263" width="52" height="8" rx="4" />
        <rect x={width - 68} y="263" width="52" height="8" rx="4" />
      </svg>
      <div className="chart-scrubber chart-scrubber-skeleton" aria-hidden="true">
        <span className="skeleton" />
      </div>
      <div className="chart-inspection" aria-hidden="true">
        <div>
          <span className="skeleton skeleton-medium" />
          <span className="skeleton skeleton-medium" />
        </div>
        <div>
          <span className="skeleton skeleton-short" />
          <span className="skeleton skeleton-short" />
        </div>
      </div>
    </div>
  );
}
