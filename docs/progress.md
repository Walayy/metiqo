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

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-005`, `FND-007` et `FND-008` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `Makefile`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** installation utilisateur de GNU Make `4.4.1` via le paquet `ezwinports.make` ; `make lint` ; `make test` ; `make typecheck` ; `make openapi-check` ; test négatif `make oe-catalog` ; `make up` ; appels HTTP avant migration ; `make db-migrate` ; appels HTTP après migration ; `make down` ; suppression contrôlée des seuls volumes du smoke test ; `make format` ; `make check` ; simulation de recette `make -n test-e2e` ; `git diff --check`.
- **Résultat exact :** `make lint` retourne `0` avec Prettier, ESLint, CSpell et Ruff sans erreur ; `make test` réussit 43 tests et ignore correctement 2 tests PostgreSQL conditionnels ; TypeScript strict et mypy contrôlent respectivement le workspace et 39 fichiers Python sans erreur ; le contrat OpenAPI reste identique après régénération. La cible OE réservée retourne explicitement `2`. Le premier essai de `make up` a exposé que Compose traitait la garde mock one-shot sortie en `0` comme un service arrêté ; la cible exécute désormais cette garde séparément et attend uniquement les services durables. Le parcours corrigé retourne `0`, `/ready` passe de `503` à `200` après migration, les sondes API/web répondent `200`, les quatre services durables sont sains et `make down` retourne `0`. `make format` ne modifie aucun fichier supplémentaire et `make check` repasse intégralement en code `0`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le ticket expose les commandes prévues sans décision architecturale.
- **Commit/hash :** `bc1903b6b708c437ba6b870db9b7e22a07c6f225` (`chore: add developer Make targets`).

## FND-010 — CI de base et discipline ADR

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-009` est `DONE` et présent sur `origin/main`.
- **Fichiers créés/modifiés :** `.github/workflows/ci.yml`, `Makefile`, `README.md`, `docs/adr/README.md`, `docs/adr/0000-template.md`, `docs/progress.md`.
- **Migrations :** aucune nouvelle migration.
- **Commandes/tests exécutés :** contrôle des versions et SHA des actions officielles ; `make format` ; `make lint` ; `make typecheck` ; `make test` ; `make openapi-check` ; test négatif `make test-migrations` sans URL ; conteneur PostgreSQL `18` jetable sur port aléatoire ; `TEST_DATABASE_URL=... make test-migrations` ; `make docker-build` ; `make check` ; `git diff --check` ; commits et push ; `gh run watch 33879548552 --exit-status` ; `gh run watch 33879729747 --exit-status` ; lecture de la visibilité, des checks et de la protection via l’API GitHub ; activation puis relecture de la protection stricte de `main`.
- **Résultat exact :** contrôles locaux intégralement verts : Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy sur 39 fichiers, 43 tests réussis et 2 tests PostgreSQL conditionnels ignorés ; la garde sans `TEST_DATABASE_URL` échoue fermement ; sur PostgreSQL réel, les 2 tests de migration passent en `1.26 s` ; le build des cinq images Compose passe. Les runs GitHub Actions réels `33879548552` et `33879729747` sont verts sur les trois jobs. Les actions tierces sont figées par SHA, les permissions sont en lecture seule et le template ADR couvre explicitement les décisions SFG §33. Après passage du dépôt en public, `main` exige strictement les checks GitHub Actions `Qualité`, `Build Docker` et `Migrations PostgreSQL`, y compris pour l’administrateur ; force-push et suppression sont interdits.
- **Blocker éventuel :** aucun. Le refus GitHub initial en HTTP `403` a été levé par le passage du dépôt en public décidé par le propriétaire.
- **ADR éventuel :** ajout du template et de la règle de création ; aucune décision structurante n’est modifiée par le ticket.
- **Commit/hash :** `6b44b323ac9a076bacadb6960806ecf5ebb8d5fa` (`ci: add base validation pipeline`).

