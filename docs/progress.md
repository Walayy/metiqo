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
- **Fichiers créés/modifiés :** `apps/web/src/app/globals.css`, `apps/web/src/components/data-health-dashboard.tsx`, `tests/e2e/accessibility.spec.ts`, six baselines Windows/Linux sous `tests/e2e/accessibility.spec.ts-snapshots/`, `playwright.config.ts`, `package.json`, `pnpm-lock.yaml`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** vérification de la version `@axe-core/playwright` auprès du registre pnpm ; installation verrouillée de `4.13.0` ; Prettier ; typecheck web strict ; ESLint ciblé ; plusieurs builds Next.js de production ; exécutions ciblées puis complète des 6 tests Playwright UI-011 ; génération puis comparaison des baselines visuelles desktop/tablette/mobile sous Windows et dans l'image Linux officielle Playwright `1.62.1` ; inspection des captures mobile et tablette ; `make check` via le chemin absolu de GNU Make installé ; `git diff --check`.
- **Résultat exact :** les contrôles axe WCAG A/AA passent sans violation sur 9 routes clés en même temps que l'absence d'erreur ou avertissement d'hydratation. Axe a d'abord détecté puis fait corriger une structure `<dl>` invalide dans les statistiques de données. Le CLS mesuré sur cinq dashboards reste sous la cible stricte `0,05`. La file de mapping est parcourue au clavier, le focus possède un contour calculé d'au moins 2 px, les quatre commandes mobiles critiques mesurent au moins 44 px de haut et la réduction de mouvement ramène animations/transitions à `0,01 ms`. Les transitions globales utilisent le token de 160 ms ; trois captures stables, chacune versionnée pour Windows et Linux, couvrent Opportunités desktop, Administration tablette et Paper mobile sans débordement global. La séparation par plateforme et Inter embarquée évitent de confondre les différences de rendu typographique des polices avec une régression visuelle. `make check` passe : 16 tests UI et 4 tests web, 90 tests Python réussis et 3 ignorés, Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI verts. Le premier appel `make` nu n'a exécuté aucun contrôle car son dossier n'était pas dans le `PATH` ; la relance absolue retourne `0`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l’audit automatise les exigences UX existantes sans modifier l’architecture.
- **Commit/hash :** `7fcf60f240719cc94d686f89842c50a7740dc996` (`test: enforce responsive accessibility gate`).

## OE-001 — Modèle raw : catalogue, snapshots, runs et qualité

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-004` est `DONE` et le gate `MCK-007` autorise le démarrage de P2.
- **Fichiers créés/modifiés :** `python/metiquo/db/raw_models.py`, migration `20260905_0003`, `python/metiquo/db/migrations/env.py`, `tests/integration/test_migrations.py`, `tests/integration/test_raw_migration.py`, `docs/progress.md`.
- **Migrations :** `20260905_0003_create_raw_ingestion_model.py` crée `raw.source_catalog`, `raw.snapshots`, `raw.ingestion_runs`, `raw.quality_issues`, `raw.quarantine_items` et `raw.row_revisions`, leurs contraintes de statut/unicité, les liens de provenance et le trigger PostgreSQL d'immutabilité des snapshots validés. Le cycle `upgrade → downgrade base → upgrade` passe sur PostgreSQL 18 jetable.
- **Commandes/tests exécutés :** Ruff format/check ciblé ; mypy strict ciblé puis global ; tests unitaires des conventions DB ; tests d'intégration migrations et contraintes exécutés deux fois sur `postgresql+psycopg://…@127.0.0.1:55432/metiqo_test` ; `make check` via le chemin absolu de GNU Make ; contrôle OpenAPI et génération TypeScript sans diff ; `git diff --check`.
- **Résultat exact :** les six tables raw existent avec UUID, timestamps UTC, statuts fermés, hashes SHA-256 contrôlés et clés étrangères `RESTRICT`. Une unicité partielle interdit deux sources actives pour un même provider/dataset/année. Les exécutions, anomalies, quarantaines et révisions gardent leur run et leur snapshot d'origine. Un trigger `BEFORE UPDATE OR DELETE` refuse en base toute mutation d'un snapshot dont le statut est `validated`; les tests prouvent séparément l'échec de l'`UPDATE`, l'échec du `DELETE` et la conservation de la taille initiale. Les 5 tests de migration passent, puis la suite complète retourne 98 tests réussis ; Prettier, ESLint, CSpell, Ruff, TypeScript strict, mypy et OpenAPI sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le modèle matérialise directement les invariants de provenance et d'immutabilité exigés par la SFG.
- **Commit/hash :** `47f701243ed8af2c518c8dbfcd18b1c4bdb6b6e9` (`feat(raw): add ingestion provenance model`).
- **Correctif/hash :** `5529754466501b268a07012d9e9b69d521415fb5` (`fix(raw): align source catalog with SFG fields`) aligne le catalogue sur les champs normatifs `season_year`, `landing_page`, `drive_file_id`, `source_name`, métadonnées source et `discovery_payload_hash`, tout en conservant les statuts d'alerte explicites.

