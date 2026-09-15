import { mkdir, writeFile } from 'node:fs/promises';
// Public links exposed by the league filter at lolesports.com/en-US, retrieved 2026-09-14.
// Embedded JSON is parsed, never executed. No private API or credentials.
const slugs = [
  'lcs',
  'cblol-brazil',
  'americas_cup',
  'lec',
  'lck',
  'lpl',
  'lcp',
  'nacl',
  'emea_masters',
  'ljl-japan',
  'turkiye-sampiyonluk-ligi',
  'nlc',
  'lfl',
  'roadoflegends',
  'liga_portuguesa',
  'lit',
  'rift_legends',
  'les',
  'primeleague',
  'hitpoint_masters',
  'esports_balkan_league',
  'hellenic_legends_league',
  'arabian_league',
  'lck_challengers_league',
  'cd',
  'pcs',
  'vcs',
  'north_regional_league',
  'south_regional_league',
  'fls',
  'kespa_cup',
  'ewc_lol',
];
const urls = [
  'https://lolesports.com/en-US',
  ...slugs.map(
    (s) =>
      `https://lolesports.com/en-US/leagues/${['first_stand', 'msi', 'worlds', s].sort().join(',')}`,
  ),
];
const objects = new Map();
function visit(value) {
  if (!value || typeof value !== 'object') return;
  if (['League', 'Team', 'EventMatch'].includes(value.__typename) && value.id) {
    const key = `${value.__typename}:${value.id}`;
    if (!objects.has(key) || Object.keys(value).length > Object.keys(objects.get(key)).length)
      objects.set(key, value);
  }
  for (const child of Object.values(value)) visit(child);
}
await mkdir('.cache', { recursive: true });
let index = 0;
async function worker() {
  while (index < urls.length) {
    const url = urls[index++];
    const response = await fetch(url, { signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    const html = await response.text();
    let parsed = 0;
    for (const [, script] of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) {
      if (!script.startsWith('(window[Symbol.for("ApolloSSRDataTransport")]')) continue;
      const json = script
        .slice(script.indexOf('.push(') + 6, script.lastIndexOf(')'))
        .replace(/:undefined(?=[,}])/g, ':null');
      visit(JSON.parse(json));
      parsed++;
    }
    if (!parsed) throw new Error(`Format de source modifié : ${url}`);
  }
}
await Promise.all(Array.from({ length: 4 }, worker));
await writeFile('.cache/riot-objects.json', JSON.stringify([...objects.values()]));
await writeFile('.cache/catalog-source-urls.json', JSON.stringify(urls, null, 2));
await writeFile(
  '.cache/catalog-source-meta.json',
  JSON.stringify({ retrievedAt: new Date().toISOString().slice(0, 10) }, null, 2),
);
console.log(`Sources récupérées : ${urls.length}. Entités : ${objects.size}.`);