## MCK-001 — Définir les contrats de domaine

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-007` est `DONE` ; la phase P0 est intégralement terminée avec `FND-010` protégé par CI sur `main`.
- **Fichiers créés/modifiés :** `python/metiquo/contracts/`, `python/metiquo/config.py`, `python/metiquo/api/dto.py`, `python/metiquo/api/app.py`, `python/metiquo/api/openapi.py`, `python/metiquo/api/contract_schema.py`, `infra/scripts/export_openapi.py`, `Makefile`, `tests/contracts/test_domain_contracts.py`, `tests/test_openapi.py`, `packages/contracts/openapi/v1.json`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** recherches ciblées des exigences SFG de cotes, fraîcheur, abstention, value, modèles, backtests, paper trading et mapping ; Ruff format/check ; mypy strict ; tests de contrats et OpenAPI ciblés ; `make openapi` ; `make format` ; `make check` ; recherches de dépendances ORM/HTML/provider, de `Any`, casts, ignores et TODO ; `git diff --check` ; commit, push et contrôles protégés de la PR GitHub #2.
- **Résultat exact :** les 11 DTO demandés et leurs enums canoniques sont stricts, immuables, sérialisés avec aliases camelCase et indépendants de SQLAlchemy ou d’un provider concret. Les décimaux refusent les `float` et valeurs non finies ; tous les instants exigent un fuseau et sont normalisés en UTC ; les références événement/marché/sélection, cutoff, intervalles de probabilité, règlements paper, décisions de mapping, promotions et backtests financiers sont validés. Les composants sont publiés dans OpenAPI sans ajouter de route et toutes les références se résolvent. Suite locale : 55 tests réussis et 2 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 49 fichiers, TypeScript strict, ESLint, Prettier et CSpell passent ; OpenAPI versionné est courant. PR #2 : `Build Docker` passe en `19 s`, `Qualité` en `40 s` et `Migrations PostgreSQL` en `41 s`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les DTO appliquent les contrats mock/réel et les invariants normatifs sans modifier une décision SFG §33.
- **Commit/hash :** `68617fcf0e78c545aa04f6d953891f27dc56e948` (`feat: add shared domain contracts`).

## MCK-002 — Implémenter l’isolation mock/réel

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-003` et `MCK-001` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** `python/metiquo/repositories/`, `python/metiquo/db/schemas.py`, migration `20260904_0002`, `tests/repositories/test_mode_boundary.py`, `tests/integration/conftest.py`, `tests/integration/test_migrations.py`, `tests/integration/test_mode_isolation.py`, `README.md`, `docs/progress.md`.
- **Migrations :** `20260904_0002_create_mock_schema.py`, réversible, crée uniquement le schéma physique `mock`.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ; tests unitaires ciblés de configuration et frontière de mode ; `uv run --frozen alembic history` ; conteneur PostgreSQL `18` jetable sur port aléatoire ; `TEST_DATABASE_URL=... make test-migrations` ; suppression du conteneur jetable ; `make format` ; `make check` ; recherche de TODO, `Any`, casts, ignores et exceptions trop larges ; `git diff --check` ; commit, push et contrôles protégés de la PR GitHub #3.
- **Résultat exact :** le schéma `mock` est créé par une migration réversible après les sept schémas réels. Toute table logique d’une `MockRepositoryFactory` est traduite vers `mock`, tandis qu’une `RealRepositoryFactory` conserve son schéma réel ; frontières, moteurs et payloads de modes opposés sont refusés. Le mode mock bloque Oracle’s Elixir et le provider de cotes avant appel du transport. Sur PostgreSQL réel, 5 tests d’intégration passent en `2.37 s`, dont migration complète et coexistence de deux lignes de même clé avec valeurs `real-only` et `mock-only`, chacune invisible depuis la factory opposée. Suite locale : 61 tests réussis et 3 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 56 fichiers, TypeScript strict, ESLint, Prettier, CSpell et OpenAPI passent. PR #3 : `Build Docker` passe en `16 s`, `Migrations PostgreSQL` en `27 s` et `Qualité` en `41 s`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le schéma mock séparé et l’interdiction réseau appliquent directement la SFG.
- **Commit/hash :** `b805cb701ae1c4727a9e39f3d740dc1060d3b92d` (`feat: isolate mock and real data access`).

## MCK-003 — Créer les 12 scénarios mock normatifs

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-001` et `MCK-002` sont `DONE` et présents sur `origin/main` après fusion protégée de la PR #3.
- **Fichiers créés/modifiés :** `python/metiquo/mock/`, `tests/mock/test_scenarios.py`, `tests/fixtures/mock_scenarios_v1.sha256`, `python/metiquo/config.py`, `.env.example`, `docker-compose.yml`, `tests/test_config.py`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** lecture ciblée de la SFG §8.2, §25.1, §26.5, §31 et §33 ainsi que de `MCK-003` dans le plan, le backlog et la traçabilité ; Ruff format/check ; mypy strict ; tests ciblés scénarios/configuration ; calcul et vérification du snapshot SHA-256 ; `make check` via le chemin absolu de GNU Make ; `make docker-build` ; recherche de TODO, ignores, casts et `Any` ; `git diff --check`. Une première invocation de `make` nu dans la copie de travail a échoué avant tout contrôle car son dossier utilisateur n’était pas dans le `PATH` de ce processus ; elle a été relancée avec l’exécutable installé explicitement.
- **Résultat exact :** catalogue de 12 scénarios, chacun adressable par une clé stable et composé des DTO canoniques ; une même graine et une même horloge produisent une sérialisation identique, une autre horloge décale uniquement les timestamps relatifs, et une autre graine produit des IDs disjoints. Les scénarios couvrent faible value, outsider à vraie value, cote stale, marché suspendu, mapping ambigu, données Oracle incomplètes, modèle stale, forte incertitude, sync échouée avec dernier snapshot valide, changement de cote append-only, void et résultat en quarantaine. Le snapshot complet est verrouillé par le digest `180ffd4e3c3159fecf41416ff81219b0d06c4b9d6a75a16c0e3b16428348909f`. Suite finale : 76 tests réussis et 3 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 59 fichiers, TypeScript strict, ESLint, Prettier, CSpell et OpenAPI passent. Les cinq images Compose du profil mock sont construites avec succès. Premier run protégé de la PR #4 : `Build Docker` passe en `20 s`, `Migrations PostgreSQL` en `21 s` et `Qualité` en `52 s`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le catalogue applique directement les scénarios et l’horloge déterministe imposés par la SFG sans modifier une décision structurante.
- **Commit/hash :** `51713aee12138d1558bf31cd1591a40d2b9f00cd` (`feat: add deterministic mock scenarios`).

## MCK-004 — Implémenter repositories/services mock

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-003` est `DONE` et présent sur `origin/main` après fusion protégée de la PR #4.
- **Fichiers créés/modifiés :** `python/metiquo/contracts/odds_provider.py`, `python/metiquo/contracts/__init__.py`, `python/metiquo/repositories/contracts.py`, `python/metiquo/repositories/mock.py`, `python/metiquo/repositories/__init__.py`, `python/metiquo/services/`, `tests/repositories/test_mock_repositories.py`, `packages/contracts/openapi/v1.json`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** tests ciblés repositories/scénarios ; Ruff format/check ; mypy strict ; Prettier, ESLint, CSpell et TypeScript strict ; suite Pytest complète ; régénération et contrôle OpenAPI ; `docker compose config --quiet` ; `docker compose --profile mock build` ; `git diff --check`.
- **Résultat exact :** les six repositories mock demandés lisent le catalogue normatif immuable et exposent opportunités, événements/marchés/historique append-only, modèles, paper bets, santé fournisseur et mappings en attente. `ReadService` dépend uniquement de ports communs, sans import de fixtures ou d'adaptateur mock, afin que l'API utilise la même orchestration en modes mock et réel. `MockOddsProvider` respecte le contrat interchangeable complet `list_events`/`get_event_markets`/`capture_snapshot`/`health`, sans accès réseau, et ses DTO provider stricts sont publiés dans OpenAPI. Validation finale : 80 tests réussis et 3 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 65 fichiers, TypeScript strict, ESLint, Prettier, CSpell et OpenAPI passent ; les cinq images Compose sont construites avec succès.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; ports/adaptateurs et façade de lecture appliquent l'indépendance provider et l'isolation mock/réel déjà imposées par la SFG.
- **Commit/hash :** `c383f283140ef786cc020da2eec39eddf0737995` (`feat: add mock repositories and services`).

