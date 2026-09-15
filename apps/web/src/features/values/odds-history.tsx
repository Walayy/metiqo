import { useId, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Opportunity } from '@/domain/schemas';
import { dateTime, decimal, signedDecimal } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { OddsChart } from '@/components/ui/odds-chart';
import { historyInPeriod } from './history-range';
import type { HistoryPeriod } from './history-range';

export function OddsHistory({ history }: { history: Opportunity['history'] }) {
  const [period, setPeriod] = useState<HistoryPeriod>('all');
  const [recordedAt, setRecordedAt] = useState<string | null>(null);
  const id = useId();
  const points = historyInPeriod(history, period);
  const found = points.findIndex((point) => point.recordedAt === recordedAt);
  const index = found < 0 ? points.length - 1 : found;
  const selected = points[index]!;
  function select(next: number) {
    setRecordedAt(points[next]!.recordedAt);
  }
  return (
    <div className="odds-history">
      <div className="history-periods" role="group" aria-label="Période de l’historique">
        {(
          [
            ['all', 'Tout le suivi'],
            ['24h', '24 h'],
            ['7d', '7 jours'],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            aria-pressed={period === value}
            onClick={() => {
              setPeriod(value);
              setRecordedAt(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="history-period-note">Période se terminant au dernier relevé · Heure de Paris</p>
      <OddsChart
        history={points}
        selectedAt={selected.recordedAt}
        onSelect={(point) => setRecordedAt(point.recordedAt)}
      />
      <div className="history-point" id={`${id}-point`}>
        <div>
          <span>Relevé sélectionné</span>
          <time dateTime={selected.recordedAt}>{dateTime(selected.recordedAt)}</time>
        </div>
        <strong>{decimal(selected.odds)}</strong>
      </div>
      {points.length > 1 && (
        <div className="history-scrubber">
          <Button
            iconOnly
            variant="ghost"
            aria-label="Relevé précédent"
            disabled={index === 0}
            onClick={() => select(index - 1)}
          >
            <ChevronLeft size={18} />
          </Button>
          <label className="sr-only" htmlFor={`${id}-range`}>
            Parcourir les relevés de cote
          </label>
          <input
            id={`${id}-range`}
            type="range"
            min={0}
            max={points.length - 1}
            step={1}
            value={index}
            onChange={(event) => select(Number(event.target.value))}
            aria-valuetext={`${dateTime(selected.recordedAt)}, cote ${decimal(selected.odds)}, relevé ${index + 1} sur ${points.length}`}
          />
          <Button
            iconOnly
            variant="ghost"
            aria-label="Relevé suivant"
            disabled={index === points.length - 1}
            onClick={() => select(index + 1)}
          >
            <ChevronRight size={18} />
          </Button>
        </div>
      )}
      <details className="history-records">
        <summary>
          Historique des relevés <span>{points.length}</span>
        </summary>
        <div className="history-table-scroll">
          <table>
            <caption className="sr-only">
              Relevés Stake de la période sélectionnée, du plus récent au plus ancien
            </caption>
            <thead>
              <tr>
                <th scope="col">Date et heure</th>
                <th scope="col">Cote</th>
                <th scope="col">Variation</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((point, index) => {
                // Each period is a suffix; keep the preceding quote even outside the window.
                const previous = history[history.length - index - 2];
                return (
                  <tr key={point.recordedAt}>
                    <td>
                      <time dateTime={point.recordedAt}>{dateTime(point.recordedAt)}</time>
                      {!previous && <small>Enregistrement</small>}
                    </td>
                    <td>{decimal(point.odds)}</td>
                    <td>{previous ? signedDecimal(point.odds - previous.odds) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
