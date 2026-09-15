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
  referenceDate: string; // ISO UTC, date de référence de la sélection
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
    bookmaker: 'stake';
    history: Array<{ recordedAt: string; odds: number }>; // ISO UTC, odds > 1, au moins un relevé
  }>;
}
```

Les éléments référencent des ligues et équipes existantes. La sélection est l’une des deux équipes. Les schémas exécutables Zod sont dans `apps/web/src/domain/schemas.ts`. Le chargement affiche un état d’erreur si un contrat ou une référence est invalide.

Stake est l’unique bookmaker accepté. Le premier relevé correspond à l’enregistrement du match dans Metiquo. Les dates doivent être strictement croissantes et uniques ; les intervalles peuvent être irréguliers et traverser plusieurs jours. Un seul relevé est valide. Une cote inchangée peut être enregistrée à une nouvelle date.

La cote courante est celle du **dernier relevé**, même si elle baisse. Aucun champ séparé de cote courante, d’écart ou de value n’est stocké. La value est `(probability * odds - 1) * 100`, et la cote juste `1 / probability`. Arrondir uniquement pour l’affichage. L’écart depuis l’enregistrement est la dernière cote moins la première. L’historique représente des relevés de cote, pas des probabilités estimées passées ; aucune value historique n’est inventée.

Le contrat est identique en modes mock et API, sans champ spécifique à un badge de démonstration. L’ancien contrat `offers`/`history.label` et le champ `scenarioDate` sont remplacés. Les identifiants existants de fixtures restent inchangés pour préserver les favoris locaux.

## Comportement réseau

AbortSignal est transmis à `fetch`, combiné à un délai maximal de 15 secondes. TanStack Query effectue une nouvelle tentative après un échec. Le catalogue reste en cache pour la session ; les opportunités ont une fraîcheur de 60 secondes. Les deux lectures sont préchargées avant le premier écran, avec ce même cache, puis utilisées sans double requête au montage. Un échec initial affiche l’état de nouvelle tentative sans redémarrage automatique au montage. « Actualiser » relance les deux lectures en conservant les résultats existants pendant le chargement. Aucun polling ni trafic réel de bookmaker.

En mode API, les erreurs HTTP et les contrats invalides sont visibles. Il n’y a aucun fallback vers une fixture. La pagination et les filtres sont locaux pour ce prototype ; le backend devra les exposer côté serveur si le volume devient significatif.
