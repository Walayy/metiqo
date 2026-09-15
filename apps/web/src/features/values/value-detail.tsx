import { Bookmark, Check, Info } from 'lucide-react';
import type { Catalog, Opportunity } from '@/domain/schemas';
import { bestOffer, expectedValue, fairOdds, marketLabel, valueOf } from '@/domain/value';
import { decimal, percent, shortDate, time } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
import { OddsChart } from '@/components/ui/odds-chart';
export function ValueDetail({
  item,
  catalog,
  saved,
  onSave,
  onClose,
}: {
  item: Opportunity | null;
  catalog: Catalog;
  saved: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  if (!item) return null;
  const home = catalog.teams.find((t) => t.id === item.homeId)!;
  const away = catalog.teams.find((t) => t.id === item.awayId)!;
  const pick = catalog.teams.find((t) => t.id === item.pickId)!;
  const league = catalog.leagues.find((l) => l.id === item.leagueId)!;
  const best = bestOffer(item);
  return (
    <Modal
      open={!!item}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="L’opportunité en détail"
      description={`${league.name} · ${shortDate(item.startsAt)} à ${time(item.startsAt)} · Match simulé`}
      className="detail-drawer"
    >
      <div className="detail-scroll">
        <div className="detail-match">
          <div>
            <Logo src={home.image} name={home.name} />
            <strong>{home.code}</strong>
            <span>{home.name}</span>
          </div>
          <span className="detail-versus">
            VS<small>{item.format}</small>
          </span>
          <div>
            <Logo src={away.image} name={away.name} />
            <strong>{away.code}</strong>
            <span>{away.name}</span>
          </div>
        </div>
        <div className="detail-selection">
          <span>{marketLabel(item.market)}</span>
          <strong>{pick.name}</strong>
          <span className="value-badge">+{percent(valueOf(item))} de value</span>
        </div>
        <div className="detail-metrics">
          <div>
            <span>Probabilité estimée</span>
            <strong>{percent(item.probability * 100, 0)}</strong>
          </div>
          <div>
            <span>Cote juste</span>
            <strong>{decimal(fairOdds(item.probability))}</strong>
          </div>
          <div>
            <span>Meilleure cote</span>
            <strong className="text-accent">{decimal(best.odds)}</strong>
          </div>
        </div>
        <section className="detail-section">
          <h3>
            Comparer les cotes <span>Simulation</span>
          </h3>
          <div className="offers-table">
            <div className="offer-head">
              <span>Bookmaker</span>
              <span>Cote</span>
              <span>Value</span>
            </div>
            {[...item.offers]
              .sort((a, b) => b.odds - a.odds)
              .map((offer) => (
                <div className="offer-row" key={offer.bookmaker}>
                  <strong>
                    <span className={`bookmaker-icon bookmaker-${offer.bookmaker.toLowerCase()}`}>
                      {offer.bookmaker.slice(0, 1)}
                    </span>
                    {offer.bookmaker}
                    {offer === best && <Check size={14} className="text-accent" />}
                  </strong>
                  <span>{decimal(offer.odds)}</span>
                  <span
                    className={expectedValue(item.probability, offer.odds) > 0 ? 'text-accent' : ''}
                  >
                    {expectedValue(item.probability, offer.odds) > 0 ? '+' : ''}
                    {percent(expectedValue(item.probability, offer.odds))}
                  </span>
                </div>
              ))}
          </div>
        </section>
        <section className="detail-section">
          <h3>
            Évolution de la meilleure cote <span>Simulée</span>
          </h3>
          <OddsChart history={item.history} />
        </section>
        <div className="formula-note">
          <Info size={17} />
          <div>
            <strong>Le calcul, en toute transparence</strong>
            <p>
              ({decimal(item.probability, 2)} × {decimal(best.odds)} − 1) × 100 = +
              {percent(valueOf(item))}. La probabilité est fictive ; aucun modèle prédictif n’est
              connecté.
            </p>
          </div>
        </div>
      </div>
      <div className="detail-footer">
        <Button variant={saved ? 'secondary' : 'primary'} onClick={onSave}>
          <Bookmark size={17} className={saved ? 'bookmark-filled' : ''} />
          {saved ? 'Retirer des favoris' : 'Suivre cette value'}
        </Button>
        <span>Enregistré sur cet appareil</span>
      </div>
    </Modal>
  );
}
