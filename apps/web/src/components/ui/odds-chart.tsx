import { useId } from 'react';
import type { Opportunity } from '@/domain/schemas';
import { decimal } from '@/lib/format';
export function OddsChart({
  history,
  compact = false,
}: {
  history: Opportunity['history'];
  compact?: boolean;
}) {
  const id = useId();
  const values = history.map((h) => h.odds);
  const min = Math.min(...values) - 0.025;
  const max = Math.max(...values) + 0.025;
  const points = values.map(
    (value, index) =>
      [(index / (values.length - 1)) * 280, 72 - ((value - min) / (max - min)) * 58] as const,
  );
  const path = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return (
    <div className={`odds-chart ${compact ? 'odds-chart--compact' : ''}`}>
      <svg
        viewBox="0 0 280 92"
        role="img"
        aria-label={`Cotes simulées : ${history.map((h) => `${h.label}, ${decimal(h.odds)}`).join(' ; ')}`}
      >
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity=".2" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[20, 48, 76].map((y) => (
          <line
            key={y}
            x1="0"
            x2="280"
            y1={y}
            y2={y}
            stroke="var(--border)"
            strokeDasharray="3 5"
          />
        ))}
        <path d={`${path} L280,90 L0,90 Z`} fill={`url(#${id})`} />
        <path
          d={path}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.3"
          strokeLinejoin="round"
        />
        {points.at(-1) && (
          <circle cx={points.at(-1)![0]} cy={points.at(-1)![1]} r="3.5" fill="var(--accent)" />
        )}
      </svg>
      <div className="chart-labels">
        <span>{history[0]?.label}</span>
        <span>{history[Math.floor(history.length / 2)]?.label}</span>
        <span>{history.at(-1)?.label}</span>
      </div>
    </div>
  );
}
