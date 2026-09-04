# Journal d’avancement Metiquo

Ce fichier consigne uniquement des résultats effectivement vérifiés. La SFG reste la source de vérité normative.

## FND-001 — Initialiser le monorepo

- **Statut :** `DONE`
- **Dépendances vérifiées :** aucune dépendance ; dépôt initial limité au pack de spécifications.
- **Fichiers créés/modifiés :** `.editorconfig`, `.gitattributes`, `.gitignore`, `.node-version`, `.python-version`, `README.md`, `docs/progress.md`, `infra/scripts/verify_structure.py`, marqueurs `.gitkeep` dans les répertoires vides requis sous `apps/`, `services/`, `packages/`, `python/metiquo/`, `infra/` et `tests/`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** `python .\infra\scripts\verify_structure.py` ; recherche récursive des fichiers `*.ipynb` ; `python -m py_compile .\infra\scripts\verify_structure.py` ; `git init` ; `git branch -M main` ; `git ls-remote https://github.com/Walayy/metiqo.git` ; configuration de `origin` ; recherche exhaustive de l’ancien identifiant et contrôle des noms de fichiers ; `git diff --cached --check` hors Markdown normatif contenant des sauts de ligne intentionnels ; `git commit` ; `git status --short --branch`.
- **Résultat exact :** structure `OK` ; `NOTEBOOK_COUNT=0` ; compilation Python `OK` ; cache `__pycache__` correctement ignoré ; dépôt distant vérifié vide avant configuration ; renommage intégral du projet vers `Metiquo` vérifié (`OLD_NAME_COUNT=0`) ; commit initial créé sur `main` ; `git status` propre (`## main`) après bootstrap.
- **Blocker éventuel :** aucun. L’ancien dossier local `C:\Users\leotr\Documents\Projets\esport` est vide mais reste temporairement verrouillé par le processus Codex ; l’intégralité du dépôt se trouve dans `C:\Users\leotr\Documents\Projets\metiqo`.
- **ADR éventuel :** aucun ; l’arborescence applique directement la SFG.
- **Commit/hash :** `f4d5e61e2aa4b3406eb1b1b6c64bd2e7a8bafe2c` (`chore: bootstrap Metiquo monorepo`).