## OE-002 — ObjectStore filesystem adressé par hash

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-001` est `DONE` dans le commit `47f7012`.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/__init__.py`, `python/metiquo/ingestion/object_store.py`, `tests/ingestion/test_object_store.py`, suppression du marqueur `.gitkeep`, `docs/progress.md`.
- **Migrations :** aucune ; le backend produit les clés relatives destinées à `raw.snapshots.object_key`.
- **Commandes/tests exécutés :** Ruff format/check ciblé ; mypy strict ciblé ; 5 tests ObjectStore ; suite Python complète sans infrastructure ; `git diff --check`.
- **Résultat exact :** le protocole `ObjectStore` et son backend `FilesystemObjectStore` écrivent par défaut sous `/data`. Chaque flux est d'abord consommé dans un répertoire temporaire situé sur le même filesystem, haché en SHA-256 pendant l'écriture et synchronisé, puis le répertoire complet est renommé atomiquement vers `year=YYYY/sha256=<digest>`. Le layout accepte `source.bin` ou `source.csv` et les documents JSON déterministes `manifest.json`, `schema.json` et `quality-report.json`. Une seconde écriture du même contenu réutilise l'objet physique sans changer fichier, métadonnée ni mtime ; une corruption au même emplacement lève une collision. Un flux interrompu ne laisse ni objet partiel ni répertoire temporaire. Les clés retournées sont relatives au store et indépendantes du chemin temporaire. Les 5 tests ciblés passent ; la suite globale sans PostgreSQL retourne 97 tests réussis et 6 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'interface permet un autre backend sans exposer le chemin temporaire, tandis que l'implémentation MVP reste le volume filesystem exigé.
- **Commit/hash :** `a8f96037eda3d1f2eba80138b86cf1f314a976ce` (`feat(ingestion): add immutable filesystem object store`).

## OE-003 — Découverte du catalogue Oracle’s Elixir

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-001` est `DONE`, y compris son alignement complet sur les champs SFG.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/catalog.py`, trois fixtures HTML sous `tests/fixtures/oracles_elixir/`, `tests/ingestion/test_catalog.py`, `tests/integration/test_catalog_repository.py`, `docs/progress.md`.
- **Migrations :** aucune nouvelle migration ; la persistance utilise `raw.source_catalog` créé par `20260905_0003`.
- **Commandes/tests exécutés :** inspection de la page officielle `https://oracleselixir.com/tools/downloads` dans le Navigateur intégré ; Ruff format/check ; mypy strict ; 6 tests unitaires de découverte ; tests de persistance et de contraintes PostgreSQL exécutés puis rejoués sur PostgreSQL 18 jetable ; suite Python complète avec PostgreSQL ; `git diff --check`.
- **Résultat exact :** le fetcher est borné en durée et taille et ne charge que la page officielle Oracle’s Elixir. L'extracteur HTML ignore tout domaine statistique tiers, accepte les formes Drive `/file/d/...`, `open?id=...` et `/folders/...`, puis associe une année uniquement lorsqu'un libellé possède une année unique. Le mécanisme de rapprochement détecte confirmation, nouvelle année, changement d'ID, doublon, disparition, lien non associable et plusieurs IDs ambigus. Une divergence ou ambiguïté est persistée en ligne séparée sans remplacer ni mettre à jour l'actif. Les confirmations mettent à jour `last_confirmed_at` et le SHA-256 du payload ; le premier `discovered_at` reste inchangé. Le 5 septembre 2026, le Navigateur a confirmé que la page officielle accessible expose seulement le dossier Drive `1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH`, sans lien annuel : la fixture correspondante produit donc `missing` et `unresolved`, et non une fausse confirmation. La suite complète retourne 110 tests réussis.
- **Blocker éventuel :** aucun ; le changement actuel de présentation est précisément rendu visible et sera traité par le fallback contrôlé de `OE-004` sans masquer la divergence.
- **ADR éventuel :** aucun ; Oracle’s Elixir reste l'unique source statistique LoL et la page officielle demeure le premier mécanisme obligatoire.
- **Commit/hash :** `65ef6c8244a587b68dee0872edf730099c2233d1` (`feat(ingestion): discover official source catalog`).