## MCK-005 — Exposer toutes les lectures API en mock

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-004` est `DONE` et présent sur `origin/main` après fusion protégée de la PR #5.
- **Fichiers créés/modifiés :** `python/metiquo/api/app.py`, `python/metiquo/api/read_routes.py`, `python/metiquo/api/dto.py`, `python/metiquo/api/contract_schema.py`, `python/metiquo/contracts/operations.py`, `python/metiquo/contracts/__init__.py`, `python/metiquo/repositories/contracts.py`, `python/metiquo/repositories/mock.py`, `python/metiquo/repositories/__init__.py`, `python/metiquo/services/`, `tests/api/test_mock_reads.py`, `tests/repositories/test_mock_repositories.py`, `tests/test_openapi.py`, `packages/contracts/openapi/v1.json`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** tests API ciblés ; Ruff format/check ; mypy strict ; Prettier, ESLint, CSpell et TypeScript strict ; suite Pytest complète ; régénération et contrôle OpenAPI ; `docker compose config --quiet` ; `docker compose --profile mock build` ; `git diff --check`.
- **Résultat exact :** les lectures `/api/v1` couvrent opportunités/détail/explication, événements/détail/marchés/historique de cotes, modèles/backtests et leurs détails, paper bets et détail, sources, ingestions, qualité, jobs et mappings en attente. Les collections ont une pagination bornée et des filtres typés ; les ressources inconnues retournent des Problem Details 404 et les requêtes invalides des Problem Details 422/400 sans reprendre les entrées. Toutes les réponses métier utilisent une enveloppe immuable contenant `dataMode`, `freshness`, `asOf`, `computedAt` et `appVersion`. Les routes ne dépendent que de `ReadService`, tandis que le mode mock assemble automatiquement le catalogue déterministe. Validation finale : 85 tests réussis et 3 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 68 fichiers, TypeScript strict, ESLint, Prettier, CSpell et OpenAPI passent ; les cinq images Compose sont construites avec succès.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l’enveloppe, la pagination et les routes appliquent les contrats et la surface HTTP déjà imposés par la SFG.
- **Commit/hash :** `4a4f4ec1cd4443bc0c44071eab73dbb2d06f9684` (`feat: expose mock read API`).

## MCK-006 — Exposer mutations mock contrôlées

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005` est `DONE` et présent sur `origin/main` après fusion protégée de la PR #6.
- **Fichiers créés/modifiés :** `python/metiquo/api/app.py`, `python/metiquo/api/dto.py`, `python/metiquo/api/mutation_routes.py`, `python/metiquo/contracts/operations.py`, `python/metiquo/contracts/__init__.py`, `python/metiquo/services/mutations.py`, `python/metiquo/services/__init__.py`, `tests/api/test_mock_mutations.py`, `tests/test_openapi.py`, `packages/contracts/openapi/v1.json`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** tests API ciblés des mutations et de l’idempotence ; Ruff format/check ; mypy strict ; Prettier, ESLint, CSpell et TypeScript strict ; suite Pytest complète ; régénération et contrôle OpenAPI ; `docker compose config --quiet` ; `docker compose --profile mock build` ; `git diff --check`.
- **Résultat exact :** les actions mock couvrent synchronisation, entraînement/promotion/retrait de modèle, création/règlement de paper bet, approbation/rejet de mapping et création d’alias. Toutes exigent `Idempotency-Key` : une répétition identique retourne le résultat initial sans nouvel effet ni nouvel audit, tandis qu’un payload différent avec la même clé retourne un conflit. Les transitions invalides sont bloquées, une opportunité non publiable ne peut pas créer de paper bet et aucune action n’accède au réseau. Le journal d’audit immuable conserve action, ressource, date, mode et empreinte SHA-256 de la clé sans sa valeur brute. Validation finale : 90 tests réussis et 3 tests PostgreSQL conditionnels ignorés ; Ruff, mypy sur 71 fichiers, TypeScript strict, ESLint, Prettier, CSpell et OpenAPI passent ; les cinq images Compose sont construites avec succès.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l’idempotence, l’audit et les transitions appliquent les exigences existantes sans modifier une décision structurante.
- **Commit/hash :** `1709834977053554f3b6ea14b6f6f6c8fe7e12b8` (`feat: add idempotent mock mutations`).

