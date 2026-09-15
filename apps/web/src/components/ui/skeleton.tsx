export function ValuesSkeleton() {
  return (
    <div
      className="values-skeleton"
      role="status"
      aria-label="Chargement des opportunités"
      aria-busy="true"
    >
      <span className="sr-only">Chargement des opportunités…</span>
      <div className="table-heading skeleton-heading" aria-hidden="true">
        <span>RENCONTRE</span>
        <span>SÉLECTION</span>
        <span>COTE</span>
        <span>PROBA.</span>
        <span>VALUE</span>
        <span />
      </div>
      {Array.from({ length: 6 }, (_, index) => (
        <div className="value-row skeleton-row" key={index} aria-hidden="true">
          <div className="match-cell skeleton-match">
            <div className="skeleton skeleton-logo" />
            <div className="skeleton-lines">
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          </div>
          <div className="pick-cell">
            <span className="skeleton skeleton-short" />
            <span className="skeleton skeleton-medium" />
          </div>
          <div className="odds-cell">
            <span className="skeleton skeleton-odds" />
            <span className="skeleton skeleton-short" />
          </div>
          <div className="probability-cell">
            <span className="skeleton skeleton-short" />
            <span className="skeleton skeleton-short" />
          </div>
          <div className="value-cell">
            <span className="skeleton skeleton-value" />
          </div>
          <div className="row-actions">
            <span className="skeleton skeleton-bookmark" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function InsightsSkeleton() {
  return (
    <>
      <div className="featured-card featured-skeleton" aria-hidden="true">
        <div className="skeleton skeleton-medium" />
        <div className="featured-teams">
          <span className="skeleton skeleton-team" />
          <span className="skeleton skeleton-team" />
        </div>
        <div className="skeleton skeleton-feature-number" />
        <div className="skeleton skeleton-feature-label" />
        <div className="skeleton skeleton-feature-pick" />
        <div className="skeleton skeleton-feature-button" />
      </div>
      <div className="trend-card trend-skeleton" aria-hidden="true">
        <div className="skeleton skeleton-medium" />
        <div className="skeleton skeleton-feature-label" />
        <div className="skeleton skeleton-chart" />
      </div>
    </>
  );
}