## FND-002 — Figer l’outillage et les dépendances

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-001` est `DONE` et le commit initial est présent sur `origin/main`.
- **Fichiers créés/modifiés :** `.node-version`, `.python-version`, `.prettierignore`, `.prettierrc.json`, `README.md`, `cspell.json`, `eslint.config.mjs`, `package.json`, `playwright.config.ts`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `pyproject.toml`, `tsconfig.json`, `uv.lock`, `python/metiquo/__init__.py`, `python/metiquo/py.typed`, `tests/test_tooling.py`, `infra/scripts/verify_structure.py`, `docs/specs/02_IMPLEMENTATION_BACKLOG.yaml`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** consultation des versions stables via les sources officielles et registres ; `pnpm install` pour générer `pnpm-lock.yaml` ; `uv sync --python 3.13.14` pour générer `uv.lock` ; suppression contrôlée des seuls répertoires générés `node_modules` et `.venv` ; `pnpm install --frozen-lockfile` ; `uv sync --frozen` ; `uv lock --check` ; `pnpm run spellcheck` ; `pnpm run format:check` ; `pnpm run lint` ; `pnpm run typecheck` ; `pnpm exec playwright --version` ; `uv run --frozen ruff format --check python services infra/scripts tests` ; `uv run --frozen ruff check python services infra/scripts tests` ; `uv run --frozen mypy` ; `uv run --frozen pytest` ; `uv run --frozen python --version`.
- **Résultat exact :** réinstallation depuis les lockfiles réussie avec pnpm `11.25.0` et CPython `3.13.14` ; `uv lock --check` résout 14 paquets sans modification ; CSpell contrôle 9 fichiers avec 0 erreur ; Prettier passe ; ESLint passe sans warning ; TypeScript `5.9.3` strict passe ; Playwright `1.62.1` est exécutable ; Ruff confirme 3 fichiers formatés et 0 erreur ; mypy strict contrôle 3 fichiers sans erreur ; pytest collecte et réussit 1 test en `0.01 s` ; aucun navigateur Playwright n’est téléchargé à ce ticket.
- **Blocker éventuel :** aucun. Le premier `uv sync` a révélé un shim `pyenv-win` non configuré ; uv utilise désormais explicitement sa distribution gérée CPython `3.13.14`. La version `3.13.15` publiée n’était pas disponible dans le catalogue de téléchargement de la version locale d’uv, donc la dernière version `3.13` effectivement installable et vérifiée a été figée sans mise à jour globale forcée d’uv.
- **ADR éventuel :** aucun ; le ticket applique directement la stack imposée par la SFG.
- **Commit/hash :** `da717de893c12b92949522410a8bbf4612de4274` (`chore: pin FND-002 toolchains`).

## FND-003 — Créer la configuration typée

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-002` est `DONE` et présent sur `origin/main`.
- **Fichiers créés/modifiés :** `.env.example`, `README.md`, `pyproject.toml`, `uv.lock`, `python/metiquo/config.py`, `tests/test_config.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** résolution contrôlée de `pydantic-settings==2.15.0` et `tzdata==2026.3` ; `uv lock` ; `uv lock --check` ; `uv sync --frozen` ; `pnpm run spellcheck` ; `pnpm run format:check` ; `pnpm run lint` ; `pnpm run typecheck` ; `uv run --frozen ruff format --check python services infra/scripts tests` ; `uv run --frozen ruff check python services infra/scripts tests` ; `uv run --frozen mypy` ; `uv run --frozen pytest`.
- **Résultat exact :** lock uv résolu à 21 paquets et synchronisé sans modification ; CSpell contrôle 9 fichiers avec 0 erreur ; Prettier passe ; ESLint passe sans warning ; TypeScript strict passe ; Ruff confirme 5 fichiers formatés et 0 erreur ; mypy strict contrôle 5 fichiers sans erreur ; pytest réussit 10 tests en `0.23 s`, dont configuration valide/invalide, garde `real` + provider mock, fuseau IANA, UTC interne, erreur de démarrage expurgée, masquage de l’URL de base et scan de `.env.example` sans secret.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le ticket ajoute une frontière de configuration sans modifier l’architecture.
- **Commit/hash :** `94d0b673965bbb6927782681b52efd7d14e59bc8` (`feat: add typed server configuration`).

## FND-004 — Créer PostgreSQL et les schémas logiques

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-003` est `DONE` et présent sur `origin/main`.
- **Fichiers créés/modifiés :** `alembic.ini`, `README.md`, `pyproject.toml`, `uv.lock`, `python/metiquo/db/__init__.py`, `python/metiquo/db/base.py`, `python/metiquo/db/schemas.py`, `python/metiquo/db/migrations/env.py`, `python/metiquo/db/migrations/script.py.mako`, `python/metiquo/db/migrations/versions/20260904_0001_create_logical_schemas.py`, `tests/test_database_conventions.py`, `tests/integration/test_migrations.py`, `docs/progress.md`.
- **Migrations :** révision initiale réversible `20260904_0001` ; création des schémas `raw`, `core`, `odds`, `features`, `ml`, `signals`, `ops` sans extension ni donnée.
- **Commandes/tests exécutés :** démarrage contrôlé de Docker Desktop ; conteneur jetable local `postgres:18` publié sur un port aléatoire ; attente `pg_isready` ; `TEST_DATABASE_URL=... uv run --frozen pytest tests/integration/test_migrations.py -vv` ; `uv run --frozen alembic current` ; contrôles SQL des schémas et tables ; arrêt et suppression automatique du conteneur jetable ; `pnpm install --frozen-lockfile` ; `uv lock --check` ; `uv sync --frozen` ; `pnpm run spellcheck` ; `pnpm run format:check` ; `pnpm run lint` ; `pnpm run typecheck` ; `uv run --frozen ruff format --check python services infra/scripts tests` ; `uv run --frozen ruff check python services infra/scripts tests` ; `uv run --frozen mypy` ; `uv run --frozen pytest` ; `uv run --frozen alembic history`.
- **Résultat exact :** test PostgreSQL réel réussi en `1.02 s` sur base vide avec séquence `upgrade head → downgrade base → upgrade head` ; révision courante `20260904_0001 (head)` ; sept schémas attendus présents ; `0` table métier et aucune donnée mock ; session vérifiée en UTC ; suite hors infrastructure : 12 tests réussis et 1 test d’intégration correctement ignoré sans `TEST_DATABASE_URL` ; Ruff, mypy strict, TypeScript strict, ESLint, Prettier et CSpell passent ; historique Alembic linéaire de `base` à `head`.
- **Blocker éventuel :** aucun. Docker Desktop était initialement arrêté ; il a été démarré et le test PostgreSQL réel a ensuite passé.
- **ADR éventuel :** aucun ; PostgreSQL, Alembic et les sept schémas sont imposés par la SFG. La convention applicative utilise des UUID et refuse tout datetime naïf avant persistance.
- **Commit/hash :** `b74f8fd05920d5bd38e8a0f258c2b4f4fad7e8ab` (`feat: add initial PostgreSQL schemas`).