## UI-001 — Initialiser le frontend et le design system

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-002` et `MCK-001` sont `DONE` et présents sur `origin/main`.
- **Fichiers créés/modifiés :** application Next.js sous `apps/web/`, design system sous `packages/ui/`, client et DTO TypeScript générés sous `packages/contracts/src/generated/`, configurations workspace pnpm/TypeScript/ESLint/Prettier, `Makefile`, image web et service Compose, `.dockerignore`, `.gitignore`, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** consultation des documentations officielles Tailwind CSS, TanStack Query, Hey API et Motion ; vérification des versions via le registre pnpm ; `pnpm install` ; `pnpm run contracts:generate` ; tests et contrôles de types frontend ciblés ; build Next.js local ; `make check` via GNU Make installé ; `make docker-build` ; démarrage isolé `docker compose up -d --build --no-deps web` ; appels HTTP `/health` et `/` ; inspection de l’utilisateur et de la racine du conteneur ; arrêt Compose et suppression des volumes et réseaux de smoke test ; `git diff --check`.
- **Résultat exact :** Next.js `16.3.4`, React `19.2.8`, Tailwind CSS `4.3.3` et TypeScript strict sont opérationnels ; les tokens couvrent couleurs, espacement, rayons, typographie, élévation et durée d’interaction. Les primitives `Button`, `MotionButton`, `Badge` et `Card` exposent focus visible, sémantique native, tailles tactiles, état désactivé et réduction du mouvement. Le contrat OpenAPI versionné génère les DTO, le client Fetch, le SDK et les options TanStack Query sans copie manuelle ; le provider Query est monté une seule fois côté client. Quatre tests de composants réussissent, dont activation clavier, sémantique désactivée/section et disponibilité du client Query. `make check` passe avec Prettier, ESLint, CSpell, Ruff, mypy sur 71 fichiers, TypeScript sur les trois workspaces, 90 tests Python réussis et 3 tests PostgreSQL conditionnels ignorés ; le contrat OpenAPI et le client généré sont courants. Les cinq images Compose se construisent ; le conteneur Next.js réel répond `200` sur `/health` et `/`, contient le rendu Metiquo, tourne sous `node` avec une racine en lecture seule, puis ne laisse aucun conteneur, volume ou réseau de test. Le premier build web a détecté l’inclusion des `node_modules` Windows imbriqués dans le contexte Docker ; les exclusions récursives empêchent désormais leur copie dans les builds Linux.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le ticket applique directement la stack frontend et les exigences d’accessibilité de la SFG sans modifier une décision structurante.
- **Commit/hash :** `fa8e7716c923a33ebc19722aa9d4de7ba0b7c788` (`feat: add frontend foundation`).

## UI-002 — Thème et shell sans flash

- **Statut :** `DONE`
- **Dépendances vérifiées :** `UI-001` est `DONE` et présent sur `origin/main` après fusion protégée de la PR #8.
- **Fichiers créés/modifiés :** shell applicatif et menu de thème sous `apps/web/src/components/`, layout/providers/styles et routes de navigation sous `apps/web/src/app/`, tokens clair/sombre sous `packages/ui/src/styles.css`, configuration Next.js/Playwright et tests E2E, dépendances frontend, image web et service Compose, workflow CI, `README.md`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** consultation des documentations officielles Next.js, next-themes et Radix UI ; vérification des versions via le registre pnpm ; `pnpm install` ; `pnpm run format` ; `make check` via GNU Make installé ; installation locale de Chromium Playwright ; `make test-e2e` ; inspection visuelle des captures plein écran clair/sombre ; `make docker-build` ; smoke tests HTTP d’images web standalone compilées avec `APP_DATA_MODE=mock` puis `APP_DATA_MODE=real` ; `git diff --check`.
- **Résultat exact :** le thème suit le système par défaut et applique la préférence persistée avant l’hydratation via `data-theme`, avec fallback CSS initial clair/sombre et transitions neutralisées au changement. Le shell responsive expose les sept destinations normatives, un tiroir mobile accessible, un lien d’évitement clavier, des focus visibles, le menu clair/sombre/système et le badge de mode persistant. Six tests Playwright réussissent : rendu pré-hydratation clair/sombre sans erreur ni warning console, préférence système, navigation desktop/clavier, navigation mobile et changement de thème ; les captures visuelles clair/sombre sont jointes au rapport HTML conservé par la CI. Les quatre tests de composants réussissent ; 90 tests Python réussissent et 3 tests PostgreSQL conditionnels sont ignorés ; Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI passent. Les cinq images Compose se construisent ; les conteneurs web mock et réel répondent `200` sur `/health` et `/`, avec respectivement les badges `MOCK` et `REAL` dans le rendu serveur.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le ticket applique le thème système, le shell responsive et l’identification explicite du mode imposés par la SFG sans modifier une décision structurante.
- **Commit/hash :** `221f118688c0dad4acd7e11b7fcab3240458cc85` (`feat: add responsive themed app shell`).

## UI-003 — Bibliothèque d’états distants

- **Statut :** `DONE`
- **Dépendances vérifiées :** `UI-001` est `DONE` et présent sur `origin/main` après fusion protégée de la PR #8.
- **Fichiers créés/modifiés :** `packages/ui/src/remote-states.tsx`, `packages/ui/src/remote-states.test.tsx`, `packages/ui/src/index.ts`, `packages/ui/src/styles.css`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** tests Vitest ciblés ; typecheck strict du package UI ; ESLint ciblé ; formatage Prettier ; build Next.js de production local ; `make check` via GNU Make installé ; `make docker-build` ; `git diff --check`.
- **Résultat exact :** la bibliothèque exporte un skeleton à dimensions réservées, les états loading, vide, erreur récupérable avec retry clavier, erreur bloquante, stale, permission refusée, mock, hors connexion et reconnexion, ainsi qu’une frontière de données qui conserve explicitement le contenu précédent pendant un refetch sûr et permet de le masquer lorsqu’il ne l’est pas. Aucun spinner n’est utilisé ; le shimmer respecte `prefers-reduced-motion`, les états dynamiques ont des rôles accessibles et les états plein écran réservent la même hauteur que le chargement. La matrice de composants couvre tous les états demandés, les dimensions, le retry et les deux politiques de refetch. Validation finale : 16 tests UI et 1 test web réussissent ; 90 tests Python réussissent et 3 tests PostgreSQL conditionnels sont ignorés ; Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI passent ; les cinq images Compose sont construites avec succès.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la bibliothèque applique directement les exigences d’états, d’accessibilité et de stabilité visuelle de la SFG sans modifier une décision structurante.
- **Commit/hash :** `57b523a8f317d4221440eb91e68a98129ee40b99` (`feat: add remote state library`).

## UI-004 — Dashboard Opportunités

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `UI-002` et `UI-003` sont `DONE` et présents sur `origin/main` après fusion protégée de la PR #10.
- **Fichiers créés/modifiés :** `apps/web/src/app/page.tsx`, `apps/web/src/app/api/backend/[...path]/route.ts`, `apps/web/src/components/app-shell.tsx`, `apps/web/src/components/opportunities-dashboard.tsx`, `apps/web/src/components/opportunity-presenters.ts`, `apps/web/src/components/opportunity-presenters.test.ts`, `packages/contracts/package.json`, `playwright.config.ts`, `tests/e2e/opportunities.spec.ts`, `docker-compose.yml`, `.github/workflows/ci.yml`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** formatage Prettier ciblé ; typecheck strict des packages web et contrats ; ESLint ciblé ; build Next.js de production ; tests Vitest ciblés ; inspection fonctionnelle et visuelle dans le navigateur intégré en thème sombre, vues tableau et cartes ; inspection de la capture mobile Playwright ; test de régression du débordement horizontal à `1132 × 900` ; `make check` via GNU Make installé ; `make test-e2e` ; `make docker-build` ; `git diff --check`.
- **Résultat exact :** le dashboard affiche la santé des sources, le nombre réellement admissible et le dernier snapshot, puis les treize colonnes normatives de décision. Le tri initial est stable par EV prudente décroissante ; les filtres ligue, équipe, grade, fraîcheur, périmètre, ordre et mode d’affichage restent partageables dans l’URL. Les mouvements de cote, grades, signes d’edge/EV, fraîcheur et motifs d’abstention utilisent texte, icônes et signes sans dépendre de la couleur. Les vues tableau et cartes, l’état vide explicite, le snapshot ancien avec décision bloquée, l’erreur récupérable et le chargement à dimensions réservées sont couverts. Le proxy serveur garde l’URL privée de l’API hors du navigateur et retourne un Problem Details neutre lorsque la dépendance est indisponible. L’inspection à largeur intermédiaire a révélé puis corrigé un débordement global : la page reste désormais bornée au viewport tandis que le tableau possède son propre défilement. Validation finale locale : 16 tests UI et 4 tests web réussissent ; 90 tests Python réussissent et 3 tests PostgreSQL conditionnels sont ignorés ; 12 tests Playwright réussissent, dont filtres/URL, tri, état vide, stale, mobile et largeur intermédiaire ; Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI passent ; les cinq images Compose sont construites avec succès. Le premier job Playwright de la PR a exposé l’absence de `uv` dans son environnement Node historique ; ce job installe désormais explicitement `uv`, Python et les dépendances backend nécessaires au serveur API E2E. Le run corrigé `33906382699` est entièrement vert : migrations en `22 s`, Docker en `39 s`, qualité en `1 min 6 s` et Playwright en `1 min 40 s`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le dashboard applique les contrats, règles d’admission, colonnes et états distants déjà imposés sans modifier une décision structurante.
- **Commit/hash :** `0b613e485c530c970b672d17dc49d69a9deb8b96` (`feat: add opportunity dashboard`).

## UI-005 — Fiche événement

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `UI-002` et `UI-003` sont `DONE` et présents sur `main` ; `UI-004` est fusionné par la PR #11.
- **Fichiers créés/modifiés :** `apps/web/src/app/events/page.tsx`, `apps/web/src/app/events/[eventId]/page.tsx`, `apps/web/src/components/events-explorer.tsx`, `apps/web/src/components/event-detail.tsx`, `apps/web/src/components/opportunities-dashboard.tsx`, `tests/e2e/event-detail.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ; typecheck web strict ; ESLint ciblé ; tests Playwright ciblés ; inspection visuelle et fonctionnelle dans le navigateur intégré des vues liste et détail en thème sombre ; inspection de la capture desktop claire ; `make check` ; `make test-e2e` ; `git diff --check`.
- **Résultat exact :** la navigation Événements expose les 12 matchs mock puis une fiche partageable par identifiant canonique. La fiche regroupe participants et format, marchés supportés et non supportés, probabilités marché/modèle et intervalle, EV prudente, facteurs de qualité, données manquantes, confiance du mapping, version modèle, feature/odds snapshots, provenance source et timeline cutoff-prédiction-cote-début. Les rosters individuels absents ne sont pas inventés et le mode mock indique explicitement qu’aucun snapshot Oracle’s Elixir réel n’est utilisé. La courbe de cotes possède un titre, une description SVG et un résumé textuel équivalent. Le seul CTA transactionnel crée un paper bet depuis un signal admissible ; aucune mise réelle ni connexion bookmaker n’est proposée. Validation : 16 tests UI et 4 tests web réussissent ; 90 tests Python réussissent et 3 sont ignorés ; les 14 scénarios Playwright réussissent, dont deux nouveaux tests détail/mobile ; Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI passent.
- **Blocker éventuel :** aucun pour le mode mock. Les rosters détaillés et snapshots Oracle’s Elixir réels restent correctement absents avant les phases de données réelles.
- **ADR éventuel :** aucun ; la fiche agrège les endpoints et DTO existants sans modifier l’architecture.
- **Commit/hash :** `406b95ad893895c334c0b3c6ae345c7b48c27d30` (`feat: add event detail experience`).

