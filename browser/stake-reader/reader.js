// DOM uniquement : pas de requête de données, de cookie, de store JS ni de jeton.
globalThis.metiquoReadStake = async (mode, expectedUrl) => {
  globalThis.metiquoAbortStake = false;
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const visible = (n) => n && n.getClientRects().length > 0;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const startedAt = new Date().toISOString();
  const deadline = Date.now() + 90000;
  const guard = () => {
    if (globalThis.metiquoAbortStake) throw new Error("CANCELLED");
    if (Date.now() > deadline) throw new Error("PAGE_TIMEOUT");
    if (location.origin + location.pathname !== expectedUrl || location.search || location.hash)
      throw new Error("UNEXPECTED_REDIRECT");
    if (/just a moment|access denied|attention required/i.test(document.title))
      throw new Error("ACCESS_CHALLENGE");
  };
  const until = async (ready) => {
    const end = Math.min(deadline, Date.now() + 15000);
    while (!ready()) {
      guard();
      if (Date.now() > end) throw new Error("PAGE_NOT_READY");
      await wait(150);
    }
    guard();
  };
  const expand = async () => {
    const seen = new Set();
    for (let step = 0; step <= 30; step++) {
      guard();
      const root = document.querySelector("#main-content");
      const closed = [
        ...root.querySelectorAll(".secondary-accordion:not(.is-open) > .header"),
      ].find(visible);
      const more = [...root.querySelectorAll('[data-testid="load-more"]')].find(visible);
      let all, label;
      for (const header of root.querySelectorAll(".secondary-accordion.level-2 > .header")) {
        label = clean(header.querySelector("[data-ds-text]")?.textContent);
        all = [...header.querySelectorAll("button")].find(
          (b) => visible(b) && clean(b.textContent) === "Tout",
        );
        if (all && !seen.has(label)) break;
        all = null;
      }
      if (!closed && !more && !all) return [];
      if (step === 30) return ["EXPANSION_LIMIT_REACHED"];
      if (closed) closed.click();
      else if (more) more.click();
      else {
        all.click();
        seen.add(label);
      }
      await wait(300);
    }
    return [];
  };
  await until(
    () =>
      visible(document.querySelector("#main-content")) &&
      [...document.querySelectorAll('a[href^="/fr/sports/league-of-legends/"]')].some(visible),
  );
  await wait(800);
  if (mode === "links") {
    const warnings = await expand();
    return { links: globalThis.metiquoExtractStake().links, warnings };
  }
  await until(() => visible(document.querySelector('[data-testid="tab-main"]')));
  const first = globalThis.metiquoExtractStake();
  if (!first.displayedStart) throw new Error("START_TIME_MISSING");
  const expectedTabs = first.tabs;
  if (expectedTabs[0] !== "tab-main" || expectedTabs.length > 10) throw new Error("TABS_CHANGED");
  const states = [],
    warnings = [];
  for (const tab of expectedTabs) {
    guard();
    if (tab !== "tab-main" && !/^tab-map-[1-5]$/.test(tab)) {
      warnings.push("UNSUPPORTED_TAB:" + tab);
      continue;
    }
    // Revenir à Principal est nécessaire lors des collectes périodiques.
    document.querySelector(`[data-testid="${tab}"]`).click();
    await until(() => {
      const labels = globalThis.metiquoExtractStake().markets.map((m) => m.label);
      return (
        labels.length &&
        (tab === "tab-main"
          ? labels.some((s) => !s.startsWith("Map "))
          : labels.every((s) => s.startsWith("Map " + tab.slice(8) + " ")))
      );
    });
    // Laisser finir une mise à jour déclenchée par le clic sur un onglet déjà actif.
    await wait(800);
    warnings.push(...(await expand()));
    const dom = globalThis.metiquoExtractStake();
    if (
      JSON.stringify(dom.participants) !== JSON.stringify(first.participants) ||
      dom.competition !== first.competition
    )
      throw new Error("EVENT_CHANGED");
    if (dom.markets.some((m) => !m.expanded || !m.outcomes.length))
      warnings.push("MARKETS_WITHOUT_VISIBLE_OUTCOMES");
    states.push({ tab, capturedAt: new Date().toISOString(), dom });
  }
  guard();
  return {
    url: expectedUrl,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    startedAt,
    observedAt: new Date().toISOString(),
    expectedTabs,
    states,
    warnings: [...new Set(warnings)],
  };
};
