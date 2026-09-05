# Metiquo

[![CI](https://github.com/Walayy/metiqo/actions/workflows/ci.yml/badge.svg)](https://github.com/Walayy/metiqo/actions/workflows/ci.yml)

Metiquo est un projet personnel Dockerisé de pricing et de détection de value betting esport. Le MVP initial couvre exclusivement League of Legends et utilise Oracle’s Elixir comme unique source statistique LoL.

La spécification normative se trouve dans [`docs/specs/00_SFG_METIQUO.md`](docs/specs/00_SFG_METIQUO.md). Le plan d’exécution et le backlog se trouvent dans le même dossier. L’avancement vérifié est consigné dans [`docs/progress.md`](docs/progress.md).

## Outillage

- Node.js `24.20.0` et pnpm `11.25.0` ;
- Python `3.13.14` et uv ;
- GNU Make `4.4.1` ou une version compatible ;
- TypeScript strict, ESLint, Prettier et Playwright ;
- Ruff, mypy et pytest.

Les dépendances sont installées exclusivement depuis les lockfiles avec `pnpm install --frozen-lockfile` et `uv sync --frozen`.

## Démarrer en mock

Docker Desktop doit être démarré. Sur une machine neuve disposant de l’outillage ci-dessus, la démo complète se prépare depuis la racine du dépôt avec :

```console
pnpm install --frozen-lockfile
uv sync --frozen
make mock-demo
```

`make mock-demo` vérifie d’abord la graine déterministe et les 12 scénarios normatifs, construit le profil Compose `mock`, attend la santé des services puis applique les migrations. L’application est ensuite accessible sur `http://127.0.0.1:3000`. Ce profil ne contacte ni Oracle’s Elixir ni un fournisseur de cotes : toutes les données métier sont générées localement à partir de `MOCK_SEED` et isolées du mode réel.

Le parcours de démonstration couvre Opportunités, Événements, Modèles, Données, Administration, mapping et Paper trading. Pour vérifier les parcours critiques et l’accessibilité sur la stack démarrée :

```console
make test-e2e
```

Arrêter la démo sans supprimer ses volumes persistants avec `make down`.

## Parcours local reproductible

Docker Desktop doit être démarré. Depuis la racine du dépôt :

```console
pnpm install --frozen-lockfile
uv sync --frozen
make up
make db-migrate
```

L’API est alors disponible sur `http://127.0.0.1:8000`. Les sondes `GET /health` et `GET /ready` doivent répondre avec le statut HTTP `200` après la migration. L’application Next.js répond sur `http://127.0.0.1:3000` et expose sa propre sonde `GET /health`.

Arrêter la stack sans supprimer ses volumes persistants :

```console
make down
```

Les contrôles locaux, également destinés à la CI, sont :

```console
make format
make lint
make typecheck
make test
make openapi-check
make docker-build
```

`make test` exécute les tests de composants frontend puis la suite Python. `make test-migrations` exécute la suite PostgreSQL réelle quand `TEST_DATABASE_URL` est défini. `make test-e2e` exécute le parcours mock complet, l’audit axe A/AA, le contrôle CLS, les parcours clavier/tactiles et la régression visuelle desktop/tablette/mobile.

La CI appelle ces mêmes cibles locales. Toute modification d’une décision structurante de la SFG §33 exige un ADR accepté dans `docs/adr/`.

## Configuration serveur

Copier `.env.example` vers `.env`, puis remplacer uniquement les valeurs propres à l’environnement local. Le chargement typé est centralisé dans `metiquo.config` ; une valeur absente, incohérente ou invalide interrompt le démarrage avec le nom de la variable concernée, sans afficher sa valeur sensible.

`DISPLAY_TIMEZONE` contrôle uniquement le rendu. Les instants internes restent en UTC.

## Base de données

Dans la stack locale, `make db-migrate` applique les migrations à la base PostgreSQL. Hors Compose, après avoir défini `DATABASE_URL` pour une base vide, la commande équivalente est `uv run alembic upgrade head`. La révision initiale crée uniquement les schémas logiques `raw`, `core`, `odds`, `features`, `ml`, `signals` et `ops` ; elle n’insère aucune donnée.

Le mode réel conserve ces sept namespaces. Le mode mock traduit tous ses accès applicatifs vers le schéma physique séparé `mock` et interdit les accès réseau Oracle’s Elixir ou fournisseur de cotes avant appel du transport. Une factory liée à un mode refuse toute donnée portant l’autre mode.

`MOCK_SEED` fixe les identifiants et les valeurs des douze scénarios normatifs. Leur catalogue utilise les contrats métier communs, une horloge injectée et des timestamps relatifs ; il ne lit ni le réseau ni l’heure système implicitement.

## CLI Oracle’s Elixir

Après migration de PostgreSQL, la commande `oe` expose les opérations du pipeline. Le mode `real` utilise uniquement la découverte officielle, l’API Google Drive éventuellement authentifiée, le téléchargement public puis le miroir de snapshots validés. Le mode `mock` interdit ces transports et exige `--fixture` pour chaque synchronisation locale.

```console
uv run --frozen oe catalog refresh --json
uv run --frozen oe backfill --from-year 2014 --to-year 2026 --json
uv run --frozen oe sync --year 2026 --require-fresh --json
uv run --frozen oe verify --snapshot <uuid> --json
uv run --frozen oe diff --left <uuid> --right <uuid> --json
uv run --frozen oe rebuild-canonical --from 2025-01-01 --json
```

Les alias équivalents sont `make oe-catalog`, `make oe-backfill FROM=2014 TO=2026`, `make oe-sync YEAR=2026`, `make oe-sync-current REQUIRE_FRESH=1`, `make oe-validate SNAPSHOT=<uuid>`, `make oe-diff LEFT=<uuid> RIGHT=<uuid>` et `make oe-rebuild-canonical FROM=2025-01-01`. `JSON=1` active la sortie compacte destinée à la CI.

Les codes retour sont stables : `0` succès, `2` usage ou configuration invalide, `3` snapshot frais requis mais indisponible, `4` échec de source ou de pipeline, `5` intégrité du snapshot invalide et `6` backfill partiel. Les erreurs machine-readable contiennent toujours `ok=false` et un `errorCode` sans secret.

Un contenu téléchargé puis refusé par la validation physique, le contrat de schéma ou la qualité métier est écrit dans l’ObjectStore de quarantaine et lié au run en échec. Il ne déplace jamais `raw.source_catalog.current_snapshot_id`. Une réponse HTML de quota est refusée avant la création d’un snapshot ; avec `--allow-stale`, la commande annonce explicitement `degraded` ou `quarantined` et l’identifiant du dernier snapshot validé réutilisé.

### Gate P2 ingestion

`make test-ingestion` couvre les fixtures critiques, la reprise de backfill, l’atomicité PostgreSQL, le double run, la quarantaine et les politiques de fraîcheur. La variable `TEST_DATABASE_URL` doit désigner une instance PostgreSQL de test dont l’utilisateur peut créer une base temporaire :

```console
TEST_DATABASE_URL=postgresql+psycopg://metiqo:metiqo@127.0.0.1:55436/metiqo make test-ingestion
```

Le parcours démontrable séparément crée une base au nom aléatoire préfixé par « Metiquo gate », applique les migrations, rafraîchit le catalogue mock, exécute le backfill et les contrôles du gate, puis supprime uniquement cette base éphémère :

```console
uv run --frozen python infra/scripts/demo_ingestion_gate.py \
  --database-url "$TEST_DATABASE_URL" --json
```

Le rapport JSON contient l’empreinte de l’état canonique idempotent, le refus de la page quota, le snapshot de quarantaine, le snapshot stale réutilisé, le code `require-fresh`, l’invalidation rétroactive et la relecture du manifeste. Les fixtures sont synthétiques ; leur origine et leur couverture SFG §25.2 sont détaillées dans `tests/fixtures/oracles_elixir/README.md`.

## API de lecture mock

En mode mock, l’API expose les collections et détails versionnés sous `/api/v1` : opportunités avec explication, événements avec marchés et historique de cotes, modèles, backtests, paper bets, sources de données, ingestions, problèmes de qualité, jobs et mappings en attente. Les collections utilisent `offset` et `limit` et acceptent des filtres typés propres à leur domaine. Chaque réponse contient `dataMode`, `freshness`, `asOf` et `appVersion` dans `meta`.

Le contrat complet et reproductible est versionné dans `packages/contracts/openapi/v1.json`.

Le package `@metiquo/contracts` génère depuis ce fichier les DTO, le client Fetch et les options TanStack Query. `make openapi` régénère le contrat backend puis le client ; `make openapi-check` échoue si l’un des deux n’est plus synchronisé. Aucun DTO API n’est recopié à la main dans le frontend.

## Frontend et design system

L’application `apps/web` utilise Next.js et React avec TypeScript strict. Le package `@metiquo/ui` centralise les tokens de couleur, espacement, typographie, rayon, élévation et durée, ainsi que les primitives accessibles. Le provider TanStack Query est installé à la racine de l’application. Les animations d’interaction passent uniquement par `opacity` ou `transform` et respectent `prefers-reduced-motion`.

Pour travailler sans Docker :

```console
pnpm --filter @metiquo/web dev
```

Les actions mock de synchronisation, cycle de vie modèle, paper betting, décision de mapping et création d’alias exigent l’en-tête `Idempotency-Key`. Une même clé et une même requête retournent le résultat initial sans dupliquer l’effet ; réutiliser la clé avec un payload différent retourne un conflit. Ces actions restent locales au processus mock et alimentent `/api/v1/admin/audit-log` sans conserver la clé brute.

## Conteneurs locaux

`make up` démarre le profil Compose `mock`. L’API FastAPI expose les sondes `/health`, `/ready`, `/api/v1/system/status` et les lectures métier documentées ci-dessus. Le worker possède un cycle de vie avec arrêt gracieux, mais aucun scheduler ni job métier n’est encore activé. Le conteneur web sert le build standalone Next.js sous un utilisateur non privilégié et avec une racine en lecture seule.

Les ports web et API sont liés uniquement à `127.0.0.1`. PostgreSQL reste sur un réseau Docker interne. Le profil `production` ajoute le gateway HTTPS et `object-store` ajoute également MinIO ; ce dernier refuse de démarrer tant que ses identifiants ne sont pas fournis hors du dépôt.

Ce logiciel n’exécute aucun pari réel et ne garantit aucun gain.