## OE-004 — Catalogue de secours versionné

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-003` est `DONE` et expose distinctement indisponibilité, page invalide et divergence.
- **Fichiers créés/modifiés :** `config/oracles_elixir_sources.yml`, `python/metiquo/ingestion/fallback_catalog.py`, `python/metiquo/ingestion/catalog.py`, `infra/compose/python.Dockerfile`, `.prettierignore`, `tests/ingestion/test_fallback_catalog.py`, `tests/integration/test_catalog_repository.py`, formatage de deux fixtures HTML, `docs/progress.md`.
- **Migrations :** aucune nouvelle migration ; l'origine et la mutabilité du bootstrap sont persistées dans `raw.source_catalog`.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 12 tests unitaires catalogue/fallback ; 2 tests d'intégration de persistance PostgreSQL ; suite complète avec PostgreSQL ; contrôle Prettier global ; validation Compose ; build neuf des images API et worker avec le fichier de configuration embarqué ; `git diff --check`.
- **Résultat exact :** le fichier versionné contient uniquement l'entrée 2026 exigée, ID `1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm`, `mutable=true` et `origin=validated-bootstrap`. Son parseur strict contrôle version, schéma, types, IDs et unicité annuelle, puis conserve le SHA-256 du fichier pour audit. Le service sélectionne ce fallback uniquement après `LandingPageUnavailable`; une page officielle accessible mais limitée au dossier Drive, trop volumineuse, invalide ou divergente n'est jamais masquée. L'origine bootstrap, la mutabilité, l'ID et le hash sont prouvés en PostgreSQL. La configuration est copiée dans `/app/config` des images runtime, cohérent avec `OE_SOURCE_CATALOG_PATH`. Les 117 tests de la suite complète passent, ainsi que la construction des deux images Python.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le fichier `.yml` emploie le sous-ensemble JSON strict de YAML 1.2 afin de rester lisible sans ajouter de parseur runtime.
- **Commit/hash :** `f6d9694c48685d92446941c5c01c64ce09511716` (`feat(ingestion): add controlled fallback catalog`).

## OE-005 — Contrat SourceTransport

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-001` et `FND-006` sont `DONE`.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/transport.py`, `python/metiquo/ingestion/__init__.py`, `python/metiquo/config.py`, `.env.example`, `docker-compose.yml`, `tests/ingestion/transport_contract.py`, `tests/ingestion/test_transport_contract.py`, marqueurs de packages de tests, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** formatage ciblé ; Ruff ; mypy strict ; 21 tests configuration/transport ; validation Compose ; `make check` via GNU Make absolu ; suite Python concise ; contrôle OpenAPI et génération TypeScript sans diff ; `git diff --check`.
- **Résultat exact :** `SourceRef`, `SourceMetadata` et `DownloadReceipt` sont immuables et valident provider Oracle’s Elixir, année, tailles, timestamps UTC et SHA-256. Le protocole runtime `SourceTransport` impose `name`, `policy`, `probe` et `download`. `TransportPolicy.from_settings` injecte les timeouts de connexion/lecture, limite de 4 Gio, maximum de redirections et retry borné ; les sept variables correspondantes sont validées par Pydantic, documentées dans `.env.example` et transmises aux conteneurs. Une implémentation de référence satisfait les assertions contractuelles partagées sur sonde, identité source, destination, octets et empreinte. La suite sans PostgreSQL retourne 119 tests réussis et 8 ignorés ; format, lint, types et contrats générés sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le contrat reste synchrone comme la SFG et sépare la politique de chaque implémentation.
- **Commit/hash :** `95ca6d9b9318444502375ace24357e033748105c` (`feat(ingestion): define source transport contract`).

## OE-006 — GoogleDriveApiTransport

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-005` est `DONE` et fournit les DTO, le protocole et la politique commune.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/google_drive_api.py`, `python/metiquo/ingestion/source_errors.py`, `python/metiquo/config.py`, `tests/ingestion/test_google_drive_api.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 8 tests Drive API ; 19 tests ciblés Drive/configuration ; suite Python complète ; `git diff --check`.
- **Résultat exact :** `GoogleDriveApiTransport` n'est construit depuis les settings que lorsqu'un bearer autorisé non vide est présent et masqué par `SecretStr`. Il interroge l'endpoint metadata Drive v3, vérifie l'ID et la taille, puis télécharge `alt=media` en blocs de 256 Kio avec SHA-256 incrémental, `fsync`, limite avant et pendant le flux, timeouts injectés et redirections bornées. Les réponses Drive sont classées en not-found, permission, quota, rate-limit, timeout, taille, réponse invalide ou indisponibilité, avec code sûr et possibilité de retry. Les tests prouvent qu'une erreur quota HTTP 403 ne crée aucun fichier, qu'un dépassement en cours de flux supprime le partiel et que le credential n'apparaît ni dans le transport, ni dans l'exception sérialisée. Le transport satisfait les contract tests communs ; la suite retourne 127 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun ; l'activation en environnement réel nécessitera naturellement un bearer fourni hors dépôt.
- **ADR éventuel :** aucun ; l'API Drive autorisée reste prioritaire conformément à la SFG, sans mécanisme de contournement de quota.
- **Commit/hash :** `50f2c5a6f4d96592d6f2e8bb22a81c8f944b9027` (`feat(ingestion): add Google Drive API transport`).
- **Correctif/hash :** `40ede5414254013a13633b943d691e2559509f7e` garantit aussi qu'un échec d'ouverture exclusive ne supprime jamais une destination API préexistante ; le test conserve exactement les octets initiaux.

## OE-007 — GoogleDrivePublicHttpTransport

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-005` est `DONE` ; le transport API `OE-006` reste prioritaire lorsqu'il est configuré.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/google_drive_public.py`, `python/metiquo/ingestion/source_errors.py`, trois fixtures HTML quota/consent/login, `tests/ingestion/test_google_drive_public.py`, renforcement de `tests/ingestion/test_google_drive_api.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** formatage Ruff et Prettier des fixtures ; Ruff check ; mypy strict global ; 17 tests ciblés Drive API/public ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** `GoogleDrivePublicHttpTransport` utilise exclusivement l'URL publique standard `drive.google.com/uc?export=download&id=…`, sans paramètre `confirm`, cookie extrait ni boucle de contournement. Connexion, lecture et redirections sont bornées par la politique commune. Le premier bloc et le type MIME sont inspectés avant toute création de fichier : les pages HTML de quota, consentement et connexion sont refusées en HTTP 200 comme en HTTP 403, y compris lorsqu'une page HTML ment avec `application/octet-stream`. Le flux binaire est haché et synchronisé par blocs ; limite de taille et nettoyage du partiel sont conservés. Les transports API et public préservent tous deux une destination préexistante. Le contract test commun passe et la suite retourne 136 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; ce fallback public respecte le flux officiel et refuse explicitement tout bypass de quota.
- **Commit/hash :** `40ede5414254013a13633b943d691e2559509f7e` (`feat(ingestion): add safe public Drive transport`).

## OE-008 — MirrorTransport et LocalFixtureTransport

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-002` et `OE-005` sont `DONE`.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/local_transports.py`, `python/metiquo/ingestion/transport.py`, `tests/fixtures/oracles_elixir/sample_2026.csv`, `tests/ingestion/test_local_transports.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 14 tests ciblés locaux/contrat ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** `MirrorTransport` ne résout que le dernier `MirrorSnapshot` déjà validé, relit son objet immuable, contrôle taille et SHA-256 avant de remettre une copie, et échoue si l'année diverge. L'instant de validation du miroir et l'instant optionnel de dernière confirmation de la source sont distincts dans `SourceMetadata`; sans confirmation, `source_is_confirmed` reste faux, donc le miroir n'invente aucune fraîcheur. `LocalFixtureTransport` sert la fixture CI versionnée et refuse sa construction en `DataMode.REAL`. Le plan de priorité retourne API Drive puis HTTP public puis miroir en réel, mais la fixture seule en mock et rejette toute fixture ajoutée au plan réel. Les deux implémentations passent les assertions contractuelles communes ; la suite retourne 140 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le miroir est une copie privée validée, jamais une nouvelle source ni une preuve de fraîcheur.
- **Commit/hash :** `1d5056bae0855d1b13cb883839e86a81705e7cc1` (`feat(ingestion): add mirror and fixture transports`).

