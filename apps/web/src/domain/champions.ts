import championManifest from './data/champions.json';

type ChampionAsset = (typeof championManifest)[number];

const compactName = (value: string) =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase();

const assets = new Map<string, ChampionAsset>();
for (const asset of championManifest) {
  assets.set(compactName(asset.id), asset);
  assets.set(compactName(asset.name), asset);
}

export const championAsset = (name: string | null, preferredImage = '') => {
  const officialImage = name ? (assets.get(compactName(name))?.image ?? '') : '';
  return officialImage || preferredImage;
};

export const championManifestVersion = championManifest[0]?.version ?? null;
