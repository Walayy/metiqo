# Contrat frontend / API

Base par défaut : `/api/v1`. Tous les endpoints sont des lectures JSON. MSW les intercepte uniquement en mode `mock`.

FastAPI implémente ces contrats dans `apps/api`. Docker conserve `VITE_DATA_MODE=mock` pour les données esport ; l’authentification utilise toujours l’API réelle. Le catalogue est publié par `sync-lol-catalog` (503 s’il manque) ; l’import d’administration reste disponible. `/opportunities` renvoie une liste vide tant qu’aucune rencontre à venir ne possède un marché actif, une estimation valide et une cote suffisamment récente. Aucun scrape n’est déclenché par une requête HTTP.

## Référentiel LoL versionné

- `GET /sources/lol-esports` : version active, `checkedAt`, vingt dernières exécutions avec statuts, erreurs et bilans de collecte.
- `GET /sources/lol-esports/reference` : `versionId`, `sha256`, `retrievedAt` et `document` de la version active ; paramètre optionnel `versionId` pour une version conservée. 503 si aucune version active, 404 pour une version inconnue.
- `document` contient la projection `catalog`, les `entities` avec attributs source et URLs, les `affiliations` datées, `leagueAssignment`, la couverture et les empreintes des images. Les affiliations distinguent `home`, `tournament` et `match` ; une relation de saison non sourcée reste `null`.
- `GET /catalog/logos/{sha256}.webp` sert uniquement les images locales du worker, avec ETag et cache immuable. Un nom invalide ou absent renvoie 404 ; une validation `If-None-Match` correspondante renvoie 304.

`GET /catalog` conserve son contrat ci-dessous et lit un seul document versionné pour éviter de mélanger deux publications. Les identités historiques demeurent en base. Dans la projection actuelle, un `leagueId` sans `homeLeague` source désigne un regroupement par participation observée ; consulter `leagueAssignment` et `affiliations` pour connaître sa nature. L’interface demeure en mock ; son raccordement futur devra présenter cette distinction. Voir [collectors.md](collectors.md).

## Données Oracle’s Elixir

| Route sous `/api/v1`                           | Réponse                                                                        |
| ---------------------------------------------- | ------------------------------------------------------------------------------ |
| `/sources/oracles-elixir`                      | Les 20 dernières collectes : périmètre, dates, statut, erreur et bilan         |
| `/sources/oracles-elixir/datasets`             | Versions actives, IDs Drive, SHA-256, années, colonnes, tailles, lignes, dates |
| `/sources/oracles-elixir/datasets/{year}/rows` | Lignes brutes paginées, `versionId`, `sha256` et `nextAfter`                   |
| `/sources/oracles-elixir/datasets/{year}/file` | CSV conservé, avec ETag SHA-256 ; lecture sans requête Google                  |

Les lignes acceptent `limit` de 1 à 200, `gameId`, `after` et `versionId`. La première page choisit la version active ; les suivantes doivent reprendre le `versionId` renvoyé pour éviter de mélanger deux versions pendant une actualisation. `nextAfter: null` indique la fin. Le fichier accepte aussi `versionId` pour retrouver une ancienne version. Les métadonnées portent des dates UTC ; les valeurs CSV sont conservées comme chaînes source, sans fuseau horaire inventé.

La documentation interactive est `/api/docs` et le schéma `/api/openapi.json`. Les sondes internes sont `/health/live` et `/health/ready`. Les erreurs de base ou d’artefact manquant renvoient 503, les années/versions inconnues 404 et les paramètres invalides 422. Il n’existe aucune route HTTP publique de mutation.

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

## Authentification réelle — `/api/v1/auth`

Toujours sur la même origine, y compris en mode mock. Aucun handler MSW pour ces routes. Aucun mot de passe ni token dans le JSON. Toutes les réponses sont `Cache-Control: no-store` ; les POST exigent une origine autorisée et `X-Metiquo-Auth: 1`. Les corps JSON refusent les champs supplémentaires.

| Endpoint             | Corps                                 | Réponse                                                                            |
| -------------------- | ------------------------------------- | ---------------------------------------------------------------------------------- |
| `POST /request-code` | `{ email: string }`                   | `{ challengeId: UUID, expiresAt: ISO, resendAt: ISO }`, cookie HttpOnly de demande |
| `POST /verify-code`  | `{ challengeId: UUID, code: string }` | Session ci-dessous ; code exactement six chiffres ASCII, zéros initiaux préservés  |
| `GET /session`       | —                                     | Session authentifiée ou `{ user: null, expiresAt: null }`                          |
| `POST /logout`       | `{}` ou vide                          | 204 ; révocation serveur et suppression des cookies                                |

```ts
interface Session {
  user: null | {
    id: string;
    email: string;
    role: 'user' | 'admin';
    createdAt: string; // ISO avec fuseau
  };
  expiresAt: string | null; // minimum de l’expiration absolue et de l’expiration par inactivité
}
```

Erreurs : 400 code incorrect/expiré/consommé ou navigateur différent ; 403 origine/en-tête refusés ; 422 corps invalide ; 429 limite atteinte avec `Retry-After` en secondes ; 503 SMTP ou base indisponible. L’email et le code reçus ne sont pas recopiés dans les erreurs de validation. La réponse à la demande de code ne révèle pas l’existence d’un compte.

Le client annule les requêtes abandonnées, applique un délai maximal de 20 secondes et ne renvoie pas automatiquement un POST. La lecture de session est vérifiée au retour du focus et toutes les 60 secondes en onglet actif. Voir [authentication.md](authentication.md) pour le détail des cookies et des limites.
