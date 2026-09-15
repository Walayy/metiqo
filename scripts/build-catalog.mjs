import { readFile, writeFile, mkdir } from 'node:fs/promises';
import sharp from 'sharp';

// This script only transforms public identities. It never imports real betting data.
const objects = JSON.parse(await readFile('.cache/riot-objects.json', 'utf8'));
const metadata = JSON.parse(await readFile('.cache/catalog-source-meta.json', 'utf8'));
const leagueMap = new Map();
for (const o of objects)
  if (o.__typename === 'League' && o.slug && o.image && o.slug !== 'tft_esports')
    leagueMap.set(o.id, o);
const majors = ['lck', 'lpl', 'lec', 'lcs', 'cblol-brazil', 'lcp'];
const international = ['worlds', 'msi', 'first_stand', 'ewc_lol', 'americas_cup'];
const labels = {
  lfl: 'LFL',
  lck_challengers_league: 'LCK CL',
  liga_portuguesa: 'LPLOL',
  lit: 'LIT',
  esports_balkan_league: 'EBL',
  hellenic_legends_league: 'HLL',
  roadoflegends: 'Road of Legends',
};
const leagues = [...leagueMap.values()].map((o) => ({
  id: o.id,
  slug: o.slug,
  name: labels[o.slug] ?? o.name,
  region: o.region ?? 'INTERNATIONAL',
  image: '',
  sourceImage: o.image.replace('http:', 'https:'),
  tier: majors.includes(o.slug)
    ? 'major'
    : international.includes(o.slug)
      ? 'international'
      : 'regional',
}));
const teamsMap = new Map();
for (const o of objects)
  if (o.__typename === 'Team' && o.name && o.homeLeague && o.image)
    teamsMap.set(o.id, {
      id: o.id,
      slug: o.slug,
      name: o.name,
      code: o.code,
      leagueId: o.homeLeague.id,
      image: '',
      sourceImage: o.image.replace('http:', 'https:'),
    });
const isCrossRegion = (event) =>
  [...international, 'emea_masters'].includes(leagueMap.get(event.league.id)?.slug);
const events = objects
  .filter((o) => o.__typename === 'EventMatch' && o.league && o.matchTeams)
  .sort((a, b) => Number(isCrossRegion(a)) - Number(isCrossRegion(b)));
for (const event of events) {
  for (const team of event.matchTeams) {
    const id = team.id.split(':').at(-1);
    if (id === '0' || !team.image || teamsMap.has(id) || !leagueMap.has(event.league.id)) continue;
    teamsMap.set(id, {
      id,
      slug: team.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      name: team.name,
      code: team.code,
      leagueId: event.league.id,
      image: '',
      sourceImage: team.image.replace('http:', 'https:'),
    });
  }
}
const teams = [...teamsMap.values()];
await mkdir('apps/web/public/logos', { recursive: true });
await mkdir('apps/web/src/mocks/data', { recursive: true });
const assets = [...leagues, ...teams];
let index = 0;
const failures = [];
async function download() {
  while (index < assets.length) {
    const asset = assets[index++];
    const ext = new URL(asset.sourceImage).pathname.split('.').at(-1).toLowerCase();
    const path = `/logos/${asset.id}.webp`;
    try {
      let bytes;
      try {
        bytes = await readFile(`apps/web/public/logos/${asset.id}.${ext}`);
      } catch {
        const response = await fetch(asset.sourceImage, { signal: AbortSignal.timeout(20000) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        bytes = Buffer.from(await response.arrayBuffer());
      }
      const signature = bytes.subarray(0, 12).toString('hex');
      if (
        !signature.startsWith('89504e47') &&
        !signature.startsWith('ffd8') &&
        !signature.startsWith('47494638') &&
        !signature.startsWith('52494646') &&
        !bytes.subarray(0, 300).toString().includes('<svg')
      )
        throw new Error('Format image non reconnu');
      await writeFile(
        `apps/web/public${path}`,
        await sharp(bytes)
          .resize(144, 144, { fit: 'inside', withoutEnlargement: true })
          .webp({ quality: 88 })
          .toBuffer(),
      );
      asset.image = path;
    } catch (error) {
      failures.push({ id: asset.id, name: asset.name, error: error.message });
    }
  }
}
await Promise.all(Array.from({ length: 8 }, download));
if (failures.length)
  throw new Error(`Import interrompu, catalogue conservé : ${JSON.stringify(failures)}`);
const catalog = {
  retrievedAt: metadata.retrievedAt,
  source: 'https://lolesports.com/en-US',
  leagues,
  teams,
};
await writeFile('apps/web/src/mocks/data/catalog.json', JSON.stringify(catalog, null, 2) + '\n');
console.log(
  JSON.stringify({
    leagues: leagues.length,
    teams: teams.length,
    failures,
    regionalTeams: teams
      .filter((t) => !majors.includes(leagues.find((l) => l.id === t.leagueId)?.slug))
      .map((t) => t.code + ' ' + t.name),
  }),
);
