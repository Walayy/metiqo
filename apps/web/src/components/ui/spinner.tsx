export function Spinner({
  label = 'Chargement en cours',
  fixed = false,
}: {
  label?: string;
  fixed?: boolean;
}) {
  return (
    <div
      className={fixed ? 'activity-indicator' : 'loading-indicator'}
      role="status"
      aria-label={label}
    >
      <span className="spinner" aria-hidden="true" />
    </div>
  );
}
