// Public event state and identity are checked before touching market/odds nodes.
({ mode, game, guardSeconds = 0 }) => {
  const root = document.querySelector('#main-content');
  const text = (e) => e?.textContent?.trim().replace(/\s+/g, ' ') ?? '';
  const observed = new Date().toISOString();
  const cleanUrl = (value) => {
    if (typeof value !== 'string' || !value) return null;
    try {
      const u = new URL(value, location.href);
      return u.origin + u.pathname;
    } catch {
      return null;
    }
  };
  const eventPattern = new RegExp(`/fr/sports/${game}/([^/]+)/([^/]+)/(\\d+)-[^/]+$`);
  const metadataFor = (url, container) => {
    const match = new URL(url).pathname.match(eventPattern);
    if (!match) return null;
    const anchors = [...(container?.querySelectorAll('a[href]') ?? [])];
    const parentUrl = url.slice(0, url.lastIndexOf('/'));
    const categoryUrl = parentUrl.slice(0, parentUrl.lastIndexOf('/'));
    const live =
      !!container?.querySelector('.variant-live') ||
      /^(en direct|live)$/i.test(text(container?.querySelector('.fixture-details .badge')));
    const closed = /^(terminé|finished|closed)$/i.test(
      text(container?.querySelector('.fixture-details .badge')),
    );
    const names = [...(container?.querySelectorAll('[role="group"][aria-label]') ?? [])]
      .filter((e) => e.querySelector('[data-testid="competitor-item"]'))
      .map((e, position) => ({
        name: e.getAttribute('aria-label'),
        position,
        source_id: e.getAttribute('data-competitor-id'),
        image_url: cleanUrl(
          e.querySelector('[data-testid="competitor-image"]')?.getAttribute('src'),
        ),
      }));
    return {
      game,
      source_id: match[3],
      url,
      competition_key: new URL(parentUrl).pathname,
      competition_name: text(anchors.find((e) => cleanUrl(e.href) === parentUrl)) || null,
      category_name: text(anchors.find((e) => cleanUrl(e.href) === categoryUrl)) || null,
      participants: names,
      starts_at: null,
      status: closed ? 'closed' : live ? 'live' : 'unknown',
      observed_at: observed,
      raw: { listing_time: text(container?.querySelector('.fixture-details')), live_marker: live },
    };
  };
  if (mode === 'listing' || mode === 'hub') {
    const fixtures = [...(root?.querySelectorAll('[data-testid="fixture-preview"]') ?? [])]
      .map((e) => {
        const a = [...e.querySelectorAll('a[href]')].find((a) => eventPattern.test(a.href));
        return a ? metadataFor(cleanUrl(a.href), e) : null;
      })
      .filter(Boolean);
    const more = [...(root?.querySelectorAll('button') ?? [])].find(
      (e) =>
        !e.disabled &&
        /^(Charger Plus|Afficher plus)$/i.test(text(e)) &&
        !e.closest('[data-testid="fixture-outcome"]'),
    );
    return {
      url: cleanUrl(location.href),
      observed_at: observed,
      ready:
        !!root &&
        (fixtures.length > 0 ||
          (mode === 'hub' && !!root.querySelector('[data-testid="fixture-preview"]')) ||
          (!root.querySelector('[data-testid="fixture-outcome"]') &&
            /Aucun (match|événement)|No events/i.test(text(root)))),
      fixtures,
      links: [...document.querySelectorAll('a[href]')]
        .map((a) => cleanUrl(a.href))
        .filter((u) => u?.startsWith('https://stake.bet/fr/sports/')),
      more: more ? text(more) : null,
    };
  }
  const url = cleanUrl(location.href);
  const groups = root?.querySelector('.groups');
  const header = groups?.closest('.content-wrapper')?.querySelector(':scope > div:first-child');
  const metadata = metadataFor(url, header);
  if (!metadata) return null;
  const documents = [];
  const visit = (value) => {
    if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === 'object') {
      if (
        value['@type'] === 'SportsEvent' &&
        cleanUrl(value.url) &&
        new URL(value.url).pathname === new URL(url).pathname
      )
        documents.push(value);
      if (value.mainEntity) visit(value.mainEntity);
      if (value['@graph']) visit(value['@graph']);
    }
  };
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      visit(JSON.parse(script.textContent));
    } catch {
      /* Not valid public JSON-LD. */
    }
  }
  const event = documents.length === 1 ? documents[0] : null;
  if (event) {
    metadata.raw.jsonld = event;
    const start = event.startDate;
    if (
      typeof start === 'string' &&
      /(Z|[+-]\d\d:\d\d)$/.test(start) &&
      !Number.isNaN(Date.parse(start))
    ) {
      metadata.starts_at = start;
    }
    if (!metadata.participants.length && event.homeTeam?.name && event.awayTeam?.name) {
      metadata.participants = [event.homeTeam, event.awayTeam].map((t, position) => ({
        name: t.name,
        position,
        source_id: null,
        image_url: null,
      }));
    }
    metadata.competition_name = event.organizer?.name ?? null;
    metadata.raw.event_status = event.eventStatus ?? null;
  }
  const links = [...(root?.querySelectorAll('a[href]') ?? [])];
  const categoryPath = metadata.competition_key.slice(0, metadata.competition_key.lastIndexOf('/'));
  metadata.category_name =
    text(links.find((e) => new URL(e.href).pathname === categoryPath)) || null;
  const scores = [...(header?.querySelectorAll('[data-testid="score-ticker-item"]') ?? [])].map(
    text,
  );
  metadata.raw.score_markers = scores;
  metadata.raw.header_time = text(header?.querySelector('[data-table="time"]')?.parentElement);
  const eventStatus = typeof event?.eventStatus === 'string' ? event.eventStatus : '';
  if (metadata.status === 'closed' || /Event(Cancelled|Completed|Postponed)$/.test(eventStatus)) {
    metadata.status = 'closed';
  } else if (metadata.status === 'live' || scores.some((s) => /^\d+$/.test(s))) {
    metadata.status = 'live';
  } else if (
    /EventScheduled$/.test(eventStatus) &&
    header &&
    scores.length === 2 &&
    scores.every((s) => s === '-')
  ) {
    metadata.status = 'scheduled';
  } else {
    metadata.status = 'unknown';
  }
  metadata.raw.time_reached = !!metadata.starts_at && Date.parse(metadata.starts_at) <= Date.now();
  const tabs = [...(groups?.querySelectorAll('button[data-testid^="tab-"]') ?? [])].map((e) => ({
    id: e.getAttribute('data-testid'),
    label: text(e),
    disabled: e.disabled,
  }));
  const selected = [...(groups?.querySelectorAll('button[data-testid^="tab-"]') ?? [])].find(
    (e) =>
      e.classList.contains('!state-layer-inverse') || e.getAttribute('aria-selected') === 'true',
  );
  const result = {
    metadata,
    tab: selected?.getAttribute('data-testid') ?? 'tab-main',
    tabs,
    markets: [],
  };
  // A live marker allows an unknown planned start. Unknown or closed states expose no quotes.
  if (
    mode === 'metadata' ||
    metadata.participants.length !== 2 ||
    !metadata.participants.every((p) => p.name?.trim()) ||
    metadata.participants[0].name.trim().toLocaleLowerCase() ===
      metadata.participants[1].name.trim().toLocaleLowerCase() ||
    (metadata.status !== 'live' &&
      (metadata.status !== 'scheduled' ||
        !metadata.starts_at ||
        Date.parse(metadata.starts_at) <= Date.now() + guardSeconds * 1000))
  )
    return result;
  const attrs = (e) =>
    Object.fromEntries(
      [...e.attributes]
        .filter((a) =>
          /^(data-(market|outcome|selection|specifier|fixture)-|aria-label)/.test(a.name),
        )
        .map((a) => [a.name, a.value]),
    );
  result.markets = [...(groups?.querySelectorAll('.secondary-accordion') ?? [])].map((group) => {
    const header = group.querySelector(':scope > .header');
    return {
      label: text(header?.querySelector('span[data-ds-text]')) || text(header),
      source_id: group.getAttribute('data-market-id'),
      attributes: attrs(group),
      expanded: group.classList.contains('is-open'),
      controls: [...group.querySelectorAll('button:not([data-testid="fixture-outcome"])')]
        .filter((b) => !b.disabled)
        .map(text),
      selections: [...group.querySelectorAll('[data-testid="fixture-outcome"]')].map((button) => {
        const table = button.closest('.table-columns');
        const column = button.closest('.column');
        const row = button.closest('.row');
        const rowHeading = row?.querySelector(':scope > .column.heading');
        const columns = [...(table?.children ?? [])].filter((e) => e.classList.contains('column'));
        const headings = columns.filter((e) => e.classList.contains('heading'));
        const cells = columns.filter((e) => !e.classList.contains('heading'));
        const position = cells.indexOf(column);
        const heading =
          headings.length && position >= 0 ? headings[position % headings.length] : null;
        const oddsText = text(button.querySelector('[data-testid="fixture-odds"]'));
        const suspended = /^(suspendu|suspended|fermé|closed|locked)$/i.test(oddsText);
        return {
          name: text(button.querySelector('[data-testid="outcome-button-name"]')),
          accessible_name: button.getAttribute('aria-label'),
          column: heading ? text(heading) : null,
          row_label: rowHeading ? text(rowHeading) : null,
          source_id:
            button.getAttribute('data-outcome-id') ?? button.getAttribute('data-selection-id'),
          odds_raw: suspended ? null : oddsText || null,
          disabled: button.disabled || button.getAttribute('aria-disabled') === 'true' ||
            suspended || !oddsText,
          attributes: attrs(button),
        };
      }),
    };
  });
  return result;
};
