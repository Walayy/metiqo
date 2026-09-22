import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { useId, useDeferredValue, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Globe2, RefreshCw, Search, X } from 'lucide-react';
import type { League } from '@/domain/schemas';
import { normalize, regionLabel } from '@/lib/format';
import { Logo } from '@/components/ui/logo';
import { Modal } from '@/components/ui/modal';
import { Spinner } from '@/components/ui/spinner';
import { StatusPanel } from '@/features/status/status-panel';
import './league-filters.css';

const shortcuts = ['lck', 'lpl', 'lec', 'lfl', 'cblol-brazil'];

interface RefreshProps {
  onRefresh: () => void;
  refreshing: boolean;
  mobile?: boolean;
}

export function RefreshValues({ onRefresh, refreshing, mobile = false }: RefreshProps) {
  return (
    <button
      type="button"
      className={`values-refresh values-refresh--${mobile ? 'mobile' : 'desktop'}`}
      onClick={onRefresh}
      disabled={refreshing}
      aria-label={refreshing ? 'Actualisation en cours' : 'Actualiser les données'}
      title={refreshing ? 'Actualisation en cours' : 'Actualiser les données'}
    >
      <RefreshCw size={16} className={refreshing ? 'is-spinning' : undefined} />
      <span>Actualiser</span>
    </button>
  );
}

interface Props extends RefreshProps {
  leagues: League[];
  selectedLeague: string;
  onSelect: (id: string) => void;
  loading: boolean;
  error: Error | null;
  context?: 'values' | 'matches';
  matchCounts?: Record<string, number>;
}

