import { useDeferredValue, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { Dialog } from 'radix-ui';
import {
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Globe2,
  Menu,
  Moon,
  Radar,
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
import { catalogQuery, opportunitiesQuery } from '@/lib/api';
import { useMinimumLoading } from '@/hooks/use-minimum-loading';
import { ContentTransition } from '@/components/ui/content-transition';
import { useTheme } from '@/hooks/use-theme';
import { useExplorerLocation } from '@/hooks/use-explorer-location';
import { Sidebar } from '@/components/layout/sidebar';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Select } from '@/components/ui/select';
import { Modal } from '@/components/ui/modal';
import { InsightsSkeleton, ValuesSkeleton } from '@/components/ui/skeleton';
import { ValueRow } from '@/features/values/value-row';
import { FeaturedValue } from '@/features/values/featured-value';
import { LeagueFilters, RefreshValues } from '@/features/values/league-filters';
import { defaultFilters } from '@/features/values/filter-state';
import { filterValues } from '@/features/values/filter';
import { ValueDetail } from '@/features/values/value-detail';
import { FilterDialog } from '@/features/values/filter-dialog';
import { HelpDialog } from '@/features/values/help-dialog';
import { CatalogDialog } from '@/features/catalog/catalog-dialog';
import { Account } from '@/features/auth/account';
import { sessionQuery } from '@/features/auth/api';
import { AdminPage } from '@/features/admin/admin-page';
import { AccountContext } from '@/features/auth/account-context';
import { StatusPanel } from '@/features/status/status-panel';
import { HttpError } from '@/lib/http-error';
import { viewLabels } from './navigation';
import type { AppView } from './navigation';
import { MatchesPage } from '@/features/matches/matches-page';
import { PerformancePage } from '@/features/performance/performance-page';
import { SupportDialog } from '@/features/support/support-dialog';

const emptyCatalog: Catalog = { retrievedAt: '', source: '', leagues: [], teams: [] };
const pageSize = 6;
export function App() {
  const [open, setOpen] = useState(false);
  return (
    <AccountContext.Provider value={{ open, setOpen }}>
      <ExplorerApp />
    </AccountContext.Provider>
  );
}
function ExplorerApp() {
  const session = useQuery(sessionQuery);
  const queryClient = useQueryClient();
  const isAdmin = session.data?.user?.role === 'admin' && !session.isError;
  useEffect(() => {
    if (!isAdmin) {
      void queryClient
        .cancelQueries({ queryKey: ['admin'] })
        .then(() => queryClient.removeQueries({ queryKey: ['admin'] }));
    }
  }, [isAdmin, queryClient]);
  const catalogResult = useQuery(catalogQuery);
  const catalog = catalogResult.data ?? emptyCatalog;
  const { theme, toggleTheme } = useTheme();
  const [explorer, updateLocation] = useExplorerLocation();
  const { view, day, filters, search, sort, page, selectedId, detailOpen } = explorer;
  const adminOpen = view === 'admin' || view === 'users';
  const valuesOpen = view === 'values';
  const result = useQuery({ ...opportunitiesQuery, enabled: valuesOpen });
  const items = result.data?.items ?? [];
  const setFilters = (filters: typeof defaultFilters) => updateLocation({ filters });
  const setSearch = (search: string) => updateLocation({ search });
  const setSort = (sort: string) => updateLocation({ sort });
  const setPage = (page: number) => updateLocation({ page });
  const deferredSearch = useDeferredValue(search);
  const resultsHeading = useRef<HTMLHeadingElement>(null);
  const pendingPageFocus = useRef(false);
  const [panel, setPanel] = useState<
    'filters' | 'help' | 'catalog' | 'donation' | 'referral' | null
  >(null);
  const [mobileNav, setMobileNav] = useState(false);
  const isLoading = useMinimumLoading(
    catalogResult.isFetching || (valuesOpen && result.isFetching),
    JSON.stringify([view, filters, deferredSearch, sort, page]),
  );
  const invalidReferences = items.some(
    (item) =>
      !catalog.leagues.some((l) => l.id === item.leagueId) ||
      [item.homeId, item.awayId, item.pickId].some((id) => !catalog.teams.some((t) => t.id === id)),
  );
  const dataError =
    catalogResult.error ??
    (valuesOpen ? result.error : null) ??
    (valuesOpen && !isLoading && invalidReferences
      ? new HttpError(0, { kind: 'invalid-response' })
      : null);
  const isError = !!dataError;
  const filtered = filterValues(
    items,
    catalog,
    filters,
    deferredSearch,
    sort,
    result.data?.referenceDate ?? '',
  );
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages);
  useLayoutEffect(() => {
    if (!pendingPageFocus.current) return;
    pendingPageFocus.current = false;
    resultsHeading.current?.focus({ preventScroll: true });
    resultsHeading.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [currentPage]);
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
    updateFilters({ ...filters, league: id, team: 'all' });
  }
  function chooseTeam(id: string) {
    updateLocation({
      filters: { ...defaultFilters, team: id },
      search: '',
      view: 'values',
      page: 1,
    });
  }
  function changePage(next: number) {
    pendingPageFocus.current = true;
    setPage(next);
  }
  function openDetail(id: string) {
    updateLocation({ selectedId: id, detailOpen: true });
  }
  function closeDetail() {
    updateLocation({ detailOpen: false });
  }
  function reset() {
    updateFilters(defaultFilters);
    setSearch('');
  }
  async function refresh() {
    const refreshed = await Promise.all([catalogResult.refetch(), result.refetch()]);
    if (isError && refreshed.every((query) => query.isSuccess)) {
      requestAnimationFrame(() => resultsHeading.current?.focus({ preventScroll: true }));
    }
  }
  const sideProps = {
    view,
    onNavigate: (next: AppView) => {
      updateLocation({ view: next, page: 1, detailOpen: false });
      requestAnimationFrame(() =>
        document.getElementById('main-content')?.focus({ preventScroll: true }),
      );
      window.scrollTo({ top: 0, behavior: 'instant' });
    },
    onSupport: (kind: 'donation' | 'referral') => setPanel(kind),
    isAdmin,
  };
  useEffect(() => {
    document.title = `${viewLabels[view]} · Metiquo`;
  }, [view]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Aller au contenu principal
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
                  ?.focus({ preventScroll: true });
            }}
          >
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Choisir une section.</Dialog.Description>
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
            <span>{adminOpen ? 'Gestion' : view === 'matches' ? 'Esport' : 'Analyse'}</span>
            <ChevronRight size={13} />
            <strong>{viewLabels[view]}</strong>
          </div>
          <div className="header-actions">
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
            <Account />
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <ContentTransition id={view}>
            {adminOpen ? (
              session.isPending ? (
                <div className="admin-empty" aria-busy="true">
                  Vérification de votre accès…
                </div>
              ) : isAdmin && session.data?.user ? (
                <AdminPage
                  userId={session.data.user.id}
                  section={view === 'users' ? 'users' : 'scripts'}
                />
              ) : (
                <StatusPanel
                  error={session.error ?? new HttpError(session.data?.user ? 403 : 401)}
                  onRetry={() => void session.refetch()}
                  busy={session.isFetching}
                  onHome={() => updateLocation({ view: 'values' })}
                />
              )
            ) : dataError ? (
              <StatusPanel
                error={dataError}
                onRetry={() => void refresh()}
                busy={result.isFetching || catalogResult.isFetching}
              />
            ) : view === 'matches' ? (
              <MatchesPage
                catalog={catalog}
                day={day}
                onDay={(day) => updateLocation({ day })}
                loading={catalogResult.isPending}
              />
            ) : view === 'performance' ? (
              <PerformancePage catalog={catalog} loading={catalogResult.isPending} />
            ) : (
              <>
                <div className="page-heading">
                  <div>
                    <div className="eyebrow">
                      <span className="eyebrow-line" />
                      LEAGUE OF LEGENDS
                    </div>
                    <h1>Une longueur d’avance.</h1>
                    <p>Les bonnes cotes commencent par une meilleure lecture.</p>
                  </div>
                </div>
                <section
                  className="metrics-strip"
                  aria-label="Indicateurs des résultats filtrés"
                  aria-busy={isLoading}
                >
                  <div className="metric">
                    <div className="metric-icon">
                      <Radar size={20} />
                    </div>
                    <div>
                      <span>Opportunités détectées</span>
                      <div className="metric-line">
                        <strong>
                          {isLoading ? (
                            <span className="skeleton skeleton-metric" />
                          ) : (
                            filtered.length.toString().padStart(2, '0')
                          )}
                        </strong>
                        <span className="metric-tag">Values positives</span>
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
                        <strong>
                          {isLoading ? (
                            <span className="skeleton skeleton-metric" />
                          ) : (
                            `+${percent(average)}`
                          )}
                        </strong>
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
                          {isLoading ? (
                            <span className="skeleton skeleton-metric" />
                          ) : (
                            new Set(filtered.map((i) => i.leagueId)).size
                              .toString()
                              .padStart(2, '0')
                          )}
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
                    <div className="section-heading values-heading">
                      <div>
                        <h2 id="values-title" ref={resultsHeading} tabIndex={-1}>
                          Les values
                        </h2>
                        <span className="count-pill">{isLoading ? '…' : filtered.length}</span>
                      </div>
                      <RefreshValues
                        mobile
                        onRefresh={() => void refresh()}
                        refreshing={result.isFetching || catalogResult.isFetching}
                      />
                    </div>
                    <LeagueFilters
                      leagues={catalog.leagues}
                      selectedLeague={filters.league}
                      onSelect={chooseLeague}
                      loading={catalogResult.isPending}
                      error={catalogResult.error}
                      onRefresh={() => void refresh()}
                      refreshing={result.isFetching || catalogResult.isFetching}
                    />
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
                        disabled={!catalogResult.data}
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
                            ? (catalog.leagues.find((l) => l.id === filters.league)?.name ??
                              'Ligue indisponible')
                            : 'Toutes les ligues'}
                          {filters.team !== 'all'
                            ? ` · ${catalog.teams.find((team) => team.id === filters.team)?.name ?? 'Équipe indisponible'}`
                            : ''}
                          {filters.minValue > 0 ? ` · Value ≥ ${filters.minValue} %` : ''}
                          {filters.market !== 'all'
                            ? ` · ${filters.market === 'winner' ? 'Match' : 'Carte 1'}`
                            : ''}
                        </span>
                        <button type="button" onClick={reset}>
                          Effacer
                          <X size={12} />
                        </button>
                      </div>
                    )}
                    <div className="values-table" aria-busy={isLoading}>
                      <ContentTransition id={isLoading ? 'loading' : 'ready'}>
                        {isLoading ? (
                          <ValuesSkeleton rows={visible.length || pageSize} />
                        ) : filtered.length === 0 ? (
                          <div className="empty-state">
                            <span className="empty-icon">
                              <Search size={29} />
                            </span>
                            <h3>Aucune value dans cette sélection.</h3>
                            <p>Essayez une autre équipe ou élargissez vos filtres.</p>
                            <Button onClick={reset}>
                              Effacer les filtres et la recherche
                              <ArrowRight size={15} />
                            </Button>
                          </div>
                        ) : (
                          <div role="table" aria-label="Opportunités" aria-colcount={6}>
                            <div role="rowgroup">
                              <div className="table-heading" role="row">
                                <span role="columnheader" aria-colindex={1}>
                                  RENCONTRE
                                </span>
                                <span role="columnheader" aria-colindex={2}>
                                  SÉLECTION
                                </span>
                                <span role="columnheader" aria-colindex={3}>
                                  COTE
                                </span>
                                <span role="columnheader" aria-colindex={4}>
                                  PROBA.
                                </span>
                                <span role="columnheader" aria-colindex={5}>
                                  VALUE
                                </span>
                                <span role="columnheader" aria-colindex={6}>
                                  <span className="sr-only">Actions</span>
                                </span>
                              </div>
                            </div>
                            <div role="rowgroup">
                              {visible.map((item) => (
                                <ValueRow
                                  key={item.id}
                                  item={item}
                                  league={catalog.leagues.find((l) => l.id === item.leagueId)!}
                                  home={catalog.teams.find((t) => t.id === item.homeId)!}
                                  away={catalog.teams.find((t) => t.id === item.awayId)!}
                                  pick={catalog.teams.find((t) => t.id === item.pickId)!}
                                  onOpen={() => openDetail(item.id)}
                                />
                              ))}
                            </div>
                          </div>
                        )}
                      </ContentTransition>
                    </div>
                    <div className="table-footer">
                      <span aria-live="polite">
                        {isLoading
                          ? 'Chargement des opportunités…'
                          : !filtered.length
                            ? 'Aucun résultat'
                            : `Page ${currentPage} sur ${pages} · ${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, filtered.length)} sur ${filtered.length} opportunités`}
                      </span>
                      <div className="pagination">
                        <Button
                          iconOnly
                          variant="ghost"
                          aria-label="Page précédente"
                          disabled={currentPage === 1}
                          onClick={() => changePage(currentPage - 1)}
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
                          onClick={() => changePage(currentPage + 1)}
                        >
                          <ChevronRight size={16} />
                        </Button>
                      </div>
                    </div>
                    <div className="data-caption">
                      <span>Cotes suivies sur Stake</span>
                      <span>
                        {result.data ? `Actualisé à ${time(result.data.generatedAt)}` : '—'}
                        <span className="meta-dot">·</span>Heure de Paris
                      </span>
                    </div>
                    <div className="bottom-insight">
                      <span className="bottom-insight-icon">
                        <Radar size={20} />
                      </span>
                      <div>
                        <strong>Comprendre la value.</strong>
                        <p>Découvrez le lien entre probabilité estimée, cote et value.</p>
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
              </>
            )}
          </ContentTransition>
        </main>
      </div>
      <>
        <FilterDialog
          open={panel === 'filters'}
          onClose={() => setPanel(null)}
          filters={filters}
          onChange={updateFilters}
          catalog={catalog}
        />
        <SupportDialog
          kind={panel === 'donation' || panel === 'referral' ? panel : null}
          onClose={() => setPanel(null)}
        />
        <HelpDialog open={panel === 'help'} onClose={() => setPanel(null)} />
        <CatalogDialog
          open={panel === 'catalog'}
          onClose={() => setPanel(null)}
          catalog={catalog}
          selectedLeague={filters.league}
          onSelect={chooseLeague}
          onSelectTeam={chooseTeam}
          loading={catalogResult.isPending}
          error={catalogResult.error}
          retrying={catalogResult.isFetching}
          onRetry={() => void catalogResult.refetch()}
        />
        {selected && !isLoading && !isError && (
          <ValueDetail item={selected} open={detailOpen} catalog={catalog} onClose={closeDetail} />
        )}
        <Modal
          open={detailOpen && !selected && !isLoading && !isError}
          onOpenChange={(open) => {
            if (!open) closeDetail();
          }}
          title="Opportunité indisponible"
          description="Cette opportunité ne figure plus dans les données disponibles."
        >
          <StatusPanel
            compact
            error={new HttpError(404)}
            description="Cette opportunité ne figure plus dans les données disponibles. Retrouvez les autres rencontres dans les résultats."
            onHome={closeDetail}
          />
        </Modal>
      </>
      {(result.isFetching || catalogResult.isFetching) && (
        <Spinner fixed label="Actualisation des données" />
      )}
    </div>
  );
}