## FND-005 — Créer Docker Compose minimal

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-004` est `DONE` et présent sur `origin/main`.
- **Fichiers créés/modifiés :** `.dockerignore`, `docker-compose.yml`, `README.md`, `pyproject.toml`, `infra/compose/python.Dockerfile`, `infra/compose/web.Dockerfile`, `infra/compose/bootstrap/api_health.py`, `infra/compose/bootstrap/mock_mode_check.py`, `infra/compose/bootstrap/worker.py`, `infra/compose/bootstrap/web-health.mjs`, `infra/gateway/Caddyfile`, `tests/integration/test_compose.py`, `docs/progress.md`.
- **Migrations :** aucune nouvelle migration.
- **Commandes/tests exécutés :** pulls et contrôle des digests des images Python, Node.js, uv, PostgreSQL, Caddy et MinIO ; `docker compose config --quiet` ; `docker compose config --profiles` ; inventaire des services pour les profils `mock`, `production` et `object-store` ; `docker compose --profile mock up -d --build --wait --wait-timeout 120` ; appels HTTP des contrôles de santé API/web ; contrôle des états de santé ; contrôles `id` et droits d’écriture dans les conteneurs ; scan des configurations et historiques d’images ; recherche des services interdits ; démarrage du gateway `production` et appel HTTPS interne ; test négatif `APP_DATA_MODE=real` avec le profil mock ; `uv run --frozen pytest` ; Ruff et mypy sur `python`, `services`, `infra` et `tests` ; arrêt Compose et suppression des volumes de test.
- **Résultat exact :** profils `mock`, `production` et `object-store` déclarés ; le profil mock démarre sans source externe avec PostgreSQL, API, worker et web sains et les deux gardes one-shot sorties en code `0` ; API et worker exécutés sous UID `10001`, web et gateway sous UID `1000` ; racines en lecture seule, volumes raw/modèles en lecture seule côté API et inscriptibles uniquement côté worker ; proxy HTTPS `production` vérifié avec statut `200` ; garde mock/réel vérifiée avec refus en code `1` ; `FORBIDDEN_SERVICE_COUNT=0` ; `IMAGE_SECRET_SCAN=OK` ; suite locale : 14 tests réussis et 1 test PostgreSQL correctement ignoré sans `TEST_DATABASE_URL` ; Ruff, mypy strict, TypeScript strict, ESLint, Prettier et CSpell passent. Le premier build a échoué proprement sur une collision de tag BuildKit entre trois builds parallèles ; des tags par rôle ont supprimé la course et deux builds complets suivants ont réussi. Le profil `object-store` est validé par Compose mais son démarrage réel n’est pas simulé sans identifiants MinIO. Après le smoke test, `REMAINING_CONTAINERS=0`, `REMAINING_VOLUMES=0` et `REMAINING_NETWORKS=0`.
- **Blocker éventuel :** aucun pour les critères FND-005. Les identifiants MinIO seront nécessaires uniquement pour démarrer le profil optionnel `object-store` et ne sont ni demandés ni stockés dans le dépôt.
- **ADR éventuel :** aucun ; les services et profils appliquent directement la SFG. Les petits processus de santé portent explicitement le nom `bootstrap` et seront remplacés par les tickets applicatifs FND-007/FND-008 et le ticket web dédié.
- **Commit/hash :** `f57f42f34fcb1eb3fdc789f0c2971da617237bb6` (`feat: add minimal Docker Compose stack`).

## FND-006 — Créer les primitives transverses

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-002` et `FND-004` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `python/metiquo/foundation/__init__.py`, `python/metiquo/foundation/identifiers.py`, `python/metiquo/foundation/time.py`, `python/metiquo/foundation/finance.py`, `python/metiquo/foundation/errors.py`, `python/metiquo/foundation/observability.py`, `python/metiquo/db/base.py`, `tests/test_identifiers.py`, `tests/test_time.py`, `tests/test_finance.py`, `tests/test_errors.py`, `tests/test_observability.py`, `tests/test_database_conventions.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** recherche de directives de contournement de types (`type: ignore`, `Any`) et d’exceptions trop larges ; `pnpm install --frozen-lockfile` ; `uv lock --check` ; `uv sync --frozen` ; `pnpm run spellcheck` ; `pnpm run format:check` ; `pnpm run lint` ; `pnpm run typecheck` ; `uv run --frozen ruff format --check python services infra tests` ; `uv run --frozen ruff check python services infra tests` ; `uv run --frozen mypy` ; tests ciblés des primitives ; `uv run --frozen pytest`.
- **Résultat exact :** identifiants de domaines distincts même pour un UUID identique ; instants naïfs refusés et instants conscients normalisés/ordonnés en UTC ; horloge fixe déterministe ; `Money`, `DecimalOdds` et `Probability` fondés sur `Decimal`, valeurs non finies et `float` refusés ; erreur métier convertible en dictionnaire avec contexte immuable et retryability explicite ; logs JSON avec `trace_id`, `correlation_id`, `job_id`, `snapshot_id` et `model_version` issus d’un contexte restauré après usage. Suite complète : 32 tests réussis et 1 test PostgreSQL correctement ignoré sans `TEST_DATABASE_URL` ; Ruff, mypy strict, TypeScript strict, ESLint, Prettier et CSpell passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; primitives indépendantes des frameworks dans un paquet dédié.
- **Commit/hash :** `f0331e9f3fba1ec45fb07b5f490cccb0ffcaf79f` (`feat: add foundational domain primitives`).

## FND-007 — Squelette FastAPI et contrat OpenAPI

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-003` et `FND-006` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `.prettierignore`, `README.md`, `docker-compose.yml`, `pyproject.toml`, `uv.lock`, `python/metiquo/api/__init__.py`, `python/metiquo/api/app.py`, `python/metiquo/api/dto.py`, `python/metiquo/api/messages.py`, `python/metiquo/api/openapi.py`, `python/metiquo/api/readiness.py`, `infra/scripts/export_openapi.py`, `infra/compose/python.Dockerfile`, suppression du bootstrap `infra/compose/bootstrap/api_health.py`, `packages/contracts/openapi/v1.json`, `tests/api/test_api.py`, `tests/test_openapi.py`, `tests/integration/test_migrations.py`, `docs/progress.md`.
- **Migrations :** aucune nouvelle migration.
- **Commandes/tests exécutés :** résolution et verrouillage de FastAPI, `Uvicorn` et `httpx2` ; `uv lock` ; `uv sync --frozen` ; `uv run --frozen python infra/scripts/export_openapi.py` ; tests API et contrat ciblés ; build et démarrage `docker compose --profile mock up -d --build --wait --wait-timeout 120` ; appels HTTP `/health`, `/ready`, `/api/v1/system/status`, `/openapi.json` avant et après `docker compose exec -T api alembic upgrade head` ; conteneur PostgreSQL jetable sur port aléatoire ; `TEST_DATABASE_URL=... uv run --frozen pytest tests/integration/test_migrations.py -vv` ; arrêt/suppression des conteneurs et volumes ; suite complète format, lint, typecheck et tests.
- **Résultat exact :** `/health` retourne `200` sans sonder PostgreSQL ; `/ready` retourne `503` avec `MIGRATIONS_NOT_AT_HEAD` avant migration puis `200` après migration ; le statut système retourne `200`, `dataMode=mock`, version `0.1.0` et un instant UTC ; `/openapi.json` retourne `200`. Les erreurs 404, validation et métier utilisent `application/problem+json` sans refléter l’entrée invalide ; DTO Pydantic séparés des ORM ; contrat `packages/contracts/openapi/v1.json` régénéré puis comparé à l’octet. Suite locale : 41 tests réussis et 2 tests PostgreSQL ignorés sans `TEST_DATABASE_URL` ; suite PostgreSQL réelle : 2 tests réussis en `0.93 s` ; Ruff, mypy strict, TypeScript strict, ESLint, Prettier et CSpell passent sans warning. Le client de test `httpx` déprécié a été remplacé par le transport ASGI `httpx2` avant validation finale.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; FastAPI et OpenAPI sont imposés par le ticket. La sonde de disponibilité est injectée et reste distincte des DTO et de l’ORM.
- **Commit/hash :** `d535114eddbc29069842592266cd15dd51a563eb` (`feat: add FastAPI system endpoints`).

