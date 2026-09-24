import './status-dot.css';

export function StatusDot({
  tone = 'positive',
  active = true,
}: {
  tone?: 'positive' | 'live' | 'negative' | 'muted';
  active?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={`status-dot status-dot--${tone}${active ? ' is-pulsing' : ''}`}
    />
  );
}
