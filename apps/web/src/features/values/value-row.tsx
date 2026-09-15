import { ArrowUpRight, Bookmark } from 'lucide-react';
import { clsx } from 'clsx';
import type { League, Opportunity, Team } from '@/domain/schemas';
import { bestOffer, marketLabel, valueOf } from '@/domain/value';
import { decimal, percent, shortDate, time } from '@/lib/format';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
interface Props {
  item: Opportunity;
  league: League;
  home: Team;
  away: Team;
  pick: Team;
  saved: boolean;
  onSave: () => void;
  onOpen: () => void;
}
export function ValueRow({ item, league, home, away, pick, saved, onSave, onOpen }: Props) {
  const offer = bestOffer(item);
  return (
    <article className="value-row" aria-label={`${home.name} contre ${away.name}`}>
      <div className="match-cell">
        <div className="team-pair">
          <Logo src={home.image} name={home.name} code={home.code} />
          <Logo src={away.image} name={away.name} code={away.code} />
        </div>
        <div className="match-info">
          <button type="button" className="match-name" onClick={onOpen}>
            {home.code}
            <span className="versus">vs</span>
            {away.code}
          </button>
          <div className="match-meta">
            <span>{league.name}</span>
            <span className="meta-dot">·</span>
            <span>{item.format}</span>
            <span className="meta-dot">·</span>
            <span>
              {shortDate(item.startsAt)}, {time(item.startsAt)}
            </span>
          </div>
        </div>
      </div>
      <div className="pick-cell">
        <strong>{pick.code}</strong>
        <span>{marketLabel(item.market)}</span>
      </div>
      <div className="odds-cell">
        <strong>
          {decimal(offer.odds)}
          <ArrowUpRight size={12} />
        </strong>
        <span>{offer.bookmaker}</span>
      </div>
      <div className="probability-cell">
        <strong>{percent(item.probability * 100, 0)}</strong>
        <span>estimée</span>
      </div>
      <div className="value-cell">
        <span className="value-badge">+{percent(valueOf(item))}</span>
        <span className="mobile-value-label">value</span>
      </div>
      <div className="row-actions">
        <Button
          variant="ghost"
          iconOnly
          aria-label={`${saved ? 'Retirer' : 'Ajouter'} ${home.code} – ${away.code} ${item.market === 'winner' ? 'match' : 'carte 1'} ${saved ? 'des' : 'aux'} favoris`}
          aria-pressed={saved}
          onClick={onSave}
        >
          <Bookmark size={17} className={clsx(saved && 'bookmark-filled')} />
        </Button>
        <Button
          variant="ghost"
          iconOnly
          className="row-open"
          aria-label={`Analyser ${home.code} – ${away.code}`}
          onClick={onOpen}
        >
          <ArrowUpRight size={17} />
        </Button>
      </div>
    </article>
  );
}