## UI-006 — Fiche signal et explicabilité UI

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `UI-002` et `UI-003` sont `DONE` et présents sur `main`.
- **Fichiers créés/modifiés :** `apps/web/src/app/opportunities/[signalId]/page.tsx`, `apps/web/src/components/signal-detail.tsx`, `apps/web/src/components/event-detail.tsx`, `apps/web/src/components/opportunities-dashboard.tsx`, `tests/e2e/signal-detail.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ; typecheck web strict ; ESLint ciblé ; tests Playwright ciblés admissible/stale/mobile ; inspection de la capture desktop claire ; inspection fonctionnelle et visuelle dans le navigateur intégré en thème sombre ; `git diff --check`.
- **Résultat exact :** chaque signal possède une URL dédiée reliant prix marché observé et prix modèle indépendant, intervalle et confiance, edge/EV central et prudent, facteurs structurés, risques, qualité/fraîcheur, raisons d’abstention, référence d’explication, historique horodaté des cotes et règles paper versionnées. Un snapshot stale reste consultable pour audit avec décision et création paper bloquées. Les facteurs sont explicitement décrits comme indicateurs non causaux et aucun langage de certitude ou de résultat garanti n’est présent. Le tableau d’historique est contenu dans sa propre zone de défilement clavier sur mobile. Les 3 nouveaux tests Playwright passent ; typecheck strict, ESLint et Prettier passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la fiche assemble les endpoints existants et partage le graphique accessible de la fiche événement.
- **Commit/hash :** `5ab21f5bf1fc7ac060c60160b78f768a722f494b` (`feat: add explainable signal detail`).

## UI-007 — Catalogue modèles et backtests

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `UI-002` et `UI-003` sont `DONE` et présents sur `main`.
- **Fichiers créés/modifiés :** `apps/web/src/app/models/page.tsx`, `apps/web/src/components/models-dashboard.tsx`, `tests/e2e/models.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ciblé ; typecheck web strict ; ESLint ciblé ; build Next.js de production ; tests Playwright ciblés desktop/mobile ; inspection fonctionnelle, sémantique et visuelle dans le navigateur intégré en thème sombre ; `git diff --check`.
- **Résultat exact :** le catalogue affiche les 12 versions champion exactes, leur algorithme, métriques, feature version et justification de promotion sans créer de challenger absent des données. La comparaison de calibration montre log loss et score de Brier face à leurs baselines avec barres accessibles et résumé textuel équivalent. La table expose les périodes walk-forward, segments, effectifs, métriques et préservation du test final ; chaque backtest mock de 240 observations porte un avertissement de faible échantillon. La capacité `MATCH_WINNER` est active et les autres marchés restent explicitement désactivés jusqu’à leur gate. Les 2 nouveaux tests Playwright passent, dont la zone de défilement clavier du tableau mobile ; typecheck strict, ESLint et Prettier passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le catalogue restitue les DTO et capability gates existants sans modifier l’architecture.
- **Commit/hash :** `d0453d29753377c636ebf4827e2cc2e791b47f3a` (`feat: add models and backtests dashboard`).

