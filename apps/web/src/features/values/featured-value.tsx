import { ArrowRight, ArrowUpRight, Sparkles } from 'lucide-react';
import type { Catalog, Opportunity } from '@/domain/schemas';
import { bestOffer, valueOf, marketLabel } from '@/domain/value';
import { decimal } from '@/lib/format';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
import { OddsChart } from '@/components/ui/odds-chart';
export function FeaturedValue({
  item,
  catalog,
  onOpen,
  onHelp,
}: {
  item: Opportunity;
  catalog: Catalog;
  onOpen: () => void;
  onHelp: () => void;
}) {
  const home = catalog.teams.find((t) => t.id === item.homeId)!;
  const away = catalog.teams.find((t) => t.id === item.awayId)!;
  const pick = catalog.teams.find((t) => t.id === item.pickId)!;
  const league = catalog.leagues.find((l) => l.id === item.leagueId)!;
  const offer = bestOffer(item);
  return (
    <aside className="insights-column" aria-label="À la une">
      <div className="featured-card">
        <div className="featured-eyebrow">
          <span>
            <Sparkles size={15} /> LA VALUE À SUIVRE
          </span>
          <ArrowUpRight size={17} />
        </div>
        <div className="featured-teams">
          <div>
            <Logo src={home.image} name={home.name} />
            <strong>{home.code}</strong>
          </div>
          <span>vs</span>
          <div>
            <Logo src={away.image} name={away.name} />
            <strong>{away.code}</strong>
          </div>
        </div>
        <p className="featured-league">
          {league.name}
          <span>·</span>
          {item.format}
          <span>·</span>Simulation
        </p>
        <div className="featured-value">
          <span>
            +{decimal(valueOf(item), 1)}
            <small>%</small>
          </span>
          <p>de value estimée</p>
        </div>
        <div className="featured-pick">
          <div>
            <span>NOTRE SÉLECTION</span>
            <strong>
              {pick.code}
              <small>{marketLabel(item.market)}</small>
            </strong>
          </div>
          <strong>{decimal(offer.odds)}</strong>
        </div>
        <Button variant="primary" className="featured-cta" onClick={onOpen}>
          Voir l’analyse
          <ArrowRight size={16} />
        </Button>
      </div>
      <div className="trend-card">
        <div className="section-mini-title">
          <h3>Le mouvement de cote</h3>
          <span className="mini-icon">
            <ArrowUpRight size={15} />
          </span>
        </div>
        <div className="trend-value">
          <strong>{decimal(offer.odds)}</strong>
          <span>+{decimal(offer.odds - (item.history[0]?.odds ?? offer.odds))}</span>
        </div>
        <p>
          {pick.code} · {offer.bookmaker} · simulé
        </p>
        <OddsChart history={item.history} compact />
      </div>
      <button type="button" className="learn-card" onClick={onHelp}>
        <span className="learn-icon">
          <Sparkles size={18} />
        </span>
        <span>
          <strong>Une cote. Une opportunité.</strong>
          <small>Comprendre la value en 1 minute</small>
        </span>
        <ArrowUpRight size={16} />
      </button>
      <p className="insights-note">
        Les estimations sont simulées.
        <br />
        Une value positive ne garantit pas un gain.
      </p>
    </aside>
  );
}
