// Read only rendered elements of the selected game; never inspect React state or fetch data.
(index) => {
  const tab = document.querySelector(`[data-testid="tab-${index}"][aria-selected="true"]`);
  const panel = tab && document.getElementById(tab.getAttribute('aria-controls'));
  const visible = (element) =>
    element &&
    !element.hidden &&
    element.getAttribute('aria-hidden') !== 'true' &&
    getComputedStyle(element).display !== 'none';
  if (!visible(panel)) return null;
  const section = (names) =>
    Array.from(panel.querySelectorAll('span, h2, h3'))
      .find((e) => names.includes(e.textContent.trim()))
      ?.closest('.card-component');
  const lineups = section(['Lineups', 'Compositions']);
  const bans = section(['Ban Phase', 'Phase de ban']);
  const images = (element) =>
    element ? Array.from(element.querySelectorAll('img[src*="/character/"]')) : [];
  const portrait = (image) => ({
    image: image.getAttribute('src') || '',
    label:
      image.getAttribute('title') ||
      image.getAttribute('aria-label') ||
      image.getAttribute('alt') ||
      '',
  });
  const picks = images(lineups);
  const banRow =
    bans &&
    Array.from(bans.children).find(
      (e) => Array.from(e.children).filter((child) => images(child).length).length === 2,
    );
  const columns = banRow ? Array.from(banRow.children).filter((e) => images(e).length) : [];
  const draft = columns.flatMap((column, side) =>
    images(column).map((image) => ({
      ...portrait(image),
      teamId: side === 0 ? 'home' : 'away',
    })),
  );
  const directItems = Array.from(panel.querySelectorAll('*'))
    .filter(visible)
    .map((element) => ({
      text: Array.from(element.childNodes)
        .filter((node) => node.nodeType === 3)
        .map((node) => (node.textContent || '').trim())
        .filter(Boolean)
        .join(' '),
      className: typeof element.className === 'string' ? element.className : '',
    }))
    .filter((item) => item.text);
  const objectiveIndex = directItems.findIndex((item) =>
    ['Objectives', 'Objectifs'].includes(item.text),
  );
  const scoreItems = directItems.slice(0, objectiveIndex).filter((item) => /^\d+$/.test(item.text));
  return {
    number: index + 1,
    ready: picks.length === 10 && !!bans && images(panel).every((img) => img.complete),
    direct: directItems.map((item) => item.text),
    scoreClasses: scoreItems.slice(-2).map((item) => item.className),
    championImages: picks.map((img) => img.getAttribute('src') || ''),
    championNames: picks.map((img) => portrait(img).label),
    bans: draft,
  };
};