## OE-009 — Téléchargeur sûr en streaming

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-005` est `DONE` et tous les transports implémentés satisfont son contrat.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/safe_download.py`, `python/metiquo/ingestion/source_errors.py`, `python/metiquo/ingestion/transport.py`, `python/metiquo/config.py`, `.env.example`, `docker-compose.yml`, `tests/ingestion/test_safe_download.py`, ajustement du test de politique transport, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 8 tests ciblés de téléchargement sûr dont flux de 32 Mio sous `tracemalloc` ; suite Python complète ; contrôle Prettier global ; validation Compose ; `git diff --check`.
- **Résultat exact :** `SafeDownloader` réserve un répertoire temporaire privé `0700` sur le même volume, impose une destination interne `.part`, appelle le transport en streaming, mesure la durée totale configurable, contrôle identité du reçu, taille physique, SHA-256 recalculé et empreinte attendue optionnelle. Il inspecte seulement 64 Kio pour refuser HTML, incohérences MIME, texte non UTF-8 ou délimiteur ambigu et pour reconnaître CSV, gzip ou zip. Le fichier est passé en `0600` puis renommé atomiquement vers son nom final ; tout échec supprime le répertoire temporaire, tandis qu'une destination existante est préservée. Le test de 32 Mio conserve un pic Python inférieur à 8 Mio, des blocs source de 64 Kio et aucun `.part` résiduel ; interruption, timeout, hash divergent, contenu invalide et conflit de promotion sont couverts. La suite retourne 148 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le composant centralise la promotion locale sans modifier le contrat synchrone des transports.
- **Commit/hash :** `0f6081f38f44f805cf7dcd52775352b56faaa6b8` (`feat(ingestion): add safe streaming download promotion`).

## OE-010 — Taxonomie d’erreurs et retries

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-006`, `OE-007` et `OE-009` sont `DONE`.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/source_errors.py`, `python/metiquo/ingestion/retry.py`, `tests/ingestion/test_source_errors_retry.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 15 tests ciblés de taxonomie/retry ; suite Python complète ; contrôle Prettier global ; validation Compose ; `git diff --check`.
- **Résultat exact :** les douze exceptions normatives existent avec codes stables : not-found, permission, quota, rate-limit, timeout, HTML inattendu, type inattendu, checksum, archive corrompue, schéma incompatible, qualité et promotion atomique. Chaque instance conserve message sûr, transport, ID source, statut HTTP, contexte, timestamp UTC, compteur de tentatives et possibilité de retry dans `to_dict`. `RetryExecutor` applique un backoff exponentiel plafonné avec jitter injecté uniquement à quota, rate-limit, timeout et indisponibilité. Trois échecs avant succès produisent exactement les délais contrôlés `1,0`, `4,0`, `3,75` secondes ; un dernier échec porte `attempts=3`. Une permission permanente artificiellement marquée retryable n'est malgré tout appelée qu'une fois et ne dort jamais. La suite retourne 163 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la liste et la sémantique viennent directement de la SFG.
- **Commit/hash :** `cc00bd06d6c20e9f051031e9c0e72eaa7f2a72db` (`feat(ingestion): add source error taxonomy and retries`).

## OE-011 — Manifeste et empreintes de snapshot

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-009` est `DONE` et fournit un téléchargement physiquement validé.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/manifest.py`, `tests/ingestion/test_manifest.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 5 tests ciblés manifeste/stockage ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** `SnapshotManifest` sérialise de façon canonique et relit strictement provider, année, ID Drive, demande/téléchargement/confirmation UTC, transport, taille, SHA-256, type observé, compression, encodage, délimiteur, empreinte du schéma, nombre de lignes, dates métier min/max, statut/détail qualité et version du code. `SchemaDocument` impose positions consécutives et noms uniques ; son empreinte stable change dès qu'un type change. `store_snapshot` rapproche manifeste, reçu et schéma, écrit les trois documents dans l'ObjectStore, rouvre la source stockée et recalcule son SHA-256 avant de rendre le snapshot utilisable. Les tests prouvent le round-trip exact, le layout complet, le rejet avant stockage d'un manifeste incohérent et le blocage d'un store qui ment après promotion. La suite retourne 168 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la sérialisation déterministe renforce l'identification reproductible du dataset exigée par la SFG.
- **Commit/hash :** `0ed9fa0d97d370d7adac16d873d1cb4c7f42f879` (`feat(ingestion): add immutable snapshot manifest`).

