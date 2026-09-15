# Contrat frontend / future API

Base par défaut : `/api/v1`. Tous les endpoints sont des lectures JSON. MSW les intercepte uniquement en mode `mock`.

## `GET /catalog`

```ts
{
  retrievedAt: string; // YYYY-MM-DD
  source: string;
  leagues: Array<{
    id: string;
    slug: string;
    name: string;
    region: string;
    image: string;
    sourceImage: string;
    tier: 'major' | 'regional' | 'international';
  }>;
  teams: Array<{
    id: string;
    slug: string;
    name: string;
    code: string;
    leagueId: string;
    image: string;
    sourceImage: string;
  }>;
}
```

Pas d’enum d’équipes ou de ligues, pas de dépendance aux codes d’affichage pour l’identité. Les IDs de Riot sont des chaînes, jamais des nombres JS. Le backend pourra introduire un référentiel d’affiliations par saison sans figer les identités d’équipes.

## `GET /opportunities`

```ts
{
  generatedAt: string; // ISO UTC
  scenarioDate: string; // ISO UTC, date de référence du scénario mock
  items: Array<{
    id: string;
    leagueId: string;
    homeId: string;
    awayId: string;
    pickId: string;
    startsAt: string; // ISO UTC ; rendu Europe/Paris par le frontend
    format: 'BO1' | 'BO3' | 'BO5';
    market: 'winner' | 'map1';
    probability: number; // 0 < p < 1
    offers: Array<{ bookmaker: string; odds: number }>; // au moins une, odds > 1
    history: Array<{ label: string; odds: number }>; // au moins deux points
  }>;
}
```

Les éléments référencent des ligues et équipes existantes. La sélection est l’une des deux équipes. Les schémas exécutables Zod sont dans `apps/web/src/domain/schemas.ts`. Le chargement affiche un état d’erreur si un contrat ou une référence est invalide.

La meilleure cote est le maximum des offres. La value est `(probability * odds - 1) * 100`, et la cote juste `1 / probability`. Arrondir uniquement pour l’affichage. Le filtre « bookmaker disponible » sélectionne les marchés où ce bookmaker existe ; la colonne affiche toujours la meilleure offre du marché.

## Comportement réseau

AbortSignal est transmis à `fetch`. TanStack Query effectue une nouvelle tentative après un échec. Le catalogue reste en cache pour la session ; les opportunités ont une fraîcheur de 60 secondes. « Actualiser » relance les deux lectures en conservant les résultats existants pendant le chargement. Aucun polling ni trafic réel de bookmaker.

En mode API, les erreurs HTTP et les contrats invalides sont visibles. Il n’y a aucun fallback vers une fixture. La pagination et les filtres sont locaux pour ce prototype ; le backend devra les exposer côté serveur si le volume devient significatif.
