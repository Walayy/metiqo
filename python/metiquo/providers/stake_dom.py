"""Extraction du DOM public Stake : aucune lecture du store JS ou du trafic réseau."""

EXTRACT_DOM = r"""() => {
  const root = document.querySelector('#main-content');
  if (!root) throw new Error('STAKE_DOM_MISSING');
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const visible = node => node.getClientRects().length > 0;
  const time = root.querySelector('[data-table="time"]');
  const parentPath = location.pathname.replace(/\/$/, '').split('/').slice(0, -1).join('/');
  const competition = Array.from(document.querySelectorAll('a[href]'))
    .find(a => a.getAttribute('href') === parentPath);
  const participants = Array.from(root.querySelectorAll('[data-testid="competitor-item"]'))
    .map(n => clean(n.closest('[role="group"]')?.getAttribute('aria-label'))).filter(Boolean);
  return {
    url: location.origin + location.pathname,
    competition: clean(competition?.textContent),
    participants: [...new Set(participants)],
    displayedStart: clean(time?.parentElement?.textContent),
    scores: Array.from(root.querySelectorAll('[data-testid="score-ticker-item"]'))
      .map(n => clean(n.textContent)),
    tabs: Array.from(root.querySelectorAll('button[data-testid^="tab-"]'))
      .map(n => n.getAttribute('data-testid')),
    links: Array.from(root.querySelectorAll('a[href]'))
      .map(n => n.getAttribute('href')),
    markets: Array.from(root.querySelectorAll('.secondary-accordion.level-2'))
      .filter(visible).map(n => ({
        label: clean(n.querySelector(':scope > .header [data-ds-text]')?.textContent),
        expanded: n.classList.contains('is-open'),
        rawText: clean(n.textContent),
        outcomes: Array.from(n.querySelectorAll('[data-testid="fixture-outcome"]'))
          .filter(visible).map(b => ({
            label: clean(b.getAttribute('aria-label')),
            displayedLabel: clean(
              b.querySelector('[data-testid="outcome-button-name"]')?.textContent),
            oddsText: clean(b.querySelector('[data-testid="fixture-odds"]')?.textContent),
            disabled: b.disabled || b.getAttribute('aria-disabled') === 'true',
            text: clean(b.textContent),
          })),
      })),
  };
}"""
