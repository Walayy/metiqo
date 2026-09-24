import { BrandMark } from '@/components/ui/brand-mark';
import {
  CalendarDays,
  ChartNoAxesCombined,
  HeartHandshake,
  Link,
  Radar,
  Terminal,
  Users,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useId } from 'react';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/button';
import { viewLabels } from '@/app/navigation';
import type { AppView } from '@/app/navigation';
import { GameSelector } from './game-selector';

interface Props {
  view: AppView;
  onNavigate: (view: AppView) => void;
  onSupport: (kind: 'donation' | 'referral') => void;
  isAdmin: boolean;
  onClose?: () => void;
  showBrand?: boolean;
}
export function Sidebar({
  view,
  onNavigate,
  onSupport,
  isAdmin,
  onClose,
  showBrand = true,
}: Props) {
  const selectionId = useId();
  function entry(id: AppView, Icon: LucideIcon) {
    return (
      <button
        type="button"
        className={clsx('nav-item', view === id && 'is-active')}
        aria-current={view === id ? 'page' : undefined}
        onClick={() => {
          onNavigate(id);
          onClose?.();
        }}
      >
        {view === id && <SelectionIndicator id={selectionId} />}
        <Icon size={18} />
        <span>{viewLabels[id]}</span>
        <span className="nav-active-dot" />
      </button>
    );
  }
  return (
    <div className="sidebar-inner">
      {showBrand && (
        <div className="brand">
          <BrandMark size={40} />
          <span>
            metiquo<span className="brand-period">.</span>
          </span>
          {onClose && (
            <Button iconOnly variant="ghost" onClick={onClose} aria-label="Fermer la navigation">
              <X size={18} />
            </Button>
          )}
        </div>
      )}
      <GameSelector />
      <nav aria-label="Navigation principale" className="sidebar-groups">
        {isAdmin && (
          <div>
            <p className="nav-label">GESTION</p>
            <div className="main-nav">
              {entry('users', Users)}
              {entry('admin', Terminal)}
            </div>
          </div>
        )}
        <div>
          <p className="nav-label">ESPORT</p>
          <div className="main-nav">{entry('matches', CalendarDays)}</div>
        </div>
        <div>
          <p className="nav-label">ANALYSE</p>
          <div className="main-nav">
            {entry('values', Radar)}
            {entry('performance', ChartNoAxesCombined)}
          </div>
        </div>
        <div>
          <p className="nav-label">SOUTENIR METIQUO</p>
          <div className="main-nav">
            <button
              type="button"
              className="nav-item"
              aria-haspopup="dialog"
              onClick={() => {
                onSupport('donation');
                onClose?.();
              }}
            >
              <HeartHandshake size={18} />
              <span>Faire un don</span>
            </button>
            <button
              type="button"
              className="nav-item"
              aria-haspopup="dialog"
              onClick={() => {
                onSupport('referral');
                onClose?.();
              }}
            >
              <Link size={18} />
              <span>Parrainage Stake</span>
            </button>
          </div>
        </div>
      </nav>
    </div>
  );
}
