() => {
  const main = document.querySelector('main');
  const selected = main
    ?.querySelector('button[aria-label="Select the match game"]')
    ?.textContent?.match(/Game\s+(\d+)/);
  if (!main || !selected || /Connecting|Loading/.test(main.innerText)) return null;
  const lists = [...main.querySelectorAll('ul')].filter((ul) =>
    ul.querySelector('a[href^="/stats/champion/"]'),
  );
  const teams = lists.map((list) => {
    const panel = list.parentElement;
    const summary = panel?.firstElementChild;
    const name = summary?.querySelector('span.truncate')?.textContent?.trim();
    const towerText = [...(summary?.querySelectorAll('p') || [])].find((p) =>
      /Towers/.test(p.textContent || ''),
    )?.textContent;
    const players = [...list.children].map((row) => {
      const champion = row.querySelector('a[href^="/stats/champion/"]');
      const img = champion?.querySelector('img');
      const paragraphs = [...row.querySelectorAll('p')].map((p) => p.textContent?.trim() || '');
      const kda = paragraphs.map((p) => p.match(/^(\d+)\s*\/\s*(\d+)\s*\/\s*(\d+)$/)).find(Boolean);
      const cs = paragraphs.map((p) => p.match(/^(\d+)\s*CS$/)).find(Boolean);
      return {
        name: paragraphs[0],
        champion: img?.getAttribute('alt') || null,
        championImage: img?.getAttribute('src') || '',
        level: /^\d+$/.test(champion?.textContent?.trim() || '')
          ? Number(champion.textContent.trim())
          : null,
        kills: kda ? Number(kda[1]) : null,
        deaths: kda ? Number(kda[2]) : null,
        assists: kda ? Number(kda[3]) : null,
        cs: cs ? Number(cs[1]) : null,
        // Displayed per-player gold is a difference, not total earned gold.
        gold: null,
      };
    });
    return {
      name,
      towers: towerText?.match(/^\s*(\d+)/) ? Number(towerText.match(/^\s*(\d+)/)[1]) : null,
      players,
    };
  });
  const heading = [...main.querySelectorAll('h2')].find(
    (h) => h.textContent?.trim() === 'Game stats',
  );
  const section = heading?.closest('section');
  const duration = [...(section?.querySelectorAll('p') || [])]
    .map((p) => p.textContent?.trim().match(/^(\d{1,3}):(\d{2})$/))
    .find(Boolean);
  return {
    number: Number(selected[1]),
    teams,
    durationSeconds: duration ? Number(duration[1]) * 60 + Number(duration[2]) : null,
  };
};
