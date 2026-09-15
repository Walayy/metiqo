import { lazy, Suspense, useDeferredValue, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { Dialog } from 'radix-ui';
import {
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Globe2,
  Menu,
  Moon,
  Radar,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sun,
  TrendingUp,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import type { Catalog } from '@/domain/schemas';
import { valueOf } from '@/domain/value';
import { percent, time } from '@/lib/format';
import { config } from '@/lib/config';
import { catalogQuery, opportunitiesQuery } from '@/lib/api';
import { useFavorites } from '@/hooks/use-favorites';
import { useTheme } from '@/hooks/use-theme';
import { Sidebar } from '@/components/layout/sidebar';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { InsightsSkeleton, ValuesSkeleton } from '@/components/ui/skeleton';
import { ValueRow } from '@/features/values/value-row';
import { FeaturedValue } from '@/features/values/featured-value';
import { defaultFilters } from '@/features/values/filter-state';
import { filterValues } from '@/features/values/filter';
const ValueDetail = lazy(() =>
  import('@/features/values/value-detail').then((module) => ({ default: module.ValueDetail })),
);
const FilterDialog = lazy(() =>
  import('@/features/values/filter-dialog').then((module) => ({ default: module.FilterDialog })),
);
const HelpDialog = lazy(() =>
  import('@/features/values/help-dialog').then((module) => ({ default: module.HelpDialog })),
);
const CatalogDialog = lazy(() =>
  import('@/features/catalog/catalog-dialog').then((module) => ({ default: module.CatalogDialog })),
);

const emptyCatalog: Catalog = { retrievedAt: '', source: '', leagues: [], teams: [] };
const pageSize = 6;
export function App() {
  const catalogResult = useQuery(catalogQuery);
  const result = useQuery(opportunitiesQuery);
  const catalog = catalogResult.data ?? emptyCatalog;
  const items = result.data?.items ?? [];
  const { favorites, toggle } = useFavorites();
  const { theme, toggleTheme } = useTheme();
  const [savedOnly, setSavedOnly] = useState(false);
  const [filters, setFilters] = useState(defaultFilters);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [sort, setSort] = useState('value');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panel, setPanel] = useState<'filters' | 'help' | 'catalog' | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [notice, setNotice] = useState('');
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(noticeTimer.current), []);
  const detailTrigger = useRef<HTMLElement | null>(null);
  const isLoading = catalogResult.isPending || result.isPending;
  const invalidReferences = items.some(
    (item) =>
      !catalog.leagues.some((l) => l.id === item.leagueId) ||
      [item.homeId, item.awayId, item.pickId].some((id) => !catalog.teams.some((t) => t.id === id)),
  );
  const isError = catalogResult.isError || result.isError || (!isLoading && invalidReferences);
  const filtered = filterValues(
    items,
    catalog,
    filters,
    deferredSearch,
    favorites,
    savedOnly,
    sort,
    result.data?.scenarioDate ?? '',
  );
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const best = filtered.reduce<(typeof filtered)[number] | undefined>(
    (acc, item) => (!acc || valueOf(item) > valueOf(acc) ? item : acc),
    undefined,
  );
  const average = filtered.length
    ? filtered.reduce((sum, item) => sum + valueOf(item), 0) / filtered.length
    : 0;
  const activeFilters = Object.entries(filters).filter(
    ([key, value]) => value !== defaultFilters[key as keyof typeof defaultFilters],
  ).length;
  const selected = items.find((item) => item.id === selectedId) ?? null;
  function updateFilters(next: typeof filters) {
    setFilters(next);
    setPage(1);
  }
  function chooseLeague(id: string) {
    updateFilters({ ...filters, league: id });
  }
  function changeSaved(value: boolean) {
    setSavedOnly(value);
    setPage(1);
  }
  function save(id: string) {
    toggle(id);
    setNotice(favorites.includes(id) ? 'Value retirée des favoris' : 'Value ajoutée aux favoris');
    clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(''), 2500);
  }
  function openDetail(id: string) {
    detailTrigger.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedId(id);
  }
  function closeDetail() {
    setSelectedId(null);
    requestAnimationFrame(() => detailTrigger.current?.focus());
  }
  function reset() {
    updateFilters(defaultFilters);
    setSearch('');
  }
  async function refresh() {
    await Promise.all([catalogResult.refetch(), result.refetch()]);
  }
  const sideProps = {
    favoriteCount: favorites.length,
    savedOnly,
    onSavedChange: changeSaved,
    leagues: catalog.leagues,
    selectedLeague: filters.league,
    onLeagueChange: chooseLeague,
    onCatalog: () => setPanel('catalog'),
    onHelp: () => setPanel('help'),
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Aller aux opportunités
      </a>
      <aside className="desktop-sidebar">
        <Sidebar {...sideProps} />
      </aside>
      <Dialog.Root open={mobileNav} onOpenChange={setMobileNav}>
        <Dialog.Portal>
          <Dialog.Overlay className="modal-overlay" />
          <Dialog.Content
            className="mobile-sidebar"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              if (!panel)
                document
                  .querySelector<HTMLButtonElement>('[aria-label="Ouvrir la navigation"]')
                  ?.focus();
            }}
          >
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Description className="sr-only">
              Choisir une section ou une ligue.
            </Dialog.Description>
            <Sidebar {...sideProps} onClose={() => setMobileNav(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              variant="ghost"
              iconOnly
              className="mobile-menu"
              onClick={() => setMobileNav(true)}
              aria-label="Ouvrir la navigation"
            >
              <Menu size={20} />
            </Button>
            <span className="breadcrumb-mark">
              <Radar size={17} />
            </span>
            <span>Espace d’analyse</span>
            <ChevronRight size={13} />
            <strong>{savedOnly ? 'Mes favoris' : 'Les values'}</strong>
          </div>
          <div className="header-actions">
            <button type="button" className="mode-pill" onClick={() => setPanel('help')}>
              <FlaskConical size={13} />
              {config.dataMode === 'mock' ? 'Mode démo' : 'Mode API'}
            </button>
            <span className="header-divider" />
            <Button
              variant="ghost"
              iconOnly
              onClick={toggleTheme}
              aria-label={`Activer le thème ${theme === 'dark' ? 'clair' : 'sombre'}`}
              title={`Thème ${theme === 'dark' ? 'clair' : 'sombre'}`}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={theme}
                  initial={{ opacity: 0, rotate: -30 }}
                  animate={{ opacity: 1, rotate: 0 }}
                  exit={{ opacity: 0, rotate: 30 }}
                  transition={{ duration: 0.12 }}
                >
                  {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
                </motion.span>
              </AnimatePresence>
            </Button>
            <Button
              variant="ghost"
              iconOnly
              className="header-help"
              onClick={() => setPanel('help')}
              aria-label="Aide et méthodologie"
            >
              <CircleHelp size={18} />
            </Button>
            <span className="profile-mark" title="Espace de démonstration">
              M
            </span>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" />
                LEAGUE OF LEGENDS
              </div>
              <h1>{savedOnly ? 'Vos values, à l’œil.' : 'Une longueur d’avance.'}</h1>
              <p>
                {savedOnly
                  ? 'Retrouvez les opportunités que vous suivez.'
                  : 'Les bonnes cotes commencent par une meilleure lecture.'}
              </p>
            </div>
            <div className="heading-actions">
              <span className="scenario-label">SCÉNARIO DE DÉMONSTRATION</span>
              <div className="date-caption">
                <span className="calendar-number">14</span>
                <span>
                  Septembre 2026<small>Heure de Paris · UTC+2</small>
                </span>
              </div>
            </div>
          </div>
          <section className="metrics-strip" aria-label="Indicateurs des résultats filtrés">
            <div className="metric">
              <div className="metric-icon">
                <Radar size={20} />
              </div>
              <div>
                <span>Opportunités détectées</span>
                <div className="metric-line">
                  <strong>{isLoading ? '—' : filtered.length.toString().padStart(2, '0')}</strong>
                  <span className="metric-tag">{savedOnly ? 'Favoris' : 'Values positives'}</span>
                </div>
              </div>
            </div>
            <div className="metric">
              <div className="metric-icon">
                <TrendingUp size={20} />
              </div>
              <div>
                <span>Value moyenne</span>
                <div className="metric-line">
                  <strong>{isLoading ? '—' : `+${percent(average)}`}</strong>
                  <span className="metric-description">sur la sélection</span>
                </div>
              </div>
            </div>
            <div className="metric">
              <div className="metric-icon">
                <Globe2 size={20} />
              </div>
              <div>
                <span>Ligues représentées</span>
                <div className="metric-line">
                  <strong>
                    {isLoading
                      ? '—'
                      : new Set(filtered.map((i) => i.leagueId)).size.toString().padStart(2, '0')}
                  </strong>
                  <button type="button" onClick={() => setPanel('catalog')}>
                    Explorer le catalogue
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          </section>
          <div className="workspace-grid">
            <section className="values-section" aria-labelledby="values-title">
              <div className="section-heading">
                <div>
                  <h2 id="values-title">{savedOnly ? 'Mes favoris' : 'Les values'}</h2>
                  <span className="count-pill">{isLoading ? '…' : filtered.length}</span>
                </div>
                <Button
                  variant="ghost"
                  className="refresh-button"
                  onClick={() => void refresh()}
                  disabled={result.isFetching || catalogResult.isFetching}
                >
                  <RefreshCw size={14} className={result.isFetching ? 'is-spinning' : ''} />
                  <span>{result.isFetching ? 'Actualisation…' : 'Actualiser'}</span>
                </Button>
              </div>
              <div className="league-tabs" aria-label="Filtres rapides par ligue">
                <button
                  type="button"
                  className={clsx(filters.league === 'all' && 'is-selected')}
                  aria-pressed={filters.league === 'all'}
                  aria-label="Toutes les ligues"
                  onClick={() => chooseLeague('all')}
                >
                  <span className="desktop-tab-label">Toutes les ligues</span>
                  <span className="mobile-tab-label">Toutes</span>
                </button>
                {['lck', 'lpl', 'lec', 'lfl', 'cblol-brazil']
                  .map((slug) => catalog.leagues.find((l) => l.slug === slug))
                  .filter((l) => !!l)
                  .map((league) => (
                    <button
                      type="button"
                      key={league.id}
                      data-league={league.slug}
                      className={clsx(filters.league === league.id && 'is-selected')}
                      aria-pressed={filters.league === league.id}
                      onClick={() => chooseLeague(league.id)}
                    >
                      {league.name}
                    </button>
                  ))}
                <button
                  type="button"
                  className="more-leagues"
                  onClick={() => setPanel('catalog')}
                  aria-label="Voir toutes les ligues"
                >
                  <Globe2 size={14} />
                  <span>Plus</span>
                </button>
              </div>
              <div className="filter-toolbar">
                <label className="search-field">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Une équipe, une ligue…"
                    aria-label="Rechercher une équipe ou une ligue"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch('')}
                      aria-label="Effacer la recherche"
                    >
                      <X size={14} />
                    </button>
                  )}
                </label>
                <Button
                  className={clsx('filter-button', activeFilters > 0 && 'has-filters')}
                  onClick={() => setPanel('filters')}
                >
                  <SlidersHorizontal size={15} />
                  Filtres{activeFilters > 0 && <span>{activeFilters}</span>}
                </Button>
                <div className="sort-wrapper">
                  <ArrowDownUp size={14} />
                  <Select
                    label="Trier les opportunités"
                    value={sort}
                    onChange={(value) => {
                      setSort(value);
                      setPage(1);
                    }}
                    options={[
                      { value: 'value', label: 'Value décroissante' },
                      { value: 'time', label: 'Matchs à venir' },
                      { value: 'probability', label: 'Probabilité estimée' },
                    ]}
                  />
                </div>
              </div>
              {activeFilters > 0 && (
                <div className="active-filters">
                  <span>
                    {filters.league !== 'all'
                      ? catalog.leagues.find((l) => l.id === filters.league)?.name
                      : 'Toutes les ligues'}
                    {filters.minValue > 0 ? ` · Value ≥ ${filters.minValue} %` : ''}
                    {filters.market !== 'all'
                      ? ` · ${filters.market === 'winner' ? 'Match' : 'Carte 1'}`
                      : ''}
                    {filters.bookmaker !== 'all' ? ` · ${filters.bookmaker}` : ''}
                  </span>
                  <button type="button" onClick={reset}>
                    Effacer
                    <X size={12} />
                  </button>
                </div>
              )}
              <div className="values-table" aria-busy={isLoading}>
                {isLoading ? (
                  <ValuesSkeleton />
                ) : isError ? (
                  <div className="empty-state" role="alert">
                    <span className="empty-icon">
                      <RefreshCw size={27} />
                    </span>
                    <h3>Les données font une pause.</h3>
                    <p>Impossible de charger les opportunités pour le moment.</p>
                    <Button onClick={() => void refresh()}>
                      Réessayer
                      <ArrowRight size={15} />
                    </Button>
                  </div>
                ) : filtered.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon">
                      {savedOnly ? <Bookmark size={29} /> : <Search size={29} />}
                    </span>
                    <h3>
                      {savedOnly && !favorites.length
                        ? 'Gardez vos meilleures pistes.'
                        : 'Aucune value dans cette sélection.'}
                    </h3>
                    <p>
                      {savedOnly && !favorites.length
                        ? 'Ajoutez une opportunité aux favoris pour la retrouver ici.'
                        : 'Essayez une autre équipe ou élargissez vos filtres.'}
                    </p>
                    <Button
                      onClick={() => {
                        reset();
                        if (savedOnly) changeSaved(false);
                      }}
                    >
                      {savedOnly ? 'Explorer les values' : 'Réinitialiser les filtres'}
                      <ArrowRight size={15} />
                    </Button>
                  </div>
                ) : (
                  <>
                    <div className="table-heading" aria-hidden="true">
                      <span>RENCONTRE</span>
                      <span>SÉLECTION</span>
                      <span>COTE</span>
                      <span>PROBA.</span>
                      <span>
                        VALUE <ArrowDownUp size={10} />
                      </span>
                      <span />
                    </div>
                    <motion.div
                      key={`${filters.league}-${savedOnly}-${currentPage}`}
                      initial={{ opacity: 0.55, y: 3 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.18 }}
                    >
                      {visible.map((item) => (
                        <ValueRow
                          key={item.id}
                          item={item}
                          league={catalog.leagues.find((l) => l.id === item.leagueId)!}
                          home={catalog.teams.find((t) => t.id === item.homeId)!}
                          away={catalog.teams.find((t) => t.id === item.awayId)!}
                          pick={catalog.teams.find((t) => t.id === item.pickId)!}
                          saved={favorites.includes(item.id)}
                          onSave={() => save(item.id)}
                          onOpen={() => openDetail(item.id)}
                        />
                      ))}
                    </motion.div>
                  </>
                )}
              </div>
              <div className="table-footer">
                <span aria-live="polite">
                  {!filtered.length
                    ? 'Aucun résultat'
                    : `${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, filtered.length)} sur ${filtered.length} opportunités`}
                </span>
                <div className="pagination">
                  <Button
                    iconOnly
                    variant="ghost"
                    aria-label="Page précédente"
                    disabled={currentPage === 1}
                    onClick={() => setPage(currentPage - 1)}
                  >
                    <ChevronLeft size={16} />
                  </Button>
                  <span>
                    {currentPage}
                    <small>/ {pages}</small>
                  </span>
                  <Button
                    iconOnly
                    variant="ghost"
                    aria-label="Page suivante"
                    disabled={currentPage === pages}
                    onClick={() => setPage(currentPage + 1)}
                  >
                    <ChevronRight size={16} />
                  </Button>
                </div>
              </div>
              <div className="data-caption">
                <span>
                  <FlaskConical size={13} />
                  Matchs et cotes simulés
                </span>
                <span>
                  {result.data
                    ? `Actualisé à ${time(result.data.generatedAt)}`
                    : 'Chargement du scénario'}
                  <span className="meta-dot">·</span>Heure de Paris
                </span>
              </div>
              <div className="bottom-insight">
                <span className="bottom-insight-icon">
                  <Radar size={20} />
                </span>
                <div>
                  <strong>Le bon réflexe : comparer.</strong>
                  <p>Ouvrez une value pour retrouver les cotes et le détail du calcul.</p>
                </div>
                <button
                  type="button"
                  aria-label="Comprendre le calcul"
                  onClick={() => setPanel('help')}
                >
                  <ArrowUpRight size={18} />
                </button>
              </div>
            </section>
            {!isLoading && !isError && best ? (
              <FeaturedValue
                item={best}
                catalog={catalog}
                onOpen={() => openDetail(best.id)}
                onHelp={() => setPanel('help')}
              />
            ) : (
              <aside className="insights-placeholder" aria-hidden="true">
                {isLoading && <InsightsSkeleton />}
              </aside>
            )}
          </div>
          <footer className="page-footer">
            <span>Un peu de recul. Une meilleure décision.</span>
            <span>
              18+<span className="meta-dot">·</span>Jouez avec modération.
            </span>
          </footer>
        </main>
      </div>
      <Suspense
        fallback={
          <div className="dialog-loading" role="status">
            Ouverture…
          </div>
        }
      >
        {panel === 'filters' && (
          <FilterDialog
            open
            onClose={() => setPanel(null)}
            filters={filters}
            onChange={updateFilters}
            catalog={catalog}
            bookmakers={[...new Set(items.flatMap((i) => i.offers.map((o) => o.bookmaker)))]}
          />
        )}
        {panel === 'help' && <HelpDialog open onClose={() => setPanel(null)} />}
        {panel === 'catalog' && (
          <CatalogDialog
            open
            onClose={() => setPanel(null)}
            catalog={catalog}
            selectedLeague={filters.league}
            onSelect={chooseLeague}
          />
        )}
        {selected && (
          <ValueDetail
            item={selected}
            catalog={catalog}
            saved={favorites.includes(selected.id)}
            onSave={() => save(selected.id)}
            onClose={closeDetail}
          />
        )}
      </Suspense>
      <div className="toast-region" role="status" aria-live="polite">
        <AnimatePresence>
          {notice && (
            <motion.div
              className="toast"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 5 }}
            >
              <Bookmark size={16} />
              {notice}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
