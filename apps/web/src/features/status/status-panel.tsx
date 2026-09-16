import { BrandMark } from '@/components/ui/brand-mark';
import { useContext, useEffect, useId, useRef, useState } from 'react';
import {
  ArrowRight,
  Clock3,
  FileQuestion,
  House,
  LockKeyhole,
  LogIn,
  Moon,
  RefreshCw,
  ServerOff,
  ShieldBan,
  Sun,
  WifiOff,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AccountContext } from '@/features/auth/account-context';
import { useTheme } from '@/hooks/use-theme';
import { HttpError, remainingSeconds } from '@/lib/http-error';
import { statusContent, waitLabel } from './status-model';
import './status.css';

const icons = {
  document: FileQuestion,
  clock: Clock3,
  lock: LockKeyhole,
  shield: ShieldBan,
  server: ServerOff,
  network: WifiOff,
  refresh: RefreshCw,
};

export function StatusPanel({
  error,
  onRetry,
  onHome,
  busy = false,
  compact = false,
  focus = true,
  retryLabel,
  description,
  headingLevel,
}: {
  error: Error;
  onRetry?: () => void;
  onHome?: () => void;
  busy?: boolean;
  compact?: boolean;
  focus?: boolean;
  retryLabel?: string;
  description?: string;
  headingLevel?: 1 | 2;
}) {
  const content = statusContent(error);
  const Icon = icons[content.icon];
  const account = useContext(AccountContext);
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  const deadline = error instanceof HttpError ? error.retryAt : 0;
  const [now, setNow] = useState(Date.now);
  const seconds = remainingSeconds(deadline, now);
  const waiting = seconds > 0;
  useEffect(() => {
    if (!deadline) return;
    const tick = () => setNow(Date.now());
    const timer = setInterval(tick, 1000);
    window.addEventListener('focus', tick);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', tick);
    };
  }, [deadline]);
  useEffect(() => {
    if (!focus) return;
    const focusHeading = () => heading.current?.focus({ preventScroll: true });
    if (document.getElementById('root')?.hasAttribute('inert')) {
      window.addEventListener('metiquo:ready', focusHeading, { once: true });
      return () => window.removeEventListener('metiquo:ready', focusHeading);
    }
    focusHeading();
  }, [content.code, focus]);
  const canRetry = content.action === 'retry' && onRetry;
  const canLogin = content.action === 'login' && account;
  const Heading = compact || headingLevel === 2 ? 'h2' : 'h1';
  const homeLabel = compact ? 'Revenir aux values' : 'Retour aux values';
  return (
    <section
      className={`status-panel${compact ? ' status-panel--compact' : ''}`}
      aria-labelledby={id}
      aria-busy={busy}
    >
      <div className="status-visual" aria-hidden="true">
        <Icon size={compact ? 28 : 40} strokeWidth={1.5} />
      </div>
      <div className="status-copy">
        <span className="status-code">{content.code}</span>
        <Heading id={id} ref={heading} tabIndex={-1}>
          {content.title}
        </Heading>
        <p>{description ?? content.description}</p>
        {deadline > 0 ? (
          <div className="status-wait">
            <Clock3 size={18} aria-hidden="true" />
            <div>
              <span role="status">
                {waiting ? 'Nouvel essai possible dans' : 'Vous pouvez réessayer maintenant.'}
              </span>
              {waiting && <strong aria-live="off">{waitLabel(seconds)}</strong>}
              <small>Aucune demande ne sera relancée automatiquement.</small>
            </div>
          </div>
        ) : error instanceof HttpError && error.status === 429 ? (
          <p className="status-hint">
            Le serveur n’a pas indiqué de délai précis. Patientez un moment avant de réessayer.
          </p>
        ) : null}
        <div className="status-actions">
          {canLogin && (
            <Button variant="primary" onClick={() => account.setOpen(true)}>
              <LogIn size={17} /> Se connecter
            </Button>
          )}
          {canRetry && (
            <Button variant="primary" disabled={waiting || busy} onClick={onRetry}>
              <RefreshCw size={17} />
              {busy
                ? 'Vérification…'
                : (retryLabel ?? (content.code === '409' ? 'Actualiser' : 'Réessayer'))}
            </Button>
          )}
          {onHome ? (
            <Button variant={canLogin || canRetry ? 'secondary' : 'primary'} onClick={onHome}>
              <House size={17} />
              {homeLabel}
            </Button>
          ) : (
            <a
              className={`button button--${canLogin || canRetry ? 'secondary' : 'primary'}`}
              href="/"
            >
              <House size={17} />
              {homeLabel}
              <ArrowRight size={16} />
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

export function StatusPage({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { theme, toggleTheme } = useTheme();
  const title = statusContent(error).title;
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · Metiquo`;
    return () => {
      document.title = previous;
    };
  }, [title]);
  return (
    <div className="status-page">
      <a className="skip-link" href="#status-main">
        Aller au contenu principal
      </a>
      <header className="status-header">
        <a href="/" className="brand" aria-label="Metiquo, retour aux values">
          <BrandMark size={40} />
          <span>
            metiquo<span className="brand-period">.</span>
          </span>
        </a>
        <Button
          variant="ghost"
          iconOnly
          onClick={toggleTheme}
          aria-label={`Activer le thème ${theme === 'dark' ? 'clair' : 'sombre'}`}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </Button>
      </header>
      <main id="status-main">
        <StatusPanel error={error} onRetry={onRetry} />
      </main>
      <footer className="status-footer">Metiquo · Une meilleure lecture du jeu.</footer>
    </div>
  );
}