## UI-008 — Santé data et administration UI

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `MCK-006`, `UI-002` et `UI-003` sont `DONE` et présents sur `main`.
- **Fichiers créés/modifiés :** `apps/web/src/app/data/page.tsx`, `apps/web/src/app/admin/page.tsx`, `apps/web/src/app/api/backend/[...path]/route.ts`, `apps/web/src/components/data-health-dashboard.tsx`, `tests/e2e/admin-data.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ciblé ; typecheck web strict ; ESLint ciblé ; build Next.js de production ; 3 tests Playwright ciblés ; inspection fonctionnelle, sémantique et visuelle dans le navigateur intégré en thème sombre ; déclenchement d’une synchronisation mock depuis l’interface ; `git diff --check`.
- **Résultat exact :** la vue Données expose le catalogue source, dernière tentative et dernier succès, statut de fraîcheur annuelle, lignes validées, snapshot actif, historique d’ingestion, anomalies bloquantes et quarantaine. Les hash, plage métier et changements de schéma absents du DTO mock sont signalés explicitement au lieu d’être déduits. Un échec avec dernier snapshot valide apparaît comme récupérable ; l’absence du catalogue primaire est bloquante, tandis qu’une erreur isolée de qualité conserve un retry. La vue Administration affiche les jobs, lance une mutation POST avec clé d’idempotence, montre progression puis résultat direct et actualise une seule fois le journal d’audit, sans polling. Les 3 nouveaux tests Playwright passent et le parcours Navigateur confirme 12 lignes synchronisées avec une nouvelle trace `mock.sync` ; typecheck strict, ESLint et Prettier passent.
- **Blocker éventuel :** aucun. Les métadonnées détaillées réelles seront branchées par `OE-023` sur les mêmes composants.
- **ADR éventuel :** aucun ; le proxy transmet uniquement les en-têtes métier nécessaires et n’expose ni cookies ni configuration privée.
- **Commit/hash :** `43e61e5a89fc1e1c76573808e3f2ab824615d60f` (`feat: add data health administration`).

## UI-009 — File de mapping UI

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `MCK-006`, `UI-002` et `UI-003` sont `DONE` et présents sur `main`.
- **Fichiers créés/modifiés :** `apps/web/src/components/data-health-dashboard.tsx`, `apps/web/src/components/mapping-review-queue.tsx`, `tests/e2e/mapping-review.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ciblé ; typecheck web strict ; ESLint ciblé ; build Next.js de production ; 2 tests Playwright ciblés ; inspection fonctionnelle, sémantique et visuelle dans le navigateur intégré en thème sombre ; `git diff --check`.
- **Résultat exact :** la file Administration affiche l’événement fournisseur brut, compétition et participants, les deux candidats canoniques, leur confiance globale, les composantes textuelles réellement présentes et l’absence explicite de pondérations individuelles dans le DTO mock. Le choix radio alimente un aperçu d’impact qui précise qu’aucun historique n’est réécrit. L’ambiguïté reste signalée comme bloquante et les décisions sont désactivées tant que relecteur et motif ne sont pas valides. La création d’alias enregistre sa date serveur ; approbation et rejet sont idempotents, et le candidat retenu est inclus dans le motif audité. Les 2 tests Playwright passent : changement d’aperçu puis parcours alias + approbation, avec traces `alias.create` et `mapping.approved` visibles dans le journal ; typecheck strict, ESLint et Prettier passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l’interface respecte les DTO de revue et mutations existants sans inventer de score de composante.
- **Commit/hash :** `3f88139440118f8b4f5c96c8fe8d912bfad72ea5` (`feat: add audited mapping review queue`).