## OE-012 — Validation physique

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-009` et `OE-011` sont `DONE`.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/physical_validation.py`, renforcement de `python/metiquo/ingestion/safe_download.py` et `source_errors.py`, trois fixtures invalides JSON/CSV, `tests/ingestion/test_physical_validation.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** formatage Ruff/Prettier ; Ruff check ; mypy strict global ; 11 tests ciblés de validation physique ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** la validation précoce refuse corps vide, HTML reconnu par MIME ou magic bytes, JSON d'erreur, encodage inconnu, délimiteur absent/ambigu et incohérence MIME/magic, avec un code de règle dans le contexte sûr. `PhysicalValidator` relit taille et SHA-256, compare la taille au précédent selon un ratio configurable avec approbation explicite, ouvre réellement gzip/zip, exige un unique CSV dans un zip, détecte UTF-8/BOM et délimiteur sans correction, valide un en-tête non numérique aux noms uniques puis scanne toutes les lignes pour un nombre de colonnes constant. Chaque rejet testé porte un diagnostic stable ; aucune destination finale n'apparaît lors des rejets précoces et aucun snapshot n'est envoyé au store. CSV, gzip et zip valides retournent header, colonnes et lignes exacts. La suite retourne 179 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les règles matérialisent la section 9.10 de la SFG sans inférence réparatrice.
- **Commit/hash :** `6019ae8c553721578ee2b295c68eacde924e7ab6` (`feat(ingestion): validate physical source files`).

## OE-013 — Contrat de schéma évolutif

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-012` est `DONE` et garantit un CSV physiquement lisible.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/schema_contract.py`, fixtures `schema_additive.csv` et `schema_missing_core.csv`, `tests/ingestion/test_schema_contract.py`, `docs/progress.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 5 tests ciblés schéma/capacités ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** `EvolvingSchemaContract` distingue sept colonnes cœur, les colonnes optionnelles et les exigences propres à `market.match_winner`, `feature.team_form`, `feature.side_strength` et `feature.early_game`. Chaque header observé produit un `SchemaDocument` qui conserve l'ordre et toutes les colonnes additives dans le raw, une empreinte, les absences et une matrice de capacités. La fixture avec `vendor_metric` peut être ingérée, conserve la valeur `42` et ne change pas les capacités compatibles. L'absence de `gameid` bloque l'ingestion avec le diagnostic `SCHEMA_CORE_MISSING`; l'absence de `datacompleteness` ne bloque pas le raw mais désactive uniquement le marché match-winner sans reconstruire une complétude. Le diff rapporte ajout, retrait, changement de type et ordre, et l'empreinte inclut les additives. La suite retourne 184 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le registre de capacités matérialise l'abstention ciblée exigée par la SFG.
- **Commit/hash :** `42347a6a4afb490371eb274cbf7ff726d68c4906` (`feat(ingestion): add evolving schema contract`).

## OE-014 — Data Quality métier

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-013` est `DONE` et expose les colonnes/capacités réellement disponibles.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/data_quality.py`, fixtures `dq_valid.csv` et `dq_problematic.csv`, `tests/ingestion/test_data_quality.py`, `docs/progress.md`.
- **Migrations :** aucune ; `QualityReport.to_dict` fournit le contenu déterministe de `quality-report.json` et les issues prêtes pour `raw.quality_issues`.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 15 tests ciblés DQ ; suite Python complète ; contrôle Prettier global ; `git diff --check`.
- **Résultat exact :** `DataQualityValidator` scanne IDs game/participant, validité et plausibilité des dates, unicité des clés naturelles, cohérence participant-équipe par side, équipes opposées distinctes, sides, plages numériques, gagnant/perdant, structure des deux lignes équipe et des dix lignes joueur. Il signale explicitement games incomplètes, remakes et forfeits. La comparaison au précédent bloque une suppression massive sous le ratio configuré sauf approbation explicite et compte les clés disparues. Les 17 codes `QualityCode` sont stables ; chaque issue porte severity `blocking`, `capability-only` ou `warning`, ligne, clé, capacité et contexte. Une game incomplète désactive seulement `market.match_winner`; une structure joueur partielle seulement `feature.player_form`. La fixture valide passe 12 lignes sans issue, la fixture problématique produit les trois niveaux, et `require_pass` lève un `DataQualityFailed` structuré. La suite retourne 199 tests réussis et 8 ignorés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les seuils et abstentions suivent directement les règles métier SFG.
- **Commit/hash :** `16380b7e926309128a9054c4bec32a2e62c48263` (`feat(ingestion): enforce business data quality`).

## OE-015 — Quarantaine durable

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-014` fournit le diagnostic DQ structuré et `OE-002` le stockage immuable adressé par contenu.
- **Fichiers créés/modifiés :** `python/metiquo/ingestion/quarantine.py`, `tests/integration/test_quarantine.py`, `docs/progress.md`.
- **Migrations :** aucune ; les tables `raw.snapshots` et `raw.quarantine_items` créées par `OE-001` sont utilisées sous transaction PostgreSQL réelle.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ; test d'intégration PostgreSQL dédié ; `make check` complet avec PostgreSQL et contrat OpenAPI.
- **Résultat exact :** `QuarantineService.capture` conserve la source rejetée et ses manifestes dans un ObjectStore dédié, puis crée un snapshot `quarantined` et une entrée `pending` contenant code et diagnostic. `SnapshotReader` filtre structurellement sur `validated`, de sorte que le dernier snapshot validé reste courant avant comme après résolution. Une décision exige acteur, motif et sink d'audit ; elle verrouille la ligne, refuse toute seconde décision et ne promeut jamais automatiquement le snapshot, même lorsqu'elle vaut `accepted`. Le test réel vérifie aussi le contenu physique et les JSON de diagnostic. La suite retourne 208 tests réussis, sans test ignoré avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'acceptation d'une quarantaine est une décision auditée distincte d'une promotion de données.
- **Commit/hash :** `4a7a38d` (`feat(ingestion): quarantine invalid snapshots`).

## OE-016 — Promotion atomique du snapshot

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-011`, `OE-014` et `OE-015` sont `DONE` ; seuls les objets relus, intègres et non bloqués peuvent atteindre la publication.
- **Fichiers créés/modifiés :** migration `20260905_0004`, `python/metiqo/db/raw_models.py`, `python/metiqo/ingestion/promotion.py`, extension du lecteur de snapshots et tests PostgreSQL de promotion/quarantaine/migration.
- **Migrations :** ajout facultatif de `raw.source_catalog.current_snapshot_id` avec clé étrangère composite garantissant que la cible appartient au même catalogue ; upgrade/downgrade testés.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; tests PostgreSQL ciblés ; `make check` complet avec base réelle et contrat OpenAPI.
- **Résultat exact :** `SnapshotPromotionService` relit et recalcule le hash de l'objet immuable avant transaction, refuse un rapport DQ bloquant, verrouille catalogue et run, crée ou réutilise un snapshot validé, déplace le pointeur courant et clôt le run avec ses compteurs dans une transaction unique. Le résultat n'est rendu qu'après sortie réussie du commit. Une observation concurrente juste avant commit voit encore l'ancien pointeur, le run `running` et zéro nouveau snapshot ; une panne injectée à cet instant lève `ATOMIC_PROMOTION_FAILED`, restaure entièrement l'état DB et conserve seulement l'objet immuable sans visibilité courante. En succès, les trois changements deviennent visibles ensemble. La suite retourne 210 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le pointeur explicite évite de confondre ordre temporel et publication atomique.
- **Commit/hash :** `fdf1889` (`feat(ingestion): promote snapshots atomically`).