export function LeagueFilters({
  leagues,
  selectedLeague,
  onSelect,
  loading,
  error,
  onRefresh,
  refreshing,
  context = 'values',
  matchCounts,
}: Props) {
  const selectionId = useId();
  const [open, setOpen] = useState(false);
  const rail = useRef<HTMLDivElement>(null);
  const quickLeagues = useMemo(() => {
    const pinned =
      context === 'matches'
        ? leagues
            .filter((l) => (matchCounts?.[l.id] ?? 0) > 0)
            .sort(
              (a, b) =>
                (matchCounts?.[b.id] ?? 0) - (matchCounts?.[a.id] ?? 0) ||
                a.name.localeCompare(b.name, 'fr'),
            )
            .slice(0, 5)
        : shortcuts
            .map((slug) => leagues.find((league) => league.slug === slug))
            .filter((league) => !!league);
    const selected = leagues.find((league) => league.id === selectedLeague);
    return selected && !pinned.some((league) => league.id === selected.id)
      ? [...pinned, selected]
      : pinned;
  }, [leagues, selectedLeague, context, matchCounts]);

  useLayoutEffect(() => {
    const container = rail.current;
    if (!container) return;
    // Move only the horizontal rail: changing a league must not scroll the page.
    const revealSelection = () => {
      const selected = container.querySelector<HTMLButtonElement>('[aria-pressed="true"]');
      if (!selected) return;
      const bounds = container.getBoundingClientRect();
      const button = selected.getBoundingClientRect();
      if (button.left < bounds.left) container.scrollLeft += button.left - bounds.left;
      else if (button.right > bounds.right) container.scrollLeft += button.right - bounds.right;
    };
    revealSelection();
    const observer = new ResizeObserver(revealSelection);
    observer.observe(container);
    return () => observer.disconnect();
  }, [selectedLeague, quickLeagues]);

  return (
    <>
      <div className="league-filter-bar">
        <div className="league-filter-rail" ref={rail} role="group" aria-label="Filtrer par ligue">
          <button
            type="button"
            className="league-chip"
            aria-pressed={selectedLeague === 'all'}
            aria-label="Toutes les ligues"
            onClick={() => onSelect('all')}
          >
            {selectedLeague === 'all' && <SelectionIndicator id={selectionId} />}
            <Globe2 size={17} aria-hidden="true" />
            <span>Toutes</span>
          </button>
          {quickLeagues.map((league) => (
            <button
              type="button"
              key={league.id}
              className="league-chip"
              aria-pressed={selectedLeague === league.id}
              aria-label={league.name}
              title={league.name}
              onClick={() => onSelect(league.id)}
            >
              {selectedLeague === league.id && <SelectionIndicator id={selectionId} />}
              <Logo src={league.image} name={league.name} league />
              <span>{league.name}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          className="league-picker-trigger"
          aria-label="Choisir parmi toutes les ligues"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          Plus <ChevronDown size={16} aria-hidden="true" />
        </button>
        <RefreshValues onRefresh={onRefresh} refreshing={refreshing} />
      </div>
      {open && (
        <LeaguePicker
          leagues={leagues}
          selectedLeague={selectedLeague}
          onSelect={(id) => {
            onSelect(id);
            setOpen(false);
          }}
          onClose={() => setOpen(false)}
          loading={loading}
          error={error}
          onRefresh={onRefresh}
          refreshing={refreshing}
          context={context}
          matchCounts={matchCounts}
        />
      )}
    </>
  );
}

function LeaguePicker({
  leagues,
  selectedLeague,
  onSelect,
  loading,
  error,
  onRefresh,
  refreshing,
  onClose,
  context = 'values',
  matchCounts,
}: Props & { onClose: () => void }) {
  const [search, setSearch] = useState('');
  const searchField = useRef<HTMLInputElement>(null);
  const term = normalize(useDeferredValue(search));
  const matches = leagues.filter((league) =>
    normalize(`${league.name} ${league.region} ${regionLabel(league.region)}`).includes(term),
  );
  const ordered = matches.toSorted((a, b) => a.name.localeCompare(b.name, 'fr'));
  const available = ordered.filter((l) => (matchCounts?.[l.id] ?? 0) > 0);
  const remaining = ordered.filter((l) => !(matchCounts?.[l.id] ?? 0));
  const sections =
    context === 'matches'
      ? [
          { label: 'Dans cette journée', leagues: available },
          ...[...new Set(remaining.map((l) => l.region))]
            .sort((a, b) => regionLabel(a).localeCompare(regionLabel(b), 'fr'))
            .map((region) => ({
              label: regionLabel(region),
              leagues: remaining.filter((l) => l.region === region),
            })),
        ].filter((section) => section.leagues.length)
      : [{ label: '', leagues: matches }];
  return (
    <Modal
      open
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title="Choisir une ligue"
      description={
        context === 'matches'
          ? 'Les compétitions du jour, puis le répertoire par région.'
          : 'Retrouvez les values de votre compétition.'
      }
      className="league-picker"
    >
      {loading ? (
        <div className="league-picker-state" aria-busy="true">
          <Spinner label="Chargement des ligues" />
        </div>
      ) : error ? (
        <div className="league-picker-list">
          <StatusPanel error={error} onRetry={onRefresh} busy={refreshing} compact />
        </div>
      ) : (
        <>
          <div className="league-picker-search">
            <label className="search-field">
              <Search size={18} aria-hidden="true" />
              <input
                ref={searchField}
                aria-label="Rechercher une ligue ou une région"
                placeholder="Une ligue, une région…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                type="search"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            {search && (
              <button
                type="button"
                aria-label="Effacer la recherche de ligue"
                onClick={() => {
                  setSearch('');
                  searchField.current?.focus();
                }}
              >
                <X size={17} />
              </button>
            )}
          </div>
          <div className="league-picker-list" role="group" aria-label="Ligues disponibles">
            <button
              type="button"
              className="league-picker-option"
              aria-pressed={selectedLeague === 'all'}
              onClick={() => onSelect('all')}
            >
              <span className="league-picker-all">
                <Globe2 size={22} />
              </span>
              <span>
                <strong>Toutes les ligues</strong>
                <small>
                  {context === 'matches'
                    ? 'Voir tous les matchs de la journée'
                    : 'Voir toutes les values'}
                </small>
              </span>
              {selectedLeague === 'all' && <Check size={18} aria-hidden="true" />}
            </button>
            <p className="league-picker-count" role="status">
              {matches.length} {matches.length > 1 ? 'ligues' : 'ligue'}
              {term ? (matches.length > 1 ? ' trouvées' : ' trouvée') : ' disponibles'}
            </p>
            {sections.map((section) => (
              <section key={section.label} aria-label={section.label || 'Toutes les compétitions'}>
                {section.label && <h3 className="league-picker-section">{section.label}</h3>}
                {section.leagues.map((league) => (
                  <button
                    type="button"
                    className="league-picker-option"
                    key={league.id}
                    aria-pressed={selectedLeague === league.id}
                    onClick={() => onSelect(league.id)}
                  >
                    <Logo src={league.image} name={league.name} league />
                    <span>
                      <strong>{league.name}</strong>
                      <small>
                        {regionLabel(league.region)}
                        {context === 'matches' &&
                          ` · ${matchCounts?.[league.id] ?? 0} match${(matchCounts?.[league.id] ?? 0) > 1 ? 's' : ''} ce jour`}
                      </small>
                    </span>
                    {selectedLeague === league.id && <Check size={18} aria-hidden="true" />}
                  </button>
                ))}
              </section>
            ))}
            {matches.length === 0 && (
              <p className="league-picker-empty">
                Aucune ligue trouvée. Essayez un autre nom ou une région.
              </p>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
