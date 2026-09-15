import { useDeferredValue, useState } from 'react';
import { Check, Globe2, Search, Users } from 'lucide-react';
import type { Catalog } from '@/domain/schemas';
import { catalogDate, normalize } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';
import { Button } from '@/components/ui/button';
export function CatalogDialog({
  open,
  onClose,
  catalog,
  selectedLeague,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  catalog: Catalog;
  selectedLeague: string;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState<'leagues' | 'teams'>('leagues');
  const term = normalize(useDeferredValue(search));
  const leagues = catalog.leagues.filter((l) => normalize(`${l.name} ${l.region}`).includes(term));
  const teams = catalog.teams.filter((t) =>
    normalize(
      `${t.name} ${t.code} ${catalog.leagues.find((l) => l.id === t.leagueId)?.name}`,
    ).includes(term),
  );
  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title="Tout l’univers LoL"
      description={`${catalog.leagues.length} compétitions · ${catalog.teams.length} équipes dans ce référentiel`}
      className="catalog-dialog"
    >
      <div className="catalog-controls">
        <div className="segment-control" aria-label="Type de catalogue">
          <button type="button" aria-pressed={tab === 'leagues'} onClick={() => setTab('leagues')}>
            <Globe2 size={16} />
            Ligues
          </button>
          <button type="button" aria-pressed={tab === 'teams'} onClick={() => setTab('teams')}>
            <Users size={16} />
            Équipes
          </button>
        </div>
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="Rechercher dans le catalogue"
            placeholder={
              tab === 'leagues' ? 'Rechercher une ligue, une région…' : 'Rechercher une équipe…'
            }
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div className="catalog-list">
        {tab === 'leagues' && (
          <Button
            variant="ghost"
            className="catalog-all"
            onClick={() => {
              onSelect('all');
              onClose();
            }}
          >
            <Globe2 size={18} />
            Toutes les compétitions{selectedLeague === 'all' && <Check size={17} />}
          </Button>
        )}
        {tab === 'leagues'
          ? leagues.map((league) => (
              <button
                type="button"
                className="catalog-item"
                key={league.id}
                onClick={() => {
                  onSelect(league.id);
                  onClose();
                }}
              >
                <Logo src={league.image} name={league.name} league />
                <span>
                  <strong>{league.name}</strong>
                  <small>{league.region}</small>
                </span>
                <span className="catalog-count">
                  {catalog.teams.filter((t) => t.leagueId === league.id).length} équipes
                </span>
                {selectedLeague === league.id && <Check size={16} className="text-accent" />}
              </button>
            ))
          : teams.map((team) => (
              <div className="catalog-item" key={team.id}>
                <Logo src={team.image} name={team.name} code={team.code} />
                <span>
                  <strong>{team.name}</strong>
                  <small>
                    {catalog.leagues.find((l) => l.id === team.leagueId)?.name ?? 'International'}
                  </small>
                </span>
                <span className="catalog-count">{team.code}</span>
              </div>
            ))}
        {(tab === 'leagues' ? leagues : teams).length === 0 && (
          <p className="catalog-empty">Aucun résultat pour cette recherche.</p>
        )}
      </div>
      <p className="catalog-footnote">
        Source :{' '}
        <a href={catalog.source} target="_blank" rel="noreferrer">
          LoL Esports
        </a>{' '}
        · relevé du {catalog.retrievedAt ? catalogDate(catalog.retrievedAt) : 'chargement en cours'}
        . Les équipes correspondent aux identités et rencontres publiées dans ces sources ; le
        circuit amateur peut être incomplet.
      </p>
    </Modal>
  );
}