## UI-010 — Paper trading UI mock

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-005`, `MCK-006`, `UI-002` et `UI-003` sont `DONE` et présents sur `main`.
- **Fichiers créés/modifiés :** `apps/web/src/app/paper-trading/page.tsx`, `apps/web/src/app/paper-trading/[paperBetId]/page.tsx`, `apps/web/src/components/paper-trading-dashboard.tsx`, `apps/web/src/components/paper-bet-detail.tsx`, `tests/e2e/paper-trading.spec.ts`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Prettier ciblé ; typecheck web strict ; ESLint ciblé ; builds Next.js de production ; 3 tests Playwright ciblés exécutés après correction visuelle ; inspection fonctionnelle, sémantique et visuelle dans le navigateur intégré des vues liste/création et détail en thème sombre ; `git diff --check`.
- **Résultat exact :** la page Paper trading présente l’historique, les fiches dédiées, snapshots, règles de règlement versionnées et les six statuts contractuels, avec `open` libellé comme en attente. Un signal admissible préremplit la sélection et la cote figée ; une clé d’idempotence protège création et règlement fictifs. Le résultat créé reste visible dans la session et peut être réglé en `won`, `lost`, `push` ou `void`. Gains, pertes et solde ont des cartes de poids identique ; un scénario contrôlé prouve l’affichage simultané de `+14,00 €` et `-10,00 €`. Le Navigateur a révélé puis fait corriger le signe positif trompeur sur un P&L nul. Les écrans répètent qu’aucune mise bookmaker ni exécution réelle n’existe. Les 3 nouveaux tests Playwright passent ; typecheck strict, ESLint et Prettier passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les flux utilisent les mutations paper existantes et conservent la séparation stricte du mode réel.
- **Commit/hash :** `e4d0a7a5ace7a1470a6f42c9e2ca1599e7bcfbc9` (`feat: add paper trading workflow`).

## UI-011 — Micro-interactions, responsive et accessibilité

- **Statut :** `DONE`
- **Dépendances vérifiées :** `UI-004`, `UI-005`, `UI-006`, `UI-007`, `UI-008`, `UI-009` et `UI-010` sont `DONE`.
- **Fichiers créés/modifiés :** `apps/web/src/app/globals.css`, `apps/web/src/components/data-health-dashboard.tsx`, `tests/e2e/accessibility.spec.ts`, trois baselines sous `tests/e2e/accessibility.spec.ts-snapshots/`, `playwright.config.ts`, `package.json`, `pnpm-lock.yaml`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** vérification de la version `@axe-core/playwright` auprès du registre pnpm ; installation verrouillée de `4.13.0` ; Prettier ; typecheck web strict ; ESLint ciblé ; plusieurs builds Next.js de production ; exécutions ciblées puis complète des 6 tests Playwright UI-011 ; génération puis comparaison des baselines visuelles desktop/tablette/mobile ; inspection des captures mobile et tablette ; `make check` via le chemin absolu de GNU Make installé ; `git diff --check`.
- **Résultat exact :** les contrôles axe WCAG A/AA passent sans violation sur 9 routes clés en même temps que l’absence d’erreur ou avertissement d’hydratation. Axe a d’abord détecté puis fait corriger une structure `<dl>` invalide dans les statistiques de données. Le CLS mesuré sur cinq dashboards reste sous la cible stricte `0,05`. La file de mapping est parcourue au clavier, le focus possède un contour calculé d’au moins 2 px, les quatre commandes mobiles critiques mesurent au moins 44 px de haut et la réduction de mouvement ramène animations/transitions à `0,01 ms`. Les transitions globales utilisent le token de 160 ms ; trois captures stables sans suffixe de plateforme couvrent Opportunités desktop, Administration tablette et Paper mobile sans débordement global. `make check` passe : 16 tests UI et 4 tests web, 90 tests Python réussis et 3 ignorés, Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI verts. Le premier appel `make` nu n’a exécuté aucun contrôle car son dossier n’était pas dans le `PATH` ; la relance absolue retourne `0`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l’audit automatise les exigences UX existantes sans modifier l’architecture.
- **Commit/hash :** `7fcf60f240719cc94d686f89842c50a7740dc996` (`test: enforce responsive accessibility gate`).

## MCK-007 — Gate P1 — démo mock complète

- **Statut :** `DONE`
- **Dépendances vérifiées :** `MCK-006` et `UI-011` sont `DONE` ; l'ensemble des livrables P1 est présent dans le même lot de fusion.
- **Fichiers créés/modifiés :** `Makefile`, `README.md`, `python/metiqo/mock/demo.py`, `infra/scripts/seed_mock_demo.py`, `tests/mock/test_seed_mock_demo.py`, `docs/progress.md`.
- **Migrations :** les migrations existantes `20260904_0001` et `20260904_0002` ont été appliquées avec succès sur un volume PostgreSQL Compose neuf ; aucune nouvelle migration.
- **Commandes/tests exécutés :** `make mock-seed` ; `make mock-demo`, qui exécute le profil `docker compose --profile mock up -d --build --wait` puis `make db-migrate` ; vérification HTTP de `/health`, `/ready`, `/api/v1/system/status` et du web ; inspection Navigateur des vues Opportunités et Paper trading sur les images fraîchement construites ; `make test-e2e` sur la stack Compose ; `make check` ; `git diff --check`.
- **Résultat exact :** la graine `metiquo-demo-v1` produit de façon déterministe les 12 scénarios normatifs et le manifeste SHA-256 `65e4fc0cdcd680ba4bd7bd5efdef79b0cee1465f07eeb54833438b7572b77d43`, avec identifiants événement/signal stables et `externalNetworkAccess=false`. PostgreSQL, API, worker et web deviennent tous `healthy`; les sondes API et web répondent `200`, et le statut système confirme `dataMode=mock` avec la base disponible. Le README documente le démarrage neuf, la validation et l'arrêt. Les 33 tests Playwright passent sur Compose, dont axe WCAG A/AA sur 9 routes sans erreur console/hydratation, CLS, clavier/tactile et trois baselines responsive. `make check` passe : 16 tests UI et 4 tests web, 92 tests Python réussis et 3 ignorés, Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI verts.
- **Blocker éventuel :** aucun ; le gate P1 est vert et autorise le démarrage de P2.
- **ADR éventuel :** aucun ; le script expose et vérifie le catalogue mock existant sans introduire de persistance ou d'accès réseau métier.
- **Commit/hash :** `6ee0186e6632f9a5cbbc0506a395202d96c9ba51` (`feat: complete the mock demo gate`).
