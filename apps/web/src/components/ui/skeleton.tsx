export function ValuesSkeleton({ rows = 6 }: { rows?: number }) {
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
      {Array.from({ length: rows }, (_, index) => (
        <div className="value-row skeleton-row" key={index} aria-hidden="true">
          <div className="match-cell skeleton-match">
            <div className="team-pair">
              <span className="skeleton skeleton-logo" />
              <span className="skeleton skeleton-logo" />
            </div>
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
            <span className="skeleton skeleton-detail" />
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
        <div className="featured-eyebrow">
          <span className="skeleton skeleton-copy">LA VALUE À SUIVRE</span>
        </div>
        <div className="featured-teams">
          <div>
            <span className="logo-frame skeleton" />
            <strong className="skeleton skeleton-copy">XXX</strong>
          </div>
          <span>vs</span>
          <div>
            <span className="logo-frame skeleton" />
            <strong className="skeleton skeleton-copy">XXX</strong>
          </div>
        </div>
        <p className="featured-league">
          <span className="skeleton skeleton-copy">Ligue · BO3</span>
        </p>
        <div className="featured-value">
          <span className="skeleton skeleton-copy">
            +00,0<small>%</small>
          </span>
          <p>de value estimée</p>
        </div>
        <div className="featured-pick">
          <div>
            <span>NOTRE SÉLECTION</span>
            <strong>
              <span className="skeleton skeleton-copy">XXX</span>
              <small className="skeleton skeleton-copy">Vainqueur du match</small>
            </strong>
          </div>
          <strong className="skeleton skeleton-copy">0,00</strong>
        </div>
        <div className="featured-cta skeleton" />
      </div>
      <div className="trend-card trend-skeleton" aria-hidden="true">
        <div className="section-mini-title">
          <h3>Le mouvement de cote</h3>
        </div>
        <div className="trend-value">
          <strong className="skeleton skeleton-copy">0,00</strong>
        </div>
        <p>
          <span className="skeleton skeleton-copy">XXX · Stake</span>
        </p>
        <div className="odds-chart odds-chart--compact">
          <svg viewBox="0 0 320 100">
            <rect className="skeleton-plot" x="0" y="12" width="320" height="72" rx="4" />
          </svg>
          <div className="chart-labels">
            <span className="skeleton skeleton-copy">00 sept. · 00:00</span>
            <span className="skeleton skeleton-copy">00 sept. · 00:00</span>
          </div>
        </div>
      </div>
      <div className="learn-card" aria-hidden="true">
        <span className="learn-icon skeleton" />
        <span>
          <strong>Une cote. Une opportunité.</strong>
          <small>Comprendre la value en 1 minute</small>
        </span>
      </div>
      <p className="insights-note">Une value positive ne garantit pas un gain.</p>
    </>
  );
}
