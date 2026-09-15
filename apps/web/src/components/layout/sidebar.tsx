import { ArrowUpRight, Bookmark, CircleHelp, Globe2, Radar, ShieldCheck, X } from 'lucide-react';
import type { League } from '@/domain/schemas';
import { clsx } from 'clsx';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
import { GameSelector } from './game-selector';

interface Props {
  favoriteCount: number;
  savedOnly: boolean;
  onSavedChange: (value: boolean) => void;
  leagues: League[];
  selectedLeague: string;
  onLeagueChange: (id: string) => void;
  onCatalog: () => void;
  onHelp: () => void;
  onClose?: () => void;
}
export function Sidebar({
  favoriteCount,
  savedOnly,
  onSavedChange,
  leagues,
  selectedLeague,
  onLeagueChange,
  onCatalog,
  onHelp,
  onClose,
}: Props) {
  const pinned = ['lck', 'lpl', 'lec', 'lfl', 'lcs', 'cblol-brazil', 'lcp'];
  return (
    <div className="sidebar-inner">
      <div className="brand">
        <svg viewBox="0 0 48 48" aria-hidden="true">
          <rect width="48" height="48" rx="13" fill="currentColor" />
          <path d="M10 33V15h6l8 10 8-10h6v18h-7V25l-7 8-7-8v8z" fill="var(--brand-ink)" />
        </svg>
        <span>
          metiquo<span className="brand-period">.</span>
        </span>
        {onClose && (
          <Button iconOnly variant="ghost" onClick={onClose} aria-label="Fermer la navigation">
            <X size={18} />
          </Button>
        )}
      </div>
      <GameSelector />
      <p className="nav-label">ESPACE D’ANALYSE</p>
      <nav aria-label="Navigation principale" className="main-nav">
        <button
          type="button"
          className={clsx('nav-item', !savedOnly && 'is-active')}
          aria-current={!savedOnly ? 'page' : undefined}
          onClick={() => {
            onSavedChange(false);
            onClose?.();
          }}
        >
          <Radar size={19} />
          <span>Les values</span>
          <span className="nav-active-dot" />
        </button>
        <button
          type="button"
          className={clsx('nav-item', savedOnly && 'is-active')}
          aria-current={savedOnly ? 'page' : undefined}
          onClick={() => {
            onSavedChange(true);
            onClose?.();
          }}
        >
          <Bookmark size={18} />
          <span>Mes favoris</span>
          <span className="nav-count">{favoriteCount}</span>
        </button>
      </nav>
      <div className="nav-section-heading">
        <p className="nav-label">LES COMPÉTITIONS</p>
        <span>LoL</span>
      </div>
      <nav aria-label="Ligues favorites" className="league-nav">
        {!leagues.length &&
          pinned.map((slug) => (
            <div key={slug} className="nav-item league-loading" aria-hidden="true">
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          ))}
        {pinned
          .map((slug) => leagues.find((l) => l.slug === slug))
          .filter((league): league is League => !!league)
          .map((league) => (
            <button
              type="button"
              key={league.id}
              className={clsx(
                'nav-item league-nav-item',
                selectedLeague === league.id && 'league-is-active',
              )}
              aria-pressed={selectedLeague === league.id}
              onClick={() => {
                onLeagueChange(selectedLeague === league.id ? 'all' : league.id);
                onClose?.();
              }}
            >
              <Logo src={league.image} name={league.name} league />
              <span>{league.name}</span>
            </button>
          ))}
        <button
          type="button"
          className="nav-item all-leagues"
          onClick={() => {
            onCatalog();
            onClose?.();
          }}
        >
          <Globe2 size={17} />
          <span>Toutes les ligues</span>
          <ArrowUpRight size={14} />
        </button>
      </nav>
      <div className="sidebar-bottom">
        <div className="analysis-card">
          <span className="analysis-icon">
            <ShieldCheck size={19} />
          </span>
          <strong>Le jeu de l’analyse.</strong>
          <p>
            Explorez les données.
            <br />
            Affinez votre lecture.
          </p>
        </div>
        <button
          type="button"
          className="nav-item help-nav"
          onClick={() => {
            onHelp();
            onClose?.();
          }}
        >
          <CircleHelp size={18} />
          <span>Comprendre la value</span>
          <ArrowUpRight size={14} />
        </button>
        <div className="sidebar-signature">
          <span>Conçu pour voir plus juste.</span>
          <span>v0.1</span>
        </div>
      </div>
    </div>
  );
}
