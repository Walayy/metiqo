import { useId } from 'react';
import type { Opportunity } from '@/domain/schemas';
import { dateTime, decimal } from '@/lib/format';

export function OddsChart({
  history,
  compact = false,
  selectedAt,
  onSelect,
}: {
  history: Opportunity['history'];
  compact?: boolean;
  selectedAt?: string;
  onSelect?: (point: Opportunity['history'][number]) => void;
}) {
  const id = useId();
  const first = history[0]!;
  const last = history.at(-1)!;
  const values = history.map((point) => point.odds);
  const min = Math.min(...values) - 0.03;
  const max = Math.max(...values) + 0.03;
  const start = Date.parse(first.recordedAt);
  const duration = Date.parse(last.recordedAt) - start;
  const points = history.map(
    (point) =>
      [
        duration ? 38 + ((Date.parse(point.recordedAt) - start) / duration) * 272 : 174,
        84 - ((point.odds - min) / (max - min)) * 72,
      ] as const,
  );
  // A quote holds until the next observation. Avoid implying interpolated prices.
  const path = points.map(([x, y], index) => (index ? `H${x} V${y}` : `M${x},${y}`)).join(' ');
  const lastPoint = points.at(-1)!;
  const selectedIndex = history.findIndex((point) => point.recordedAt === selectedAt);
  const activePoint = points[selectedIndex];
  return (
    <div className={`odds-chart ${compact ? 'odds-chart--compact' : ''}`}>
      <svg
        viewBox="0 0 320 100"
        role="img"
        aria-labelledby={`${id}-title`}
        onPointerDown={
          onSelect
            ? (event) => {
                const bounds = event.currentTarget.getBoundingClientRect();
                const x = ((event.clientX - bounds.left) / bounds.width) * 320;
                const closest = points.reduce(
                  (best, point, index) =>
                    Math.abs(point[0] - x) < Math.abs(points[best]![0] - x) ? index : best,
                  0,
                );
                onSelect(history[closest]!);
              }
            : undefined
        }
      >
        <title
          id={`${id}-title`}
        >{`Cote Stake : ${history.length} relevé${history.length > 1 ? 's' : ''}, du ${dateTime(first.recordedAt)} au ${dateTime(last.recordedAt)}, de ${decimal(first.odds)} à ${decimal(last.odds)}.`}</title>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity=".18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((ratio) => (
          <g key={ratio}>
            <line
              x1="38"
              x2="310"
              y1={84 - ratio * 72}
              y2={84 - ratio * 72}
              stroke="var(--border)"
              strokeDasharray="3 5"
            />
            <text x="0" y={87 - ratio * 72} fill="var(--muted)" fontSize="9">
              {decimal(min + ratio * (max - min))}
            </text>
          </g>
        ))}
        {duration > 0 && <path d={`${path} L310,96 L38,96 Z`} fill={`url(#${id})`} />}
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
        <circle cx={lastPoint[0]} cy={lastPoint[1]} r="3.5" fill="var(--accent)" />
        {activePoint && (
          <g>
            <line
              x1={activePoint[0]}
              x2={activePoint[0]}
              y1="8"
              y2="96"
              stroke="var(--muted)"
              strokeDasharray="3 3"
            />
            <circle
              cx={activePoint[0]}
              cy={activePoint[1]}
              r="5"
              fill="var(--accent)"
              stroke="var(--surface)"
              strokeWidth="2"
            />
          </g>
        )}
      </svg>
      <div className="chart-labels">
        <span>{dateTime(first.recordedAt)}</span>
        {duration > 0 && <span>{dateTime(last.recordedAt)}</span>}
      </div>
      {history.length === 1 && <p className="history-empty">Premier relevé enregistré.</p>}
    </div>
  );
}
