// Read-only snapshot for the manual Stake feasibility audit. Never clicks a selection.
() => {
  const contentRoot = document.querySelector('#main-content');
  const root = contentRoot ?? document.createElement('div');
  const text = (node) => node?.textContent?.trim().replace(/\s+/g, ' ') ?? '';
  const url = (value) => {
    try {
      const parsed = new URL(value, location.href);
      return parsed.origin + parsed.pathname;
    } catch {
      return null;
    }
  };
  const rect = (node) => {
    const r = node.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  };
  const links = (parent) =>
    [...parent.querySelectorAll('a[href]')]
      .filter((a) => /\/sports\/(esports|league-of-legends)(\/|$)/.test(a.href))
      .map((a) => ({ text: text(a), url: url(a.href) }));
  const number = (raw) => (/^[+-]?\d+(?:[.,]\d+)?$/.test(raw) ? raw.replace(',', '.') : null);
  const selections = (parent, title) =>
    [...parent.querySelectorAll('[data-testid="fixture-outcome"]')].map((button, index) => {
      const name = text(button.querySelector('[data-testid="outcome-button-name"]'));
      const odds = text(button.querySelector('[data-testid="fixture-odds"]'));
      const table = button.closest('.table-columns');
      const column = button.closest('.column');
      const columns = table
        ? [...table.children].filter((n) => n.classList.contains('column'))
        : [];
      const headings = columns.filter((n) => n.classList.contains('heading'));
      const cells = columns.filter((n) => !n.classList.contains('heading'));
      const position = cells.indexOf(column);
      const heading =
        headings.length && position >= 0 ? headings[position % headings.length] : null;
      const hasNumericLine =
        /handicap|nombre|total|durée|duration|premier.*atteindre|first.*to/i.test(title);
      return {
        index,
        nameRaw: name,
        accessibleName: button.getAttribute('aria-label'),
        columnHeaderRaw: heading ? text(heading) : null,
        lineRaw: hasNumericLine && number(name) !== null ? name : null,
        line: hasNumericLine ? number(name) : null,
        oddsRaw: odds || null,
        decimalOdds: number(odds),
        disabled: button.disabled,
        text: text(button),
        rect: rect(button),
      };
    });
  const markets = [...root.querySelectorAll('.groups .secondary-accordion')].map((group) => {
    const header = group.querySelector(':scope > .header');
    const title = text(header?.querySelector('span[data-ds-text]')) || text(header);
    return {
      title,
      headerRaw: text(header),
      expanded: group.classList.contains('is-open'),
      text: text(group),
      columnHeadersRaw: [...group.querySelectorAll('.table-columns .column.heading')].map(text),
      selections: selections(group, title),
      controls: [...group.querySelectorAll('button:not([data-testid="fixture-outcome"])')].map(
        (b) => ({
          text: text(b),
          testId: b.getAttribute('data-testid'),
          disabled: b.disabled,
        }),
      ),
    };
  });
  const fixtures = [...root.querySelectorAll('[data-testid="fixture-preview"]')].map((fixture) => {
    const observedLinks = links(fixture);
    const eventLink = observedLinks.find((link) =>
      /\/sports\/league-of-legends\/[^/]+\/[^/]+\/\d+-[^/]+$/.test(link.url ?? ''),
    );
    const eventUrl = eventLink?.url;
    const parentUrl = eventUrl?.slice(0, eventUrl.lastIndexOf('/'));
    const categoryUrl = parentUrl?.slice(0, parentUrl.lastIndexOf('/'));
    return {
      event: eventLink
        ? { ...eventLink, idFromUrl: eventUrl.match(/\/(\d+)-[^/]+$/)?.[1] ?? null }
        : null,
      competition: observedLinks.find((link) => link.url === parentUrl) ?? null,
      category: observedLinks.find((link) => link.url === categoryUrl) ?? null,
      text: text(fixture),
      links: observedLinks,
      selections: selections(fixture, ''),
    };
  });
  return {
    contentRootFound: contentRoot !== null,
    url: url(location.href),
    title: document.title,
    viewport: { width: innerWidth, height: innerHeight },
    mainText: text(root),
    links: links(document),
    fixtures,
    tabs: [...root.querySelectorAll('.groups button[data-testid^="tab-"]')].map((b) => ({
      testId: b.getAttribute('data-testid'),
      text: text(b),
      classes: b.className,
      disabled: b.disabled,
    })),
    markets,
    listingControls: [...root.querySelectorAll('button')]
      .filter((b) => !b.closest('.groups') && !b.matches('[data-testid="fixture-outcome"]'))
      .map((b) => ({
        text: text(b),
        testId: b.getAttribute('data-testid'),
        label: b.getAttribute('aria-label'),
        disabled: b.disabled,
      })),
  };
};
