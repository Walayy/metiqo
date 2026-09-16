import { History, Info } from 'lucide-react';
import type { Catalog, Opportunity } from '@/domain/schemas';
import { currentQuote, oddsChange, fairOdds, marketLabel, valueOf } from '@/domain/value';
import { dateTime, decimal, signedDecimal, percent, shortDate, time } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';
import { OddsHistory } from './odds-history';
export function ValueDetail({
  item,
  open,
  catalog,
  onClose,
}: {
  item: Opportunity | null;
  open: boolean;
  catalog: Catalog;
  onClose: () => void;
}) {
  if (!item) return null;
  const home = catalog.teams.find((t) => t.id === item.homeId)!;
  const away = catalog.teams.find((t) => t.id === item.awayId)!;
  const pick = catalog.teams.find((t) => t.id === item.pickId)!;
  const league = catalog.leagues.find((l) => l.id === item.leagueId)!;
  const latest = currentQuote(item);
  const first = item.history[0]!;
  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title="L’opportunité en détail"
      description={`${league.name} · ${shortDate(item.startsAt)} à ${time(item.startsAt)}`}
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
          <span className="value-badge">{signedDecimal(valueOf(item), 1)} % de value</span>
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
            <span>Cote Stake</span>
            <strong className="text-accent">{decimal(latest.odds)}</strong>
          </div>
        </div>
        <section className="detail-section">
          <h3>
            <span className="history-title">
              <History size={16} /> Le suivi de cote
            </span>
            <span>Stake · Heure de Paris</span>
          </h3>
          <div className="history-summary">
            <div>
              <span>À l’enregistrement</span>
              <strong>{decimal(first.odds)}</strong>
              <time dateTime={first.recordedAt}>{dateTime(first.recordedAt)}</time>
            </div>
            <div>
              <span>Dernier relevé</span>
              <strong>{decimal(latest.odds)}</strong>
              <time dateTime={latest.recordedAt}>{dateTime(latest.recordedAt)}</time>
            </div>
            <div>
              <span>Écart de cote</span>
              <strong>{signedDecimal(oddsChange(item))}</strong>
              <small>depuis le début du suivi</small>
            </div>
          </div>
          <OddsHistory key={item.id} history={item.history} />
        </section>
        <div className="formula-note">
          <Info size={17} />
          <div>
            <strong>Le calcul, en toute transparence</strong>
            <p>
              ({decimal(item.probability, 2)} × {decimal(latest.odds)} − 1) × 100 ={' '}
              {signedDecimal(valueOf(item), 1)} %. Le calcul utilise la dernière cote relevée. Une
              value positive ne garantit pas un gain.
            </p>
          </div>
        </div>
      </div>
    </Modal>
  );
}