## OE-017 — Staging et chargement raw tabulaire

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-016` garantit que seuls un snapshot validé et son pointeur courant peuvent être chargés.
- **Fichiers créés/modifiés :** migration `20260905_0005`, `python/metiqo/db/raw_models.py`, `python/metiqo/ingestion/raw_loader.py`, tests PostgreSQL de chargement et de migrations.
- **Migrations :** création de `raw.canonical_rows` avec clé naturelle unique, hash de ligne, payload JSON complet, date métier, provenance snapshot/run, révision et garde-fous de suppression par clés étrangères restrictives.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; tests PostgreSQL ciblés ; `make check` complet avec base réelle et contrat OpenAPI.
- **Résultat exact :** `RawTabularLoader` lit le CSV en lots configurables, conserve les colonnes additives, calcule une clé naturelle canonique sur `(gameid, participantid)` et un hash déterministe, puis charge une table temporaire propre au run avec `ON COMMIT DROP`. Une stratégie de secours n'est utilisée que si elle est explicitement configurée. Le merge classe inserted, updated, unchanged et quarantined, ignore les clés invalides ou dupliquées, ne supprime jamais une ligne absente et clôt le run dans la même transaction. Le test charge deux fois le même snapshot : `12/0/0/0`, puis `0/0/12/0`, avec exactement 12 lignes canoniques de révision 1 et aucune table de staging résiduelle. La suite retourne 211 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** le module standard `csv` avec insertions par lots est retenu à ce stade : il fournit le flux adapté demandé sans ajouter Polars, tout en conservant le contrat remplaçable derrière le loader.
- **Commit/hash :** `8935c2a` (`feat(ingestion): load raw rows idempotently`).

## OE-018 — Historiser les révisions de lignes

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-017` fournit la clé naturelle, le hash déterministe, le staging et le merge canonique.
- **Fichiers créés/modifiés :** migration `20260906_0006`, `python/metiqo/db/raw_models.py`, extension de `python/metiqo/ingestion/raw_loader.py` et du test PostgreSQL de chargement.
- **Migrations :** ajout de la date métier aux révisions, création d'une baseline pour les lignes déjà canoniques, remplacement de l'unicité du hash par un index autorisant un retour légitime à une ancienne valeur, et trigger append-only interdisant UPDATE/DELETE.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; tests PostgreSQL ciblés avec upgrade/downgrade ; `make check` complet et contrat OpenAPI.
- **Résultat exact :** avant chaque upsert, le loader insère une révision pour toute ligne nouvelle ou dont le hash change, avec payload avant/après récupérable, snapshot, run, date métier, numéro séquentiel, opération et lien vers la révision précédente. La transaction sérialise le catalogue, donc révision et canonique avancent ensemble. Le scénario de correction passe de `kills=2` à `kills=99`, crée exactement les révisions 1 et 2 correctement chaînées, laisse dix lignes inchangées sans fausse révision et conserve dans le canonique la douzième ligne absente du fichier partiel. Les tentatives SQL d'UPDATE et DELETE de l'historique échouent. La suite retourne 212 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'historique append-only et la non-suppression suivent directement `SFG-DATA-005`.
- **Commit/hash :** `91199f3` (`feat(ingestion): historize row revisions`).

## OE-019 — Diff année courante et invalidation

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-018` fournit des révisions append-only datées et rattachées à leur run.
- **Fichiers créés/modifiés :** migration `20260906_0007`, `python/metiqo/db/feature_models.py`, `python/metiqo/ingestion/invalidation.py`, tests PostgreSQL de migrations et de corrections rétroactives.
- **Migrations :** création de `features.invalidations` avec plage affectée, provenance, nombre de révisions, unicité par run, index temporel et trigger append-only.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; tests PostgreSQL ciblés avec upgrade/downgrade ; `make check` complet et contrat OpenAPI.
- **Résultat exact :** `RevisionInvalidationService` ne considère que les révisions `updated` d'un run terminé, refuse une correction sans date métier et agrège une source unique. Il émet de façon idempotente un marqueur `RAW_ROW_REVISED` dont `affected_from` est la date minimale et `changed_through` la date maximale observée ; la reconstruction reste donc demandée à partir de la première date touchée. Deux corrections aux 8 et 10 janvier donnent un seul événement à partir du 8, tandis qu'un run d'insertions seules n'émet rien. Le service n'importe ni ne modifie aucune persistance de prédiction ; le test confirme que le schéma `ml` reste vide et que PostgreSQL refuse de modifier l'invalidation publiée. La suite retourne 212 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les consommateurs futurs créeront de nouvelles versions de features depuis ce marqueur, sans réécrire snapshots ou prédictions passées.
- **Commit/hash :** `71c3509` (`feat(features): emit revision invalidations`).

## OE-020 — États de fraîcheur et politiques stale

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-016` fournit le pointeur courant validé et `OE-010` les codes d'échec source structurés.
- **Fichiers créés/modifiés :** `python/metiqo/ingestion/freshness.py`, configuration serveur, `.env.example`, Compose, tests unitaires de politique et extension du test PostgreSQL de quarantaine.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; 11 tests de fraîcheur ; test PostgreSQL de quarantaine ; validation Compose ; `make check` complet et contrat OpenAPI.
- **Résultat exact :** `PostgresFreshnessRepository` ne lit comme utilisable que le snapshot explicitement pointé et `validated`, puis expose les échecs ou quarantaines plus récents. `FreshnessService` classe `fresh`, `stale`, `degraded`, `failed` et `quarantined`, publie `asOf`, `snapshotId`, âge, SLA et code de raison. Le SLA initial de 10 800 secondes est configurable. `allow-stale` peut réutiliser le dernier validé en annonçant son état non frais, mais n'invente jamais un snapshot ; `require-fresh` refuse tout autre état avec `FreshDataRequired.exit_code=3`. Le test réel prouve qu'une quarantaine résolue reste annoncée tout en ne rendant utilisable que l'ancien snapshot validé. La suite retourne 223 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; fraîcheur et politique de consommation sont séparées pour rendre l'état observable même lorsqu'une politique le refuse.
- **Commit/hash :** `5060ebc` (`feat(ingestion): enforce freshness policies`).

