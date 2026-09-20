import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDirectory = path.join(root, 'apps', 'web', 'public', 'champions');
const manifestPath = path.join(root, 'apps', 'web', 'src', 'mocks', 'data', 'champions.json');
const dataDragon = 'https://ddragon.leagueoflegends.com';

async function readJson(url) {
  const response = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': 'Metiquo champion asset sync' },
  });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

async function readBytes(url) {
  const response = await fetch(url, {
    headers: { Accept: 'image/png', 'User-Agent': 'Metiquo champion asset sync' },
  });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
}

function digest(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

const versions = await readJson(`${dataDragon}/api/versions.json`);
if (!Array.isArray(versions) || typeof versions[0] !== 'string') {
  throw new Error('Data Dragon did not return a version list');
}
const version = versions[0];
const document = await readJson(`${dataDragon}/cdn/${version}/data/fr_FR/champion.json`);
if (!document || typeof document.data !== 'object' || document.data === null) {
  throw new Error(`Data Dragon champion manifest is invalid for ${version}`);
}

await mkdir(publicDirectory, { recursive: true });
const retrievedAt = new Date().toISOString().slice(0, 10);
const champions = Object.values(document.data)
  .filter((champion) => champion && typeof champion === 'object')
  .map((champion) => ({
    id: champion.id,
    key: champion.key,
    name: champion.name,
    image: `/champions/${champion.id}.png`,
    source: `${dataDragon}/cdn/${version}/img/champion/${champion.id}.png`,
    version,
    retrievedAt,
  }))
  .sort((left, right) => left.name.localeCompare(right.name, 'fr'));

for (const champion of champions) {
  const destination = path.join(publicDirectory, `${champion.id}.png`);
  const bytes = await readBytes(champion.source);
  let previous = null;
  try {
    previous = await readFile(destination);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  if (previous === null || digest(previous) !== digest(bytes)) {
    await writeFile(destination, bytes);
  }
}

const manifestTemporaryPath = `${manifestPath}.tmp-${process.pid}`;
await writeFile(manifestTemporaryPath, `${JSON.stringify(champions, null, 2)}\n`, 'utf8');
await rename(manifestTemporaryPath, manifestPath);
console.log(`Synced ${champions.length} champion icons from Data Dragon ${version}.`);
