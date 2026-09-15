import type { Catalog } from '@/domain/schemas';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { defaultFilters } from './filter-state';
import type { Filters } from './filter-state';
export function FilterDialog({
  open,
  onClose,
  filters,
  onChange,
  catalog,
  bookmakers,
}: {
  open: boolean;
  onClose: () => void;
  filters: Filters;
  onChange: (filters: Filters) => void;
  catalog: Catalog;
  bookmakers: string[];
}) {
  return (
    <Modal
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title="Affiner les opportunités"
      description="Les filtres s’appliquent à la liste et à ses indicateurs."
      className="filter-dialog"
    >
      <div className="filter-form">
        <div className="field-group">
          <label>Ligue</label>
          <Select
            label="Filtrer par ligue"
            value={filters.league}
            onChange={(league) => onChange({ ...filters, league })}
            options={[
              { value: 'all', label: 'Toutes les ligues' },
              ...catalog.leagues.map((l) => ({ value: l.id, label: l.name })),
            ]}
          />
        </div>
        <div className="field-group">
          <label>Marché</label>
          <Select
            label="Filtrer par marché"
            value={filters.market}
            onChange={(market) => onChange({ ...filters, market })}
            options={[
              { value: 'all', label: 'Tous les marchés' },
              { value: 'winner', label: 'Vainqueur du match' },
              { value: 'map1', label: 'Vainqueur de la carte 1' },
            ]}
          />
        </div>
        <div className="field-group">
          <label>Bookmaker disponible</label>
          <Select
            label="Filtrer par bookmaker"
            value={filters.bookmaker}
            onChange={(bookmaker) => onChange({ ...filters, bookmaker })}
            options={[
              { value: 'all', label: 'Tous les bookmakers' },
              ...bookmakers.map((b) => ({ value: b, label: b })),
            ]}
          />
          <small>Affiche les marchés proposés par ce bookmaker.</small>
        </div>
        <div className="field-group">
          <label htmlFor="min-value">
            Value minimum <strong>{filters.minValue} %</strong>
          </label>
          <input
            type="range"
            id="min-value"
            min="0"
            max="15"
            step="1"
            value={filters.minValue}
            onChange={(e) => onChange({ ...filters, minValue: Number(e.target.value) })}
          />
          <div className="range-labels">
            <span>Toutes les values</span>
            <span>15 % et plus</span>
          </div>
        </div>
      </div>
      <div className="filter-footer">
        <Button onClick={() => onChange(defaultFilters)}>Réinitialiser</Button>
        <Button variant="primary" onClick={onClose}>
          Voir les résultats
        </Button>
      </div>
    </Modal>
  );
}