## OE-021 — Backfill multi-années reprenable

- **Statut :** `DONE`
- **Dépendances vérifiées :** catalogue `OE-003`, chargement/révisions `OE-017`/`OE-018` et politique de fraîcheur `OE-020` sont disponibles pour le processeur annuel injecté.
- **Fichiers créés/modifiés :** migration `20260906_0008`, `python/metiqo/db/raw_models.py`, `python/metiqo/ingestion/backfill.py`, tests PostgreSQL de reprise/concurrence et listes de tables de migration.
- **Migrations :** création de `raw.backfill_jobs` rendu unique par empreinte de requête et `raw.backfill_years` avec statut, tentatives, dernier run, erreur et timestamps par année.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; tests PostgreSQL ciblés avec upgrade/downgrade ; `make check` complet et contrat OpenAPI.
- **Résultat exact :** `BackfillOrchestrator` matérialise toute plage inclusive, saute les années réussies et retente les états pending/running/failed. Il détient un verrou advisory PostgreSQL de session dérivé de `(provider, année)` pendant le processeur annuel, puis lie le run produit au checkpoint. Un arrêt simulé après 2024 laisse 2025 `running` ; la reprise appelle 2025 à la tentative 2 puis 2026, sans rejouer 2024, et un troisième appel converge sans travail. Deux exécutions concurrentes partagent le même job ; une seule acquiert le verrou 2026 et appelle le processeur. La suite retourne 225 tests réussis avec PostgreSQL disponible.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les advisory locks PostgreSQL évitent une infrastructure distribuée supplémentaire au MVP.
- **Commit/hash :** `9ecffd8` (`feat(ingestion): resume multi-year backfills`).

## OE-022 — CLI et Make Oracle’s Elixir

- **Statut :** `DONE`
- **Dépendances vérifiées :** le backfill reprenable `OE-021` et l'ensemble des composants `OE-003` à `OE-020` sont assemblés par un coordinateur annuel sans nouveau chemin de transport.
- **Fichiers créés/modifiés :** `python/metiqo/ingestion/sync.py`, package `python/metiqo/cli`, point d'entrée `oe` dans `pyproject.toml`, `Makefile`, tests CLI PostgreSQL et alias Make, `README.md`.
- **Migrations :** aucune nouvelle migration ; la CLI exige que la base soit déjà à la révision Alembic courante.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; parcours PostgreSQL réel `catalog refresh → sync → verify → diff → second sync → rebuild-canonical → backfill` avec ObjectStore temporaire et fixture locale en mode mock ; simulations des sept alias Make ; `make check` complet sur une base PostgreSQL jetable recréée vide.
- **Résultat exact :** la commande `oe` expose `catalog refresh`, `backfill`, `sync`, `verify`, `diff` et `rebuild-canonical`. Le mode mock exige explicitement `--fixture` et ne construit aucun transport réseau ; le mode réel conserve l'ordre API Drive optionnelle, téléchargement public puis miroir validé. La sortie `--json` est compacte et les codes `0`, `2`, `3`, `4`, `5` et `6` distinguent succès, usage/configuration, fraîcheur stricte, source/pipeline, intégrité et backfill partiel. Le parcours d'intégration publie 12 lignes au premier run, retrouve le même snapshot et 12 lignes inchangées au second, vérifie le hash, compare les manifestes, rejoue le canonical puis termine le backfill. La suite complète retourne 228 tests réussis avec PostgreSQL disponible ; composants, format, lint, types et OpenAPI sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la CLI compose les frontières déjà imposées par la SFG et ne crée ni source statistique alternative ni accès local non déclaré.
- **Commit/hash :** `d61d758` (`feat(ingestion): expose Oracle Elixir operator CLI`).

## OE-023 — API/admin et UI santé réelles

