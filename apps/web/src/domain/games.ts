// Official assets and retrieval dates are recorded in docs/data-sources.md.
export const games = [
  {
    id: 'lol',
    name: 'League of Legends',
    shortName: 'LoL',
    image: '/games/lol.svg',
    available: true,
  },
  {
    id: 'cs2',
    name: 'Counter-Strike 2',
    shortName: 'CS2',
    image: '/games/cs2.svg',
    available: false,
  },
  { id: 'dota2', name: 'Dota 2', shortName: 'Dota', image: '/games/dota2.png', available: false },
] as const;