## FND-008 — Squelette worker

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-003`, `FND-004` et `FND-006` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `python/metiquo/worker/__init__.py`, `python/metiquo/worker/__main__.py`, `python/metiquo/worker/contracts.py`, `python/metiquo/worker/runtime.py`, `tests/worker/test_worker.py`, `docker-compose.yml`, `infra/compose/python.Dockerfile`, suppression de `infra/compose/bootstrap/worker.py`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** tests ciblés `uv run --frozen pytest tests/worker/test_worker.py` ; Ruff et mypy strict ; build et démarrage `docker compose --profile mock up -d --build --wait --wait-timeout 120` ; lecture des logs worker ; `docker compose stop -t 10 worker` ; inspection de l’état, du code de sortie, de l’UID et du statut OOM ; suite complète format, lint, typecheck et pytest ; arrêt Compose et suppression contrôlée des volumes et réseaux de test.
- **Résultat exact :** protocole `JobHandler`, `JobContext` typé, horloge injectable et jeton d’annulation coopérative validés ; le runtime démarre et s’arrête sans job ni scheduler ; le conteneur journalise en JSON `worker.started` puis `worker.stopped`, s’arrête en code `0` sur SIGTERM sous UID `10001` avec `oom=false`. Suite complète : 43 tests réussis et 2 tests PostgreSQL correctement ignorés sans `TEST_DATABASE_URL` ; Ruff, mypy strict, TypeScript strict, ESLint, Prettier et CSpell passent ; nettoyage final : aucun conteneur, volume ou réseau Compose Metiquo restant.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; processus worker séparé et sans scheduler conformément à la SFG. L’acquisition PostgreSQL des jobs reste explicitement hors de ce squelette et sera ajoutée par son ticket métier.
- **Commit/hash :** `b7081a8658873b99b5577848c6a91d614e742332` (`feat: add worker lifecycle skeleton`).

## FND-009 — Makefile et commandes développeur

- **Statut :** `IN_PROGRESS`
- **Dépendances vérifiées :** `FND-005`, `FND-007` et `FND-008` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `Makefile`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** installation utilisateur de GNU Make `4.4.1` via le paquet `ezwinports.make` ; validations en cours.
- **Résultat exact :** GNU Make `4.4.1` est exécutable ; validations du ticket en cours.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le ticket expose les commandes prévues sans décision architecturale.
- **Commit/hash :** à créer après validation.
