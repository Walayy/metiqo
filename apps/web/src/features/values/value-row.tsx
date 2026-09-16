import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';
import type { League, Opportunity, Team } from '@/domain/schemas';
import { currentQuote, oddsChange, trackedBookmaker, marketLabel, valueOf } from '@/domain/value';
import { decimal, percent } from '@/lib/format';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
interface Props {
  item: Opportunity;
  league: League;
  home: Team;
  away: Team;
  pick: Team;
  onOpen: () => void;
}
export function ValueRow({ item, league, home, away, pick, onOpen }: Props) {
  const offer = currentQuote(item);
  const TrendIcon =
    oddsChange(item) > 0 ? ArrowUpRight : oddsChange(item) < 0 ? ArrowDownRight : ArrowRight;
  return (
    <div
      role="row"
      className="value-row"
      aria-label={`${home.name} contre ${away.name}, ${marketLabel(item.market)}`}
    >
      <div className="match-cell" role="cell" aria-colindex={1}>
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
          </div>
        </div>
      </div>
      <div className="pick-cell" role="cell" aria-colindex={2}>
        <strong>{pick.code}</strong>
        <span>{marketLabel(item.market)}</span>
      </div>
      <div
        className="odds-cell"
        role="cell"
        aria-colindex={3}
        aria-label={`Cote Stake ${decimal(offer.odds)}`}
      >
        <strong>
          {decimal(offer.odds)}
          <TrendIcon size={12} aria-hidden="true" />
        </strong>
        <span>{trackedBookmaker.name}</span>
      </div>
      <div
        className="probability-cell"
        role="cell"
        aria-colindex={4}
        aria-label={`Probabilité estimée ${percent(item.probability * 100, 0)}`}
      >
        <strong>{percent(item.probability * 100, 0)}</strong>
        <span>estimée</span>
      </div>
      <div
        className="value-cell"
        role="cell"
        aria-colindex={5}
        aria-label={`Value +${percent(valueOf(item))}`}
      >
        <span className="value-badge">+{percent(valueOf(item))}</span>
        <span className="mobile-value-label">value</span>
      </div>
      <div className="row-actions" role="cell" aria-colindex={6}>
        <Button
          variant="ghost"
          className="row-open"
          aria-label={`Analyser ${home.code} – ${away.code}, ${marketLabel(item.market)}`}
          onClick={onOpen}
        >
          <span className="row-open-label">Détail</span>
          <ArrowUpRight size={17} />
        </Button>
      </div>
    </div>
  );
}