- **Statut :** `DONE`
- **Dépendances vérifiées :** la politique de fraîcheur `OE-020`, la CLI/coordinator `OE-022` et le dashboard de santé `UI-008` sont disponibles.
- **Fichiers créés/modifiés :** projections PostgreSQL `python/metiqo/repositories/postgres_admin.py`, service de mutation réelle idempotente, routes API réelles, branchement conditionnel dans la fabrique FastAPI, enrichissements optionnels du contrat `IngestionRunSummary`, contrat OpenAPI et client généré, dashboard partagé, tests API PostgreSQL et Playwright real-fixture.
- **Migrations :** aucune nouvelle migration ; les projections lisent `raw.source_catalog`, `raw.snapshots`, `raw.ingestion_runs`, `raw.quality_issues`, `raw.quarantine_items` et les jobs de backfill existants.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; TypeScript strict ; génération et vérification OpenAPI ; test d'intégration API mock/réel sur PostgreSQL ; `make check` sur base jetable vide ; Playwright ciblé `real-data-health.spec.ts` sur build de production ; inspection Navigateur d'une API réelle et d'un frontend démarré avec `APP_DATA_MODE=real`.
- **Résultat exact :** les endpoints `data-sources`, `ingestion-runs`, `quality-issues`, `jobs` et `oracles-elixir/sync` sont disponibles en mode réel sans monter les autres domaines prématurément. Mock et réel sérialisent les mêmes clés de DTO ; les champs de provenance optionnels exposent hash, année, lignes, plage métier, empreinte/changement de schéma, transport et code d'erreur. Une tentative en échec plus récente classe la source `degraded` tout en conservant le dernier snapshot validé et toutes les lectures en HTTP `200`. Le sync réel assure l’unicité de sa clé d'idempotence et n'accepte aucune fixture. Le Navigateur a confirmé le badge `REAL`, le hash, les 12 lignes, la couverture, le schéma stable, l'historique, l'anomalie ouverte et la quarantaine sur le même composant que le mock. La suite complète retourne 229 tests réussis ; le test Playwright real-fixture passe sur le build de production.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la différence de mode se situe dans les adaptateurs et les métadonnées, pas dans les composants UI ni les contrats publics.
- **Commit/hash :** `d91ab04` (`feat(admin): expose real ingestion health`).

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
- **Correctifs CI/hashes :** `55d9d77758e6f47acafa840279a99bc60dfc83af` (`test: stabilize Playwright across platforms`) ajoute les baselines Linux et rend les clés d'idempotence du parcours mapping stables ; `95eb64cdc4a1d504a6394215cbf3fae17e769912` (`fix: bundle Inter for stable rendering`) ajoute la police au bundle ; `fe11ec634c1fc05f2bd7f94550593aa5554e0cea` (`fix: use the bundled variable font`) relie le token du design system à la famille embarquée et régénère les références. Le test mapping passe deux fois de suite contre le même processus mock, les références visuelles passent sous Windows et dans l'image Linux Playwright, puis les 33 tests E2E passent ensemble.

## OE-024 — Suite de fixtures OE critique

- **Statut :** `DONE`
- **Dépendances vérifiées :** validations physique `OE-012`, qualité `OE-014`, révisions `OE-018` et fraîcheur `OE-020` sont `DONE` et directement exercées.
- **Fichiers créés/modifiés :** dix fixtures minimisées, manifeste d’observation historique et documentation d’origine dans `tests/fixtures/oracles_elixir`, plus `tests/ingestion/test_critical_fixtures.py`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ; 7 tests de fixtures ciblés ; suite ingestion et intégration du gate via `make test-ingestion`.
- **Résultat exact :** les cas SFG §25.2 valide, additive, cœur manquant, duplicate, incomplete, remake, correction rétroactive, tronqué, HTML quota, BOM/délimiteur inattendu et archive corrompue possèdent chacun une issue exécutable distincte. Toutes les lignes sont synthétiques et ne recopient aucune donnée Oracle’s Elixir. Les blobs binaires restent lisibles en Base64. Une observation SHA-256 historique est vérifiée comme preuve, puis un payload courant modifié est téléchargé avec son hash recalculé, sans réutilisation de l’ancien hash comme attente. Le gate ingestion retourne 142 tests réussis sur PostgreSQL réel.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les fixtures sont des données de test synthétiques minimales.
- **Commit/hash :** `a77dbce` (`test(ingestion): cover critical Oracle Elixir fixtures`).

## OE-025 — Gate P2 — reconstruction data fiable

- **Statut :** `DONE`
- **Dépendances vérifiées :** l’API/UI de santé réelle `OE-023` et la matrice de fixtures `OE-024` sont `DONE` ; tous les composants `OE-001` à `OE-024` sont inclus dans la cible du gate.
- **Fichiers créés/modifiés :** intégration de quarantaine dans le coordinateur annuel, `infra/scripts/demo_ingestion_gate.py`, `tests/integration/test_ingestion_gate.py`, cible `make test-ingestion`, guide opérateur `README.md` et présent journal.
- **Migrations :** le script crée une base PostgreSQL éphémère nommée par le programme, applique les migrations jusqu’à `20260906_0008`, puis supprime uniquement cette base ; aucune migration nouvelle.
- **Commandes/tests exécutés :** démonstration JSON autonome sur PostgreSQL 18 ; `make test-ingestion` depuis un conteneur neuf ; `make check` global sur une seconde base neuve ; Ruff format/check ; mypy strict ; vérification du diff et du contrat OpenAPI.
- **Résultat exact :** depuis une base vide, le catalogue bootstrap est chargé puis le backfill fixture réussit. Deux syncs du même fichier conservent 12 lignes, le même snapshot et l’empreinte canonique `8cc193e74ab3b0ca7ff8deb1df226a6b0155767ef41c73ef0ee014e489687ef8`, avec 12 lignes `unchanged` au second run. La page quota produit zéro snapshot et `allow-stale` retourne `degraded` avec le snapshot validé précédent. Un nouveau hash privé de colonne cœur est conservé dans l’ObjectStore de quarantaine avec `SCHEMA_INCOMPATIBLE`, lié au run, sans déplacer le pointeur courant ; une répétition sous `require-fresh` retourne le code `3`. Une colonne additive passe, une correction rétroactive met à jour exactement une ligne et publie une invalidation à partir du `2026-01-10`, puis `oe verify` relit hash et taille du snapshot final. La cible agrégée retourne 142 tests réussis, couvrant aussi reprise de backfill, concurrence et atomicité de promotion. Le contrôle global retourne 237 tests Python, 16 tests UI et 4 tests web réussis ; format, lint, orthographe, types et OpenAPI sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le gate assemble les décisions SFG déjà implémentées et sa base temporaire est volontairement isolée.
- **Commit/hash :** `79f0053` (`feat(ingestion): prove reliable reconstruction gate`).
