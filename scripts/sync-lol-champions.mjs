import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDirectory = path.join(root, 'apps', 'web', 'public', 'champions');
const manifestPath = path.join(root, 'apps', 'web', 'src', 'domain', 'data', 'champions.json');
const dataDragon = 'https://ddragon.leagueoflegends.com';

async function readJson(url) {
  const response = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': 'Metiquo champion asset sync' },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

async function readBytes(url) {
  const response = await fetch(url, {
    headers: { Accept: 'image/png', 'User-Agent': 'Metiquo champion asset sync' },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (
    bytes.length > 5_000_000 ||
    !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  ) {
    throw new Error(`Invalid champion PNG from ${url}`);
  }
  return bytes;
}

function digest(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

const versions = await readJson(`${dataDragon}/api/versions.json`);
if (!Array.isArray(versions) || typeof versions[0] !== 'string') {
  throw new Error('Data Dragon did not return a version list');
}
const version = versions[0];
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid Data Dragon version');
const document = await readJson(`${dataDragon}/cdn/${version}/data/fr_FR/champion.json`);
if (!document || typeof document.data !== 'object' || document.data === null) {
  throw new Error(`Data Dragon champion manifest is invalid for ${version}`);
}

await mkdir(path.join(publicDirectory, version), { recursive: true });
const retrievedAt = new Date().toISOString().slice(0, 10);
const champions = Object.values(document.data)
  .map((champion) => {
    if (
      !champion ||
      typeof champion !== 'object' ||
      typeof champion.id !== 'string' ||
      !/^[A-Za-z0-9]+$/.test(champion.id) ||
      typeof champion.name !== 'string' ||
      !champion.name.trim() ||
      typeof champion.key !== 'string' ||
      !/^\d+$/.test(champion.key)
    ) {
      throw new Error('Invalid Data Dragon champion identity');
    }
    return {
      id: champion.id,
      key: champion.key,
      name: champion.name,
      image: `/champions/${version}/${champion.id}.png`,
      source: `${dataDragon}/cdn/${version}/img/champion/${champion.id}.png`,
      version,
      retrievedAt,
    };
  })
  .sort((left, right) => left.name.localeCompare(right.name, 'fr'));
if (
  !champions.length ||
  new Set(champions.map((champion) => champion.id)).size !== champions.length
) {
  throw new Error('Empty or duplicate Data Dragon champion inventory');
}

for (const champion of champions) {
  const destination = path.join(publicDirectory, version, `${champion.id}.png`);
  const bytes = await readBytes(champion.source);
  let previous = null;
  try {
    previous = await readFile(destination);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  if (previous === null || digest(previous) !== digest(bytes)) {
    const temporary = `${destination}.tmp-${process.pid}`;
    await writeFile(temporary, bytes);
    await rename(temporary, destination);
  }
}

const manifestTemporaryPath = `${manifestPath}.tmp-${process.pid}`;
await writeFile(manifestTemporaryPath, `${JSON.stringify(champions, null, 2)}\n`, 'utf8');
await rename(manifestTemporaryPath, manifestPath);
console.log(`Synced ${champions.length} champion icons from Data Dragon ${version}.`);
