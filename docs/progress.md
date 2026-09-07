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

## CNL-001 — Dimensions canoniques LoL

- **Statut :** `DONE`
- **Dépendances vérifiées :** l’historisation raw `OE-018`, les conventions PostgreSQL `FND-004` et le gate P2 `OE-025` sont `DONE` sur `main`.
- **Fichiers créés/modifiés :** migration `20260906_0009`, modèles `python/metiquo/db/core_models.py`, projection `python/metiquo/canonical/dimensions.py`, enregistrement Alembic des métadonnées et tests PostgreSQL de migration/provenance.
- **Migrations :** création de `core.game_titles`, `core.competitions`, `core.teams`, `core.players` et `core.patches`, avec UUID canoniques, identité source, nom normalisé et provenance obligatoire vers ligne raw, snapshot et run.
- **Commandes/tests exécutés :** Ruff format/check ciblé ; mypy strict global sur 144 fichiers ; cycle Alembic upgrade/downgrade/upgrade ; tests PostgreSQL ciblés des migrations et dimensions.
- **Résultat exact :** `CanonicalDimensionBuilder` ne lit que les lignes Oracle’s Elixir dont le snapshot est `validated` et le run `succeeded`. Il produit des UUID v5 déterministes, normalise les identités Unicode sans les enrichir depuis une source externe, privilégie les identifiants OE `teamid`/`playerid` et n’utilise les noms OE qu’en secours explicite. Deux exécutions donnent les mêmes identifiants et cardinalités. La fixture PostgreSQL matérialise un titre, une compétition, deux équipes, deux joueurs et un patch ; une ligne rattachée à un snapshot mis en quarantaine reste absente. Chaque ligne projetée retrouve sa ligne raw, son snapshot validé, son run réussi, sa révision et `canonical-dimensions-v1`. Les trois tests ciblés passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les dimensions appliquent directement l’interdiction P3 de calculer depuis un téléchargement ad hoc.
- **Commit/hash :** `60ad1b3` (`feat(canonical): add traceable LoL dimensions`).

## CNL-002 — core.games et statistiques équipes/joueurs

- **Statut :** `DONE`
- **Dépendances vérifiées :** les dimensions traçables `CNL-001` sont `DONE` et reconstruites automatiquement avant les faits.
- **Fichiers créés/modifiés :** migration `20260906_0010`, extension des modèles core, projection `python/metiquo/canonical/games.py`, exports canoniques et tests PostgreSQL de fixtures.
- **Migrations :** création de `core.games`, `core.game_team_stats` et `core.game_player_stats` avec identités déterministes, liens aux dimensions, contraintes de structure, provenance raw obligatoire et documents JSONB d’availability.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cycle complet Alembic ; tests PostgreSQL des migrations, dimensions et faits exécutés sur PostgreSQL 18.
- **Résultat exact :** quatre fixtures matérialisent une partie complète, une incomplète, un remake et un forfeit depuis 18 lignes raw validées. Chaque partie expose séparément `complete`, `remake`, `forfeit`, `usable_for_training` et `quality_status`. Toute partie marquée complète possède exactement deux équipes Blue/Red distinctes et un seul résultat gagnant. La partie complète produit dix lignes joueurs par rôle ; les trois autres conservent leurs deux lignes équipes. Les champs source absents, notamment gold et assists, restent `NULL` et leur clé d’availability vaut `false`, sans zéro de remplacement. Un second build conserve tous les UUID et cardinalités ; les quatre tests canoniques/migrations passent.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les faits ne consomment que les lignes raw validées déjà persistées et les champs OE réellement présents.
- **Commit/hash :** `d0f135e` (`feat(canonical): project traceable game facts`).

## CNL-003 — Reconstruction des séries

- **Statut :** `DONE`
- **Dépendances vérifiées :** les games et résultats d’équipe `CNL-002` sont `DONE` et reconstruits avant les séries.
- **Fichiers créés/modifiés :** migration `20260906_0011`, modèle `core.series`, statut de résolution sur `core.games`, projection `python/metiquo/canonical/series.py` et test PostgreSQL dédié.
- **Migrations :** création de `core.series` avec format, équipes, score, résultat, qualité, provenance et clé déterministe ; ajout de `series_id` facultatif et `series_resolution_status` fermé sur les games.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cycle Alembic complet ; cinq tests PostgreSQL migrations/canonique sur PostgreSQL 18.
- **Résultat exact :** l’identifiant `seriesid` OE est prioritaire. En son absence, le fallback n’utilise que compétition, date, paire d’équipes, format et ordre de game ; deux games portant le même ordre dans ce contexte sont marquées `ambiguous` et restent sans `series_id`. Une série BO3 identifiée par OE se clôt à 2–0 avec gagnant traçable. Une série fallback BO2 à 1–1 expose `allows_draw=true`, `result_status=draw`, aucun gagnant et deux scores à 1. Deux reconstructions conservent les mêmes UUID, deux séries résolues, quatre games liées et deux games ambiguës.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le fallback minimal est volontairement refusé dès que l’ordre ne rend pas le regroupement univoque.
- **Commit/hash :** `1d9c212` (`feat(canonical): reconstruct unambiguous series`).

## CNL-004 — Observations historiques de roster

- **Statut :** `DONE`
- **Dépendances vérifiées :** les dimensions `CNL-001` et les joueurs réellement observés dans les games `CNL-002` sont `DONE` ; la projection reconstruit ces faits avant les observations.
- **Fichiers créés/modifiés :** migration `20260906_0012`, modèle `core.roster_observations`, projection `python/metiquo/canonical/rosters.py`, exports canoniques et test PostgreSQL temporel dédié.
- **Migrations :** création d’une observation unique par game, équipe et rôle, liée au joueur vu, au raw, au snapshot et au run ; statut de continuité fermé et confiance bornée entre zéro et un.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cycle Alembic complet ; six tests PostgreSQL migrations/canonique sur PostgreSQL 18.
- **Résultat exact :** deux games à cinq joueurs par équipe produisent vingt observations idempotentes. Le top Blue différent dans la seconde game est enregistré comme `substitution_observed` avec une confiance `0.6500`, tandis que les joueurs inchangés restent confirmés à `1.0000`. `RosterProjectionService.as_of` ne lit que les observations strictement antérieures au cutoff, restitue le dernier joueur connu par rôle et n’écrit aucune projection future. Une projection au jour de la substitution conserve donc l’ancien top ; une projection ultérieure expose le nouveau et la baisse de confiance. Aucune annonce externe ou source non validée n’est consultée.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; une substitution inconnue reste une observation prudente plutôt qu’une certitude reconstruite rétrospectivement.
- **Commit/hash :** `f8280c7` (`feat(canonical): observe rosters as of games`).

## CNL-005 — Provenance et historique canonique

- **Statut :** `DONE`
- **Dépendances vérifiées :** les dimensions, games, séries et observations de roster `CNL-001` à `CNL-004` sont `DONE` et publient désormais leur histoire après chaque matérialisation.
- **Fichiers créés/modifiés :** migration `20260906_0013`, modèles `core.canonical_entity_revisions` et `core.canonical_entity_sources`, enregistreur `python/metiquo/canonical/history.py`, intégration aux quatre builders canoniques et test PostgreSQL de roundtrip/correction.
- **Migrations :** création d’une chaîne de révisions par type et UUID d’entité avec état JSONB, empreinte, version de transformation, `processed_at`, statut qualité, indicateur de correction, snapshot/run représentatifs et copie immuable de chaque ligne raw source. Deux triggers PostgreSQL interdisent UPDATE et DELETE sur les révisions comme sur leurs sources.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict sur le package canonique ; cycle Alembic complet ; sept tests PostgreSQL migrations/canonique sur PostgreSQL 18 ; vérification du diff.
- **Résultat exact :** tous les builders enregistrent un nouvel état uniquement lorsque le contenu canonique, la provenance ou la version de transformation change. Une game à deux lignes source produit une révision initiale avec ses deux preuves ; une reconstruction identique n’ajoute rien. Après correction d’une ligne raw en révision 2 sur un nouveau snapshot/run validé, la game obtient une révision 2 chaînée et `correction=true`. Le roundtrip retrouve le snapshot `validated` et le run `succeeded`; la première révision conserve `kills=10` et la seconde `kills=99` pour la même ligne raw, même si la vue raw courante a changé. Une tentative d’altération SQL échoue avec la protection append-only.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la copie de la preuve source est volontaire afin que l’historique ne dépende pas de la valeur mutable de `raw.canonical_rows`.
- **Commit/hash :** `a395a4c` (`feat(canonical): preserve entity revision history`).

## CNL-006 — Capability registry

- **Statut :** `DONE`
- **Dépendances vérifiées :** contrat de schéma évolutif `OE-013`, games `CNL-002` et séries `CNL-003` sont `DONE` ; le builder de games évalue automatiquement les snapshots courants après matérialisation.
- **Fichiers créés/modifiés :** migration `20260906_0014`, modèle `core.capability_evaluations`, service `python/metiquo/canonical/capabilities.py`, DTO et routes API mock/réelles, contrat OpenAPI/client TypeScript généré, matrice dans le dashboard Données, tests PostgreSQL/API/Playwright.
- **Migrations :** création d’évaluations append-only chaînées par snapshot, capacité et version de seuil, avec état, raisons, colonnes requises/observées, complétude, échantillon, détail des gates, empreinte et date. Un trigger PostgreSQL interdit UPDATE/DELETE.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict global ; OpenAPI export/check et génération client ; TypeScript strict ; ESLint ; 19 tests Python ciblés ; 4 tests Playwright ; parcours visuel via Navigateur sur le build de production.
- **Résultat exact :** le registre versionne cinq capacités initiales de label, features et marché. Labels/features sont dérivés des colonnes raw persistées et de la couverture des games utilisables ; les issues qualité ciblées ferment leur capacité. `market.match_winner` exige explicitement huit gates `label`, `data`, `rules`, `model`, `calibration`, `mapping`, `odds` et `sample`. Avec données suffisantes mais sans preuve modèle/odds, il reste `pending`; tous les gates vrais l’activent ; chaque gate externe faux le rend `disabled`, tout comme un label, une complétude ou un échantillon insuffisant. Une évaluation identique est idempotente et un changement de preuve crée une nouvelle révision. L’API `/api/v1/admin/capabilities` partage son DTO entre mock et réel et filtre par snapshot en réel. Le Navigateur a confirmé la matrice, les badges, les raisons, seuils et identifiants de snapshot dans l’UI.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la fermeture par défaut applique directement `SFG-MARKET-001` et aucun simple marché fournisseur ne peut activer une capacité.
- **Commit/hash :** `ed1f7b6` (`feat(canonical): gate capabilities by snapshot`).

## CNL-007 — Repository real canonique et APIs événements historiques

- **Statut :** `DONE`
- **Dépendances vérifiées :** l’historique canonique immuable `CNL-005` et les DTO/scénarios mock `MCK-002` sont `DONE` ; le mode réel réutilise strictement le contrat public `Event` existant.
- **Fichiers créés/modifiés :** repository PostgreSQL `python/metiquo/repositories/postgres_canonical.py`, routes réelles `python/metiquo/api/real_historical_routes.py`, branchement conditionnel dans la fabrique FastAPI, exports repository, test de contrat PostgreSQL mock/réel et test Playwright du composant Événements inchangé.
- **Migrations :** aucune ; l’adaptateur lit exclusivement les tables `core` et la santé du dernier snapshot validé.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; 27 tests Python de migrations, projections canoniques, capabilities, API mock/réelle et OpenAPI ; test Playwright ciblé ; build Next.js de production en mode réel ; parcours visuel via Navigateur de la liste et d’une fiche événement contre PostgreSQL réel.
- **Résultat exact :** les repositories réels exposent équipes, games et séries avec leurs identifiants, noms, qualité, dates et provenance de snapshot. Les séries résolues deviennent des événements historiques et les games ambiguës restent des événements unitaires, sans double comptage des games déjà liées. L’API `/api/v1/events` applique pagination et filtres compétition, équipe, statut et fenêtre temporelle ; le détail et les collections marchés/cotes conservent les mêmes DTO que le mock, avec des collections vides honnêtes tant que leurs domaines ne sont pas matérialisés. La fraîcheur du snapshot validé alimente `asOf` et `computedAt` reste monotone même si l’horloge applicative précède l’horodatage source. Le Navigateur a confirmé le badge `REAL`, 15 événements canoniques et une fiche historique complète sans modification des composants UI.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les games sans série ne sont exposées séparément que lorsque la reconstruction canonique les a laissées non liées, et aucune donnée marché n’est synthétisée.
- **Commit/hash :** `fa7f53c` (`feat(canonical): expose real historical events`).

## FEAT-001 — Registre des définitions de features

- **Statut :** `DONE`
- **Dépendances vérifiées :** l’historique canonique append-only `CNL-005` est `DONE` ; le registre reprend la même exigence d’identité, version et immutabilité pour toutes les futures colonnes de modèle.
- **Fichiers créés/modifiés :** migration `20260906_0015`, modèles `FeatureDefinition`, `FeatureSet` et `FeatureSetMember`, service `python/metiquo/features/registry.py`, exports features et tests PostgreSQL du registre.
- **Migrations :** création de `features.feature_definitions`, `features.feature_sets` et `features.feature_set_members` avec versions, domaine, paramètres JSON, politique de disponibilité, capacité éventuellement requise, version de code, empreintes SHA-256 et ordre des membres. Des triggers PostgreSQL interdisent UPDATE et DELETE sur les trois tables.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cycle Alembic upgrade/downgrade/upgrade ; quatre tests de migration et registre sur PostgreSQL réel ; vérification du diff.
- **Résultat exact :** une définition est identifiée par son nom normalisé et sa version, et son empreinte couvre domaine, paramètres, disponibilité, capacité et version de code. Un feature set versionné référence une liste ordonnée de définitions exactes et possède sa propre empreinte déterministe. Un second enregistrement identique est idempotent ; réutiliser la même version avec un contenu différent échoue. `FeatureRegistry.build_vector` exige un set enregistré, refuse toute colonne ad hoc, toute colonne omise et toute valeur requise absente, tout en conservant explicitement `None` pour les features optionnelles ou dépendantes d’une capacité. Le vecteur produit porte l’UUID et la version du set ainsi que la version de chaque définition.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le registre ne pré-enregistre pas de calcul encore inexistant, les tickets suivants ajouteront leurs définitions au set complet sans prétendre qu’elles sont déjà disponibles.
- **Commit/hash :** `0a5a5a9` (`feat(features): add immutable definition registry`).

## FEAT-002 — Primitives as-of et cutoff

- **Statut :** `DONE`
- **Dépendances vérifiées :** le registre fermé `FEAT-001` et les games historisées `CNL-002` sont `DONE` ; la lecture temporelle s’appuie sur les révisions immuables de `CNL-005` plutôt que sur le seul état courant des tables core.
- **Fichiers créés/modifiés :** primitives `python/metiquo/features/temporal.py`, exports features, dépendance Polars stable, verrou Python et tests PostgreSQL/Polars des cutoffs.
- **Migrations :** aucune ; `max_input_time` et `max_knowledge_time` sont transportés dans l’audit immuable du lot et seront enregistrés par les feature snapshots de `FEAT-011`.
- **Commandes/tests exécutés :** ajout et verrouillage de Polars `1.44.1` ; Ruff format/check ; mypy strict ciblé ; quatre tests de migration et temporalité sur PostgreSQL réel ; vérification du diff.
- **Résultat exact :** `FeatureCutoff` refuse tout datetime sans fuseau et normalise en UTC. Les helpers SQL et Polars exigent ce type et appliquent toujours `source_event_time < cutoff`. `AsOfGameRepository` relit, pour chaque game et statistique équipe, la dernière révision canonique connue au cutoff ; une correction traitée plus tard ne peut donc pas remplacer rétroactivement l’état historique. Le lot retourné calcule et conserve cutoff, maximum des instants métier, maximum des instants de connaissance, UUID de révisions et snapshots sources. Une game volontairement injectée exactement au cutoff est exclue ; une observation à la frontière ou une révision postérieure soumise directement à l’audit lève une erreur bloquante.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; Polars est introduit ici car la SFG l’impose pour les calculs de features et le même garde-fou temporel doit précéder les agrégats SQL comme les plans Polars.
- **Commit/hash :** `a1fee80` (`feat(features): enforce strict as-of cutoffs`).

## FEAT-003 — Rating temporel pré-game

- **Statut :** `DONE`
- **Dépendances vérifiées :** les lots as-of audités `FEAT-002` sont `DONE` et constituent l’unique entrée du calculateur ; toute observation à la frontière ou après le cutoff est donc bloquée avant le rejeu.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/rating.py`, exports features et tests unitaires de séquences Elo vérifiables à la main.
- **Migrations :** aucune ; les paramètres et cinq colonnes produites sont déclarables dans le registre versionné de `FEAT-001`.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; trois tests de rating déterministe et de fuite temporelle ; vérification du diff.
- **Résultat exact :** `EloParameters` versionne rating initial, facteur K, échelle et éventuels priors explicites par compétition. Le calculateur rejoue uniquement les games antérieures du lot, trace pour chacune ratings pré-game, probabilité attendue, résultat passé et delta, puis expose ratings des deux équipes, différence et tailles d’échantillon. Une victoire entre deux équipes à 1500 produit exactement 1516/1484 avec K=32. Deux games partageant le même timestamp sont toutes deux évaluées depuis l’état antérieur commun puis appliquées ensemble, de sorte qu’aucun résultat simultané ne fuit dans l’autre. L’ordre d’entrée ne change pas le résultat et une game cible placée au cutoff déclenche le blocage temporel.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; Elo est la baseline auditable exigée par la SFG, pas encore un modèle promu, et les priors de compétition restent absents tant qu’ils ne sont pas explicitement fournis.
- **Commit/hash :** `bb9c9fb` (`feat(features): add auditable pregame Elo`).

## FEAT-004 — Forme récente

- **Statut :** `DONE`
- **Dépendances vérifiées :** les cutoffs et lots historiques `FEAT-002` sont `DONE` ; le calculateur réutilise aussi les transitions pré-game de la baseline `FEAT-003` pour mesurer la force réellement connue des adversaires.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/form.py`, durcissement du filtre des games non utilisables dans le rating, exports features et tests unitaires de fenêtres/missingness.
- **Migrations :** aucune ; toutes les sorties et tous les paramètres sont exposés comme `FeatureDefinitionSpec` versionnées pour le registre de `FEAT-001`.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cinq tests cumulés rating/forme ; vérification du diff.
- **Résultat exact :** chaque équipe expose simultanément les 5/10/20 dernières games et les fenêtres 30/60/90 jours, avec taux de victoire et complétude propres à chaque fenêtre. Le calcul fournit aussi moyenne exponentiellement pondérée, tendance linéaire, volatilité, rating pré-game moyen des adversaires et nombre de games utilisables. Une fixture dont une des cinq observations récentes est incomplète conserve cinq observations mais seulement quatre résultats, soit une complétude de 0,8 ; le taux de victoire est calculé sur ces quatre résultats et l’absence n’est ni une défaite ni un zéro. Une équipe nouvelle retourne échantillon zéro et métriques `None` explicites, prêtes pour la régularisation de `FEAT-010`.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les petits échantillons ne sont pas encore ramenés vers un prior dans ce ticket, afin que `FEAT-010` applique une politique unique et versionnée au-dessus des statistiques brutes.
- **Commit/hash :** `f9cac23` (`feat(features): compute explicit recent form`).

## FEAT-005 — Features side

- **Statut :** `DONE`
- **Dépendances vérifiées :** les relectures historiques strictes `FEAT-002` sont `DONE` ; les statistiques early sont relues depuis les copies immuables des payloads raw liées aux révisions canoniques, sans rouvrir un fichier source.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/side.py`, enrichissement as-of prudent des statistiques source autorisées, exports features, tests unitaires Blue/Red et extension du test PostgreSQL temporel.
- **Migrations :** aucune ; les statistiques early restent dans la preuve source de `CNL-005` et ne sont exposées que lorsqu’une valeur réelle est présente.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; sept tests du domaine features ; quatre tests de migration/temporalité sur PostgreSQL réel ; vérification du diff.
- **Résultat exact :** chaque équipe possède des échantillons Blue et Red séparés avec games, victoires, taux ajusté par un prior explicite et versionné, moyenne early disponible et taille de cet échantillon. Le différentiel Blue/Red est exposé sans confondre les sides. La fixture produit 2 victoires en 3 games Blue, soit un taux ajusté 0,571429, et 0 en 2 Red, soit 0,333333 ; deux valeurs `gold_diff_at_15` donnent une moyenne 25 tandis que la side sans donnée reste `None`. Les définitions early sont marquées `capability_gated` par `feature.early_game`. Pour une side cible inconnue, les deux équipes restent `unknown` et les poids Blue/Red valent explicitement 0,5/0,5 ; aucune side n’est supposée. Une side connue devient au contraire un scénario one-hot déterministe.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le prior Blue/Red est une régularisation locale documentée exigée par le ticket, tandis que les priors hiérarchiques généraux restent réservés à `FEAT-010`.
- **Commit/hash :** `fdc65d2` (`feat(features): model explicit side uncertainty`).

## FEAT-006 — Économie, rythme et objectifs conditionnels

- **Statut :** `DONE`
- **Dépendances vérifiées :** les cutoffs `FEAT-002` et le capability registry `CNL-006` sont `DONE` ; les valeurs détaillées proviennent exclusivement des révisions canoniques et de leurs payloads source immuables.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/economy.py`, quatre définitions de capability supplémentaires dans le registre canonique, exports features et tests unitaires des groupes activés/désactivés.
- **Migrations :** aucune ; les évaluations des nouvelles capabilities utilisent la table append-only existante et les sorties sont déclarables dans le registre de features.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; neuf tests du domaine features ; six tests PostgreSQL de migrations, capabilities, temporalité et API réelle ; vérification du diff.
- **Résultat exact :** `feature.pace`, `feature.economy_timestamps`, `feature.objectives_total` et `feature.objectives_first` possèdent colonnes requises, seuils de complétude et taille minimale versionnés. Le calcul expose des indicateurs de disponibilité de groupe, kills/minute, durée, gold/XP/CS différentiels aux minutes 10/15/20/25 lorsqu’ils existent, tailles d’échantillon, conversion d’un avantage à 15 minutes, comeback historique, tours/dragons/barons par minute et taux de premiers objectifs. Deux games de 30 minutes donnent 0,3 kill/minute et 0,2 tour/minute pour la fixture ; un avantage gagné produit une conversion à 1 et un déficit perdu un comeback à 0. Avec les mêmes colonnes présentes mais les capabilities désactivées, toutes les métriques restent `None`, leurs comptes valent zéro et les quatre indicateurs sont faux.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les timestamps autres que 15 minutes restent optionnels avec compte nul, tandis que l’activation du groupe exige au minimum gold, XP et CS à 15 minutes comme preuve commune.
- **Commit/hash :** `7a7b3eb` (`feat(features): gate economy and objectives`).

## FEAT-007 — Roster et joueurs

- **Statut :** `DONE`
- **Dépendances vérifiées :** les lots historiques stricts `FEAT-002` et les observations de roster `CNL-004` sont `DONE` ; le calcul n'accepte que le lot canonique as-of et ne possède aucun adaptateur vers une source roster externe.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/roster.py`, enrichissement du repository temporel avec les révisions joueurs et roster, exports features, tests modèle et extensions des tests PostgreSQL roster/temporalité.
- **Migrations :** aucune ; les joueurs et observations sont relus depuis les révisions append-only `game_player_stat` et `roster_observation` déjà produites par l'historique canonique.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; onze tests modèle cumulés ; cinq tests PostgreSQL de migrations, roster et temporalité ; vérification du diff.
- **Résultat exact :** la projection choisit pour chaque rôle la dernière observation OE connue et strictement antérieure au cutoff. Elle expose couverture des cinq rôles, continuité du cinq sur les cinq dernières games complètes, nombre de games communes, joueurs ayant changé récemment de rôle, force individuelle ramenée vers un prior explicite, trois synergies de rôles avec leurs échantillons et une roster-confidence versionnée. La fixture de substitution conserve l'ancien top avant la game du changement et le nouveau top après, avec une confiance d'observation abaissée à 0,65. Une équipe sans observation garde roster vide, métriques de force et synergie à `None`, confiance zéro et indicateur `low_confidence=true`; aucune absence n'est transformée en joueur ou résultat fictif.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la « force individuelle » reste une statistique historique régularisée et auditable, non un rating externe de joueur, tandis que les pairs top/jungle, jungle/mid et bot/support couvrent les synergies de rôles stables sans inventer une composition future.
- **Commit/hash :** `e36cef7` (`feat(features): derive roster strength as of cutoff`).

## FEAT-008 — Champion pool et méta

- **Statut :** `DONE`
- **Dépendances vérifiées :** le repository strictement as-of `FEAT-002` fournit désormais les statistiques joueurs et champions historisées ; aucune donnée de draft n'est lue hors de ce lot antérieur.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/champions.py`, exports features, fixture modèle de fuite post-draft et extension du test PostgreSQL roster/joueurs.
- **Migrations :** aucune ; champion, rôle, résultat et patch sont relus depuis les révisions canoniques existantes.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; treize tests modèle cumulés ; trois tests PostgreSQL roster et temporalité ; vérification du diff.
- **Résultat exact :** pour chacun des cinq rôles et des deux équipes, le calcul expose nombre de picks historiques, diversité, profondeur effective entropique, part du champion principal, taux de victoire du rôle et moyenne des performances par champion. Il compte aussi les compositions complètes réellement observées et leur répétition. Si le patch cible est connu, ses games, champions, taux de victoire et delta d'adaptation par rapport à l'historique global sont calculés ; un patch inconnu produit `patch_known=false`, zéro échantillon et métriques patch `None`. L'API du calculateur ne reçoit aucun pick cible et rejette explicitement un lot contenant l'identifiant de la game cible, ce que couvre la fixture post-draft avec cinq champions futurs volontairement injectés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les champion pools sont résumés en colonnes fixes pré-draft plutôt qu'en catégories dynamiques dépendant du pick cible, afin de conserver un schéma reproductible et de rendre impossible la fuite du draft réel.
- **Commit/hash :** `8ad8aaa` (`feat(features): add pre-draft champion meta`).

## FEAT-009 — Contexte compétition et calendrier

- **Statut :** `DONE`
- **Dépendances vérifiées :** les lots as-of `FEAT-002` et le contexte canonique de séries `CNL-003` sont `DONE` ; les champs cibles n'acceptent que la provenance `canonical_oe` ou l'état `unknown`.
- **Fichiers créés/modifiés :** calculateur `python/metiquo/features/context.py`, exports features et tests modèle de provenance, calendrier et connaissance tardive.
- **Migrations :** aucune ; les valeurs cibles transportent l'UUID de leur révision canonique et leur instant de connaissance, tandis que le calendrier est dérivé des games déjà historisées.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; quinze tests modèle cumulés ; vérification du diff.
- **Résultat exact :** compétition, ligue, région, tournoi, stage, phase regular/playoffs/international, best-of et patch sont soit accompagnés d'une révision OE connue au cutoff, soit absents avec provenance `unknown` et indicateur de connaissance faux. Une provenance `external_news` est refusée et un champ OE appris après le cutoff déclenche le garde-fou temporel. Pour chaque équipe, le calcul expose jours de repos depuis la dernière game, densité des quatorze derniers jours et expérience du format best-of cible. La fixture internationale retrouve deux jours de repos, deux games récentes et une game antérieure dans le même BO pour l'équipe A ; une équipe sans historique conserve repos `None` sans imputation.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la phase n'est déduite que d'indicateurs OE explicites : international prend priorité, sinon playoffs vrai donne `playoffs`, playoffs faux donne `regular`, et toute autre combinaison reste inconnue.
- **Commit/hash :** `996c7c7` (`feat(features): add proven competition context`).

## FEAT-010 — Priors, missingness et cold start

- **Statut :** `DONE`
- **Dépendances vérifiées :** les domaines rating, forme, side, économie, roster, champion et contexte de `FEAT-003` à `FEAT-009` produisent tous valeurs et échantillons explicites ; le nouveau service peut donc régulariser ces métriques sans relire une source ni confondre absence et zéro.
- **Fichiers créés/modifiés :** estimateur et préprocesseur `python/metiquo/features/priors.py`, exports features et tests modèle de shrinkage, ancienneté, cold start, OOD et fit train-only.
- **Migrations :** aucune ; les artefacts immuables portent versions, cutoff, UUID des observations/lignes utilisées et empreinte déterministe avant leur persistance par les tickets suivants.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; dix-sept tests modèle cumulés ; vérification du diff.
- **Résultat exact :** l'estimateur ajuste d'abord un prior global, puis des priors de ligue ramenés vers le global et des priors de patch ramenés vers leur ligue. Les observations anciennes sont décotées selon une demi-vie versionnée ; dix games vieilles de 90 jours donnent ainsi un échantillon effectif de cinq. Une petite observation est régularisée vers son prior patch, avec taille effective et confiance explicites. Un groupe inconnu retombe sur le niveau global avec `ood=true` et confiance réduite. Un cold start conserve `raw_value=None`, `available=false`, `cold_start=true` et confiance zéro ; s'il n'existe aucun prior ajusté, la valeur finale reste elle aussi `None`. Le scaler ignore les valeurs absentes, l'encodeur réserve des codes uniquement aux catégories vues avant le cutoff, une catégorie future ou OOD garde code `None`, et l'ajout d'une ligne post-cutoff ne change ni paramètres ni empreinte du préprocesseur.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les priors peuvent fournir une valeur de repli mais jamais une confiance factice, et l'indicateur de disponibilité brute reste indépendant de la valeur régularisée.
- **Commit/hash :** `5902f4f` (`feat(features): add hierarchical priors and missingness`).

## FEAT-011 — Feature snapshots immuables

- **Statut :** `DONE`
- **Dépendances vérifiées :** le registre fermé `FEAT-001`, les lots et audits temporels `FEAT-002`, les politiques de missingness `FEAT-010` et les snapshots OE immuables `OE-011` sont `DONE`.
- **Fichiers créés/modifiés :** migration `20260906_0016`, modèle `FeatureSnapshot`, store `python/metiquo/features/snapshots.py`, exports features et tests PostgreSQL de hash, roundtrip, idempotence et immutabilité.
- **Migrations :** création de `features.feature_snapshots` avec event, équipes, feature set, cutoff, maxima métier/connaissance, versions, valeurs, missingness, listes de games/révisions/snapshots OE, empreintes games/vecteur/snapshot, commit de code, contrôles de leakage, chaînage de rebuild et génération. Les contraintes temporelles sont aussi imposées en base et un trigger interdit UPDATE/DELETE.
- **Commandes/tests exécutés :** Ruff format/check ; mypy strict ciblé ; cycle Alembic upgrade/downgrade/upgrade ; cinq tests PostgreSQL de migrations, registre et snapshots ; vérification du diff.
- **Résultat exact :** le store n'accepte qu'un `RegisteredFeatureVector`, un lot dont le cutoff correspond exactement, un snapshot OE cible validé, au moins une game cible déclarée comme exclue, un commit Git hexadécimal et tous les contrôles de fuite au vert. Les `Decimal` sont sérialisés sans perte, les `None` produisent une carte de missingness distincte, et l'empreinte du vecteur couvre set, versions, valeurs et absences. L'empreinte du snapshot ajoute candidate, audit temporel, lignage OE, fingerprint ordonné des games, commit et contrôles. Deux créations identiques retournent le même UUID et le même enregistrement ; une tentative d'UPDATE échoue avec la protection append-only. La prédiction future peut donc référencer un UUID qui restitue exactement le vecteur et toutes ses preuves.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; `target_oe_snapshot_id` assure une référence relationnelle au snapshot de la candidate, tandis que la liste JSON des snapshots historiques conserve honnêtement les cas où la fenêtre de features traverse plusieurs snapshots source.
- **Commit/hash :** `ab7d86b` (`feat(features): persist immutable feature snapshots`).

## FEAT-012 — Rebuild ciblé après invalidation

- **Statut :** `DONE`
- **Dépendances vérifiées :** les invalidations rétroactives `OE-018`, les snapshots append-only `FEAT-011` et le pipeline complet `FEAT-014` sont `DONE` ; le planificateur ne travaille que sur le feature set et le dataset explicitement demandés.
- **Fichiers créés/modifiés :** planificateur `python/metiquo/features/rebuild.py`, enrichissement du modèle, de la migration `20260906_0016` et du store de snapshots, intégration dans `python/metiquo/features/dataset.py`, exports features et tests PostgreSQL de reconstruction ciblée.
- **Migrations :** ajout des identifiants de games cibles et des invalidations déjà consommées aux snapshots ; les remplacements restent de nouvelles lignes liées par `supersedes_snapshot_id` avec une génération strictement croissante.
- **Commandes/tests exécutés :** Ruff et mypy strict ; test anti-fuite ; gate complet avec PostgreSQL réel ; cycle d'intégration explicite.
- **Résultat exact :** le plan retient la dernière génération de chaque snapshot dont le cutoff rencontre `affected_from`, limite les candidats au provider, dataset et feature set demandés, puis transmet au recalcul l'ensemble exact des invalidations non consommées. Une invalidation datée du `2026-08-10` laisse intact le snapshot du `2026-08-05`, crée une génération 2 pour celui du `2026-08-10` et conserve la génération 1 consultable sans mutation. Le passage suivant ne produit aucun remplacement, car l'identifiant d'invalidation est déjà enregistré. Le gate global retourne 270 tests Python, 16 tests UI et 4 tests web réussis ; les 34 tests PostgreSQL passent aussi séparément.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; conserver toutes les générations et leurs causes applique directement l'exigence de reproductibilité, sans réécriture destructive.
- **Commit/hash :** `ec20989` (`feat(features): rebuild invalidated snapshots append-only`) et `ff6b136` (`feat(features): build reproducible feature datasets`).

## FEAT-013 — Tests anti-leakage

- **Statut :** `DONE`
- **Dépendances vérifiées :** les primitives temporelles `FEAT-002`, les calculateurs historiques et les transformations train-only `FEAT-010` sont `DONE` ; le gate appelle désormais ces preuves avant la suite générale.
- **Fichiers créés/modifiés :** suite `tests/leakage/test_anti_leakage_guards.py`, cible `test-leakage` et dépendance explicite du gate `check` dans le `Makefile`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** `make test-leakage`, puis `make check` avec PostgreSQL réel.
- **Résultat exact :** une propriété parcourt les décalages de zéro à une microseconde ou davantage et vérifie que toute observation à la frontière ou après le cutoff est rejetée. Une seconde preuve injecte à la fois une game future et une révision apprise tardivement, et confirme que l'échec survient avant tout agrégat. Le sous-gate exécute neuf tests couvrant aussi rating, champion pré-draft, priors et préprocesseurs train-only ; les neuf passent et conditionnent dorénavant le gate global.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le test dédié rend une régression temporelle bloquante en CI au lieu de dépendre seulement de tests fonctionnels dispersés.
- **Commit/hash :** `b87998a` (`test(features): block temporal leakage in CI`).

## FEAT-014 — Pipeline reproductible complet et rapport de couverture

- **Statut :** `DONE`
- **Dépendances vérifiées :** le registre `FEAT-001`, tous les calculateurs `FEAT-003` à `FEAT-010`, les snapshots `FEAT-011`, le rebuild `FEAT-012` et le gate anti-leakage `FEAT-013` sont `DONE`.
- **Fichiers créés/modifiés :** orchestrateur `python/metiquo/features/dataset.py`, commande `oe features-rebuild`, cible `make features-rebuild`, exports, tests de CLI/Make et gate PostgreSQL `tests/integration/test_feature_dataset.py` ; isolation de la base d'intégration et restriction des candidates au provider/dataset configuré.
- **Migrations :** aucune nouvelle migration au-delà du snapshot enrichi de `FEAT-011`/`FEAT-012`.
- **Commandes/tests exécutés :** formatters, ESLint, Ruff, cspell, TypeScript strict, mypy strict sur 192 fichiers, neuf tests anti-fuite, 20 tests composants, 270 tests Python avec PostgreSQL réel, contrôle OpenAPI/client et 34 tests d'intégration PostgreSQL séparés.
- **Résultat exact :** la commande construit le feature set fermé `lol.match_winner.pregame@p3-reproducible-v1`, énumère seulement les games du provider/dataset dont le snapshot est validé et le contexte canonique connu au cutoff, puis calcule rating, forme, side, économie capability-gated, roster, champion pool, contexte et priors depuis l'histoire strictement antérieure. Sur la fixture, elle produit deux snapshots avec couverture 1, cutoffs du `2026-08-05` au `2026-08-10`, empreintes et lignage complets ; la game cible est absente des sources. Un second passage conserve exactement les mêmes UUID et missingness. Une invalidation ne reconstruit ensuite que la candidate affectée et le passage suivant redevient idempotent. Le rapport JSON expose couverture, créations, rebuilds, plage de cutoff, missingness, UUID et exemple traçable.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le pipeline reste limité à l'historique canonique déjà persisté et n'effectue ni téléchargement ad hoc ni enrichissement externe.
- **Commit/hash :** `ff6b136` (`feat(features): build reproducible feature datasets`) et `da8456d` (`fix(features): isolate rebuild inputs and integration state`).

## ML-001 — Dataset d'entraînement versionné

- **Statut :** `DONE`
- **Dépendances vérifiées :** le gate reproductible `FEAT-014`, les labels canoniques historisés `CNL-005` et les snapshots OE validés `OE-011` sont `DONE` ; le builder consomme uniquement le feature set enregistré et les tables canoniques issues du provider/dataset demandés.
- **Fichiers créés/modifiés :** migration `20260906_0017`, modèles `TrainingDataset` et `TrainingDatasetExample`, builder `python/metiquo/models/datasets.py`, exports ML et test PostgreSQL de reproductibilité/provenance.
- **Migrations :** création de `ml.datasets` et `ml.dataset_examples`. Le manifeste porte marché, provider/dataset, version de dataset, feature set/version/hash, définition du label, filtre qualité, période, plage de cutoffs, compétitions, snapshots OE, exclusions, compteurs, empreinte des exemples, hash global et commit de code. Chaque exemple référence sa game, son feature snapshot, ses équipes, son cutoff, son label booléen, la révision canonique `game_team_stat` source et son snapshot OE. Deux triggers interdisent UPDATE et DELETE sur les deux tables.
- **Commandes/tests exécutés :** formatters, ESLint, Ruff, cspell, TypeScript strict, mypy strict sur 197 fichiers, neuf tests anti-leakage, 20 tests composants, 271 tests Python avec PostgreSQL réel, contrôle OpenAPI/client et 35 tests d'intégration PostgreSQL séparés.
- **Résultat exact :** la fixture produit deux exemples `game_winner` ordonnés avec les mêmes UUID et le même hash de dataset lorsque la requête, les données, le feature set et le commit sont identiques, même si l'horloge de création change. Le hash couvre les documents d'exemples, leurs hashes de vecteur/snapshot, la sélection de compétitions, tous les snapshots OE, les filtres et les exclusions identifiées par game. Chaque label est relu depuis la statistique de l'équipe A, exige une paire binaire cohérente, puis conserve l'UUID de la révision `game_team_stat` et d'un snapshot `validated` du provider/dataset exact. Une corruption simulée vers un snapshot en quarantaine exclut cette seule game avec la raison `label_snapshot_not_validated`, crée un nouveau dataset à un exemple et laisse le premier entièrement consultable. Les feature sets contenant une colonne de cote/bookmaker sont refusés avant construction.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; `game_winner` est volontairement le seul marché admis dans ce premier schéma et les cotes restent hors du dataset du modèle indépendant.
- **Commit/hash :** `f548ade` (`feat(ml): version reproducible training datasets`).

## ML-002 — Validation walk-forward

- **Statut :** `DONE`
- **Dépendances vérifiées :** les datasets et labels immuables `ML-001`, les cutoffs stricts `FEAT-002` et les transformations train-only `FEAT-010` sont `DONE`.
- **Fichiers créés/modifiés :** moteur `python/metiquo/models/validation.py`, exports ML, extension du test d'intégration du dataset et tests modèle des splits, transformations et prédictions hors échantillon.
- **Migrations :** aucune ; le plan et son empreinte sont déterministes à partir du dataset versionné, tandis que les futurs runs enregistreront cette preuve.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests ciblés modèle/PostgreSQL, puis gate global avec anti-leakage, composants et PostgreSQL réel.
- **Résultat exact :** `WalkForwardSplitter` refuse tout split principal autre que `walk_forward`, groupe les exemples partageant exactement le même cutoff, utilise un train expansif et ne valide que sur des périodes strictement futures. La dernière fenêtre est exclue de tous les folds et son UUID est rendu explicitement comme test final intact. Deux folds synthétiques couvrent quatre prédictions OOF sans doublon ; toute couverture incomplète, tout UUID extérieur à la validation du fold ou toute probabilité hors de `[0,1]` est refusé. `prepare_walk_forward` ajuste scaler et catégories sur le train exact de chaque fold : les valeurs extrêmes et la catégorie présentes seulement dans le test final n'entrent dans aucun artefact. Le tuning n'accepte que les UUID OOF et rejette le test final. Le rapport ventile initial train, validation OOF et test final par patch et statut international, et l'empreinte du plan reste stable quel que soit l'ordre d'entrée. Le gate retourne 273 tests Python et 20 tests composants réussis ; format, lint, types et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la validation principale aléatoire et l'emploi du test final pour choisir des seuils sont explicitement impossibles.
- **Commit/hash :** `32a740f` (`feat(ml): enforce walk-forward validation`).

## ML-003 — Baselines prior et forme naïve

- **Statut :** `DONE`
- **Dépendances vérifiées :** le plan walk-forward et ses prédictions OOF exactes de `ML-002` sont `DONE` ; les deux baselines utilisent les mêmes folds chronologiques et n'accèdent jamais à la fenêtre de test finale.
- **Fichiers créés/modifiés :** migration `20260906_0018`, modèles `BaselineRun` et `BaselinePrediction`, évaluateur et registre `python/metiquo/models/baselines.py`, exports ML, tests numériques et test PostgreSQL de roundtrip/immutabilité.
- **Migrations :** création de `ml.baseline_runs` et `ml.baseline_predictions`. Chaque run référence le dataset versionné, le marché, la baseline et sa version, le fingerprint walk-forward, le split `oof_validation`, les paramètres, le rapport de métriques, le commit de code et les empreintes des prédictions et du run. Chaque probabilité OOF conserve exemple, fold, cutoff, label et position. Des contraintes ferment les types de baseline et le split, et des triggers interdisent UPDATE/DELETE sur les évaluations publiées.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests ciblés modèle/PostgreSQL, cycle Alembic upgrade/downgrade/upgrade, puis gate global avec PostgreSQL réel.
- **Résultat exact :** le prior de compétition est réajusté sur le train exact de chaque fold avec lissage bêta `0,5/0,5` et repli sur le prior global train-only pour une compétition absente. La forme naïve combine `form.team_a.ewm_win_rate` et le complément de `form.team_b.ewm_win_rate`, utilise la composante disponible si une seule existe et retombe sur le prior du fold si les deux manquent. Sur la preuve manuelle, les probabilités OOF du prior sont `0,5 / 0,5 / 0,625 / 0,25` et celles de la forme `0,7 / 0,5 / 0,9 / 0,8`. Le rapport commun calcule log loss, Brier, reliability bins et ECE ; un exemple `0,8/0,2` correctement prédit donne `0,223144`, `0,040000` et `0,200000`. Les comparaisons refusent datasets, plans, exemples ou baselines dupliqués. Les probabilités sont normalisées à la précision persistée avant métriques et hash ; tout contenu incohérent est bloqué avant insertion. Le gate retourne 276 tests Python et 20 tests composants réussis, dont 36 tests d'intégration PostgreSQL.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la forme est volontairement naïve et sans apprentissage, tandis que les données manquantes héritent d'un prior explicitement appris sur le passé du fold plutôt que d'une imputation silencieuse. Les cotes bookmaker restent totalement absentes.
- **Commit/hash :** `ea1c013` (`feat(ml): record comparable baseline runs`).

## ML-004 — Baseline rating game winner

- **Statut :** `DONE`
- **Dépendances vérifiées :** le rating pré-game déterministe `FEAT-003`, les folds temporels et le périmètre OOF `ML-002`, ainsi que le contrat de runs comparables `ML-003` sont `DONE`.
- **Fichiers créés/modifiés :** migration `20260906_0019`, modèle `RatingArtifact`, entraîneur et store `python/metiquo/models/rating.py`, extension des runs comparables, exports ML, propriétés numériques et roundtrip PostgreSQL.
- **Migrations :** création de `ml.rating_artifacts` avec dataset, marché, version, fingerprint walk-forward, feature rating exacte, grille, échelle choisie, métrique/scope de sélection, métriques de chaque candidate, commit et empreinte. `ml.baseline_runs` accepte désormais `rating` et référence facultativement l'artefact ; le repository exige l'artefact uniquement pour cette baseline et vérifie qu'il appartient au même dataset, au même plan et au fingerprint déclaré. L'artefact est append-only. Le downgrade retire les seuls runs rating introduits avant de restaurer la contrainte ML-003, ce qui permet un cycle réel même après publication d'un run.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests modèle et PostgreSQL ciblés, cycle Alembic avec données rating publiées, puis gate global avec PostgreSQL réel.
- **Résultat exact :** `rating.difference` est transformé par la probabilité Elo `1 / (1 + 10^(-diff/scale))`, saturée proprement aux extrêmes, quantifiée et refusée si l'écart ou l'échelle ne sont pas finis. Les tests couvrent des écarts de `-1 000 000` à `+1 000 000`, la monotonie, la symétrie et les bornes `[0,1]`. Les échelles `200/300/400/600/800` sont évaluées sur les mêmes prédictions OOF ; le meilleur log loss est choisi avec départage par la plus petite échelle, et chaque métrique candidate est conservée. Le test final n'est ni prédit ni consulté : remplacer ses ratings par des extrêmes laisse artefact, fingerprint et run strictement identiques. Le résultat est reproductible, le run rating rejoint les deux baselines précédentes sur le même périmètre, et les features absentes sont refusées sans imputation. Le gate retourne 278 tests Python, 20 tests composants et mypy strict sur 206 fichiers ; les contrats et migrations sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; seule l'échelle de conversion est réglée à ce stade, sur validation OOF exclusivement. Le test final reste réservé à l'évaluation finale et aucune cote bookmaker n'entre dans la probabilité.
- **Commit/hash :** `327003f` (`feat(ml): version pregame rating baseline`).

## ML-005 — Benchmark gradient boosting

- **Statut :** `DONE`
- **Dépendances vérifiées :** les folds walk-forward et transformations train-only `ML-002`, les runs de prior/forme `ML-003` et la baseline rating versionnée `ML-004` sont `DONE` ; les trois baselines partagent exactement dataset, fingerprint temporel et exemples OOF.
- **Fichiers créés/modifiés :** dépendance CPU de la bibliothèque Python verrouillée, moteur et repository `python/metiquo/models/benchmark.py`, migration `20260906_0020`, modèles ORM, exports ML, tests déterministes et extension du roundtrip PostgreSQL append-only.
- **Migrations :** création de `ml.tabular_benchmark_runs` et `ml.tabular_benchmark_predictions`. Le run conserve feature spec fermé, seed, paramètres, métriques globales/par fold, décision de sélection, trois UUID de baseline, gains du gate de promotion, fingerprints et commit. Chaque candidat conserve toutes ses probabilités OOF avec fold, cutoff, label et position ; les deux tables interdisent UPDATE/DELETE.
- **Commandes/tests exécutés :** Ruff, mypy strict sur 209 fichiers, smoke déterministe, roundtrip PostgreSQL et cycle Alembic ciblés, puis gate global complet.
- **Résultat exact :** `GradientBoostingClassifier` et `HistGradientBoostingClassifier` sont entraînés en CPU avec le même seed, les mêmes features et les mêmes transformations ajustées uniquement sur le train de chaque fold. Le test final n'est jamais converti en ligne d'entraînement ni lu pour la sélection : remplacer son signal par une valeur extrême laisse le run strictement identique. Le choix est lexicographique sur log loss, ECE, pire log loss de fold puis nom stable ; les paramètres et toutes les probabilités sont conservées. Un modèle complexe n'est promouvable que si ses gains de log loss, calibration et robustesse temporelle sont strictement positifs face au prior, à la forme récente et au rating. Le smoke de non-régression prouve aussi le refus des champs de cote/bookmaker et le maintien d'une décision non promouvable quand un gate échoue. Le gate retourne 280 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, types et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les deux boosters de la bibliothèque Python constituent les candidats tabulaires CPU prévus par la SFG. Cette étape ne promeut aucun modèle par préférence et réserve toujours le test final.
- **Commit/hash :** `69d40e8` (`feat(ml): benchmark tabular candidates`).

## ML-006 — Ensemble candidat

- **Statut :** `DONE`
- **Dépendances vérifiées :** la baseline rating `ML-004` et le benchmark tabulaire `ML-005` sont `DONE` ; l'évaluateur exige leurs mêmes dataset, fingerprint walk-forward, trois runs de baseline et exemples OOF ordonnés.
- **Fichiers créés/modifiés :** moteur et repository `python/metiquo/models/ensemble.py`, migration `20260906_0021`, modèles ORM, exports ML, test de comparaison et extension du roundtrip PostgreSQL.
- **Migrations :** création de `ml.ensemble_candidate_runs` et `ml.ensemble_candidate_predictions`. Le run référence le benchmark, le rating et les trois baselines, conserve la grille intérieure de poids, toutes les évaluations, le poids choisi, la décision structurée, métriques, pire fold, fingerprints et commit. La probabilité OOF sélectionnée conserve exemple, fold, cutoff, label et position ; les deux tables sont append-only.
- **Commandes/tests exécutés :** Ruff, mypy strict sur 212 fichiers, tests modèle/PostgreSQL ciblés, migrations aller-retour, puis gate global complet.
- **Résultat exact :** chaque poids rating strictement compris entre zéro et un est évalué contre le complément tabulaire sur les seules probabilités OOF déjà publiées. Le poids est choisi de façon déterministe par log loss, ECE, pire log loss de fold puis poids. L'activation exige que le tabulaire source soit lui-même promouvable et que le mélange améliore strictement log loss, calibration et robustesse temporelle face au prior, à la forme récente, au rating et au candidat tabulaire. Sinon, le run reste valide mais `enabled=false` avec une raison par référence non battue ; la fixture prouve cette désactivation sûre. Le test final n'entre dans aucune recherche de poids. Le repository reconstruit intégralement la décision depuis les sources persistées avant insertion. Le gate retourne 282 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, types et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'ensemble est volontairement un candidat désactivable, pas une étape obligatoire du modèle final.
- **Commit/hash :** `dcf495a` (`feat(ml): gate rating tabular ensemble`).

## ML-007 — Calibration hors échantillon

- **Statut :** `DONE`
- **Dépendances vérifiées :** rating `ML-004`, tabulaire `ML-005` et décision d'ensemble `ML-006` sont `DONE` ; la source devient l'ensemble uniquement s'il est activé, sinon le tabulaire sélectionné reste la source explicite.
- **Fichiers créés/modifiés :** moteur et repository `python/metiquo/models/calibration.py`, migration `20260906_0022`, modèles ORM, exports ML, tests de fuite temporelle et de dérive par segment.
- **Migrations :** création de `ml.calibrator_artifacts` et `ml.calibrator_oos_predictions`. L'artefact séparé référence sa source, conserve méthode, paramètres de déploiement, configuration de recherche, évaluations candidates, reliability/ECE/Brier/log loss, pente/intercept, rapports par segment, fingerprints et commit. Chaque probabilité de preuve garde exemple, fold de calibration, cutoff, label et position ; les tables sont append-only.
- **Commandes/tests exécutés :** Ruff, mypy strict sur 215 fichiers, tests calibration/migrations ciblés, puis gate global complet.
- **Résultat exact :** Platt et isotonic sont ajustés sur le passé des prédictions OOF puis évalués sur des blocs OOF futurs strictement distincts. Les vingt probabilités de preuve de la fixture proviennent de quatre validations situées après dix périodes initiales de fit ; le test final reste absent et sa modification ne change ni méthode, ni paramètres, ni empreinte. La méthode est choisie par log loss, ECE, Brier puis nom stable. L'artefact de déploiement est ensuite ajusté sur toutes les OOF disponibles et expose une application bornée. La pente et l'intercept de calibration sont calculés sur les seules prédictions de preuve. Les rapports patch et compétition portent toujours leur effectif, signalent les petits échantillons et détectent une fixture volontairement inversée comme dérive matérielle. Le gate retourne 284 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, types et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la calibration est volontairement un artefact distinct du modèle et sa preuve réutilise un second découpage temporel, jamais le test final.
- **Commit/hash :** `e6edef6` (`feat(ml): calibrate temporal OOS predictions`).

## ML-008 — Incertitude calibrée et détection hors domaine

- **Statut :** `DONE`
- **Dépendances vérifiées :** la calibration temporelle `ML-007` est `DONE` ; l'estimateur consomme son artefact séparé et uniquement ses prédictions de preuve hors échantillon.
- **Fichiers créés/modifiés :** moteur `python/metiquo/models/uncertainty.py`, exports ML et tests de propriétés numériques, de couverture incomplète et de distance hors domaine.
- **Migrations :** aucune ; l'artefact d'incertitude est adressé par une empreinte déterministe et sera rattaché au registre de modèles par `ML-010`.
- **Commandes/tests exécutés :** Ruff, mypy strict sur 217 fichiers, tests modèle ciblés, puis gate global complet.
- **Résultat exact :** deux variantes conformes sont comparées sur les seules preuves calibrées : rayon absolu global et rayon maximal des folds temporels. La sélection exige la couverture empirique cible puis minimise la largeur, avec départage stable. Chaque estimation garantit `p_low <= p50 <= p_high` et reste dans `[0,1]`. Une couverture de données insuffisante ou une distance hors domaine élargit l'intervalle, abaisse la confiance et ajoute une raison structurée ; au seuil d'abstention, l'intervalle devient `[0,1]` et la confiance zéro. Le gate retourne 286 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, types et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'incertitude reste un artefact distinct, sans nouvel entraînement ni consultation du test final, et les décisions de faible confiance demeurent explicables par des codes stables.
- **Commit/hash :** `163e3d0` (`feat(ml): estimate calibrated uncertainty`).

## ML-009 — Rapport d’évaluation et segments

- **Statut :** `DONE`
- **Dépendances vérifiées :** calibration hors échantillon `ML-007` et incertitude conforme `ML-008` sont `DONE` ; le rapport accepte exclusivement les prédictions de preuve calibrées appartenant à la validation OOF du plan et rejette le test final.
- **Fichiers créés/modifiés :** moteur `python/metiquo/models/evaluation.py`, chemin dédié aux probabilités historiques déjà calibrées dans l'artefact d'incertitude, exports ML et tests numériques/segments.
- **Migrations :** aucune ; le rapport et son identifiant sont dérivés d'une empreinte déterministe que `ML-010` pourra enregistrer avec la version modèle.
- **Commandes/tests exécutés :** Ruff, tests modèle et mypy ciblés, puis gate global complet avec PostgreSQL réel.
- **Résultat exact :** le rapport calcule log loss, Brier, ROC-AUC secondaire, ECE, pente/intercept de calibration, sharpness par largeur moyenne, couverture d'intervalle hors abstention et taux d'abstention. Chaque bloc conserve ses effectifs positifs, négatifs, évalués et abstentions. Les segments ligue, patch, stage et format sont toujours présents ; les buckets de probabilité marché et la robustesse outsider ne sont créés que pour des cotes observées explicitement fournies. Chaque segment porte son effectif, un drapeau de faible échantillon et des raisons de dérive sur log loss, calibration, couverture ou abstention. La politique de promotion exige une métrique probabiliste primaire et rejette donc accuracy ou AUC seules. La preuve numérique retrouve `0,223144` de log loss, `0,040000` de Brier, `1,000000` d'AUC, `0,200000` d'ECE, `0,400000` de largeur et une couverture parfaite. Le gate retourne 288 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 219 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les cotes restent un contexte facultatif observé pour l'analyse par segment et ne deviennent jamais une feature du modèle indépendant.
- **Commit/hash :** `35ef0b8` (`feat(ml): report segmented model evaluation`).

## ML-010 — Model registry et artefacts

- **Statut :** `DONE`
- **Dépendances vérifiées :** le rapport segmenté `ML-009` et l'ObjectStore immuable `OE-002` sont `DONE` ; l'enregistrement vérifie aussi les références du dataset, du calibrateur et de l'incertitude avant toute publication.
- **Fichiers créés/modifiés :** migration `20260907_0023`, modèle ORM `ModelVersion`, registre et adaptateur ObjectStore `python/metiquo/models/registry.py`, exports ML, tests de checksum et test PostgreSQL complet.
- **Migrations :** création de `ml.model_versions` avec jeu, marché, segment, algorithme, paramètres, version de features, dataset/hash/cutoffs, rapport/fingerprint, calibrateur, incertitude, clé/hash/taille/format de l'artefact, commit, statut, auteur, dates et motifs. Une contrainte unique partielle interdit deux champions pour le même jeu/marché/segment. Les métadonnées et suppressions sont protégées par trigger ; seuls les quatre champs de transition de statut sont réservés au workflow audité `ML-011`.
- **Commandes/tests exécutés :** tests checksum et registre ciblés, cycle Alembic, tests d'attentes du head mis à jour, puis gate global complet avec PostgreSQL réel.
- **Résultat exact :** les statuts `candidate`, `champion`, `retired` et `blocked` sont fermés par contrainte. Le registre dérive version de features, hash et cutoffs depuis le dataset réellement persisté, exige le calibrateur du même dataset, puis adresse le binaire par SHA-256 dans l'ObjectStore avec manifeste. Un second enregistrement identique réutilise le même objet et la même version. Chaque chargement relit le contenu, recalcule checksum et taille, et refuse une corruption physique. La preuve PostgreSQL enregistre un candidat, charge exactement ses octets, crée un champion, refuse un second champion concurrent, puis bloque modification de l'algorithme et suppression. Le gate retourne 290 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 223 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le binaire reste hors PostgreSQL mais sa référence et son empreinte sont indissociables de la version enregistrée.
- **Commit/hash :** `3f01839` (`feat(ml): register verifiable model artifacts`).

## ML-011 — Champion/challenger et rollback

- **Statut :** `DONE`
- **Dépendances vérifiées :** le registre et l'unicité du champion `ML-010` sont `DONE` ; les transitions réutilisent les champs de statut réservés sans modifier les métadonnées immuables de la version.
- **Fichiers créés/modifiés :** migration `20260907_0024`, modèles ORM d'événements et prédictions shadow, service `python/metiquo/models/lifecycle.py`, exports ML et scénario PostgreSQL de promotion/remplacement/rollback.
- **Migrations :** création de `ml.model_status_events` et `ml.shadow_predictions`, toutes deux append-only. Chaque transition conserve version, ancien/nouveau statut, version liée, action, acteur, motif, preuve, instant et fingerprint. Chaque prédiction shadow conserve challenger, champion servi à cet instant, événement, cutoff, instant, probabilité/intervalle et fingerprint de contexte. Les clés étrangères et contraintes probabilistes rendent les versions historiques indissociables de la preuve.
- **Commandes/tests exécutés :** Ruff, mypy strict, scénario lifecycle PostgreSQL et cycle Alembic ciblés, puis gate global complet.
- **Résultat exact :** une promotion exige une référence d'approbation manuelle, un rapport exact, des gains positifs face aux trois baselines prior/forme/rating et au moins deux métriques dont une probabiliste primaire. Le service verrouille le scope, retire l'ancien champion puis promeut le candidat dans une seule transaction. Le shadow d'un challenger est enregistré sans effet sur le modèle servi ; après promotion puis rollback, il référence encore exactement le challenger et le champion d'origine. Le rollback retire le champion courant et réactive immédiatement la version retirée, avec deux événements consignés. Un candidat peut aussi être bloqué avec motif. Une preuve fondée seulement sur accuracy et ROC-AUC est refusée et les événements ne peuvent être modifiés. Le gate retourne 291 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 226 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les promotions restent exclusivement explicites, manuelles, multi-métriques et réversibles, sans modifier les prédictions historiques.
- **Commit/hash :** `ed3ce5c` (`feat(ml): audit champion lifecycle and rollback`).

## ML-012 — MarketPlugin GAME_WINNER

- **Statut :** `DONE`
- **Dépendances vérifiées :** le lifecycle champion/challenger `ML-011` et le registre de capacités `CNL-006` sont `DONE` ; le gate joint désormais les preuves de données au champion effectivement servi.
- **Fichiers créés/modifiés :** contrat et implémentation `python/metiquo/markets/game_winner.py`, exports du package marchés et suite `tests/markets/test_game_winner_plugin.py`.
- **Migrations :** aucune ; le plugin consomme les états de capacité, versions de modèles, calibrateur et artefacts d'incertitude déjà historisés.
- **Commandes/tests exécutés :** Ruff, mypy strict ciblé, tests du plugin, puis gate global complet avec PostgreSQL réel.
- **Résultat exact :** le protocole expose capacités requises, labels, features, entraînement, prédiction, pricing et settlement. L'implémentation fixe le label binaire et le sous-ensemble de features tabulaires, délègue l'entraînement au benchmark walk-forward et refuse un backend absent. Son gate reste fermé lorsqu'une capacité est absente, pending ou disabled, lorsque les états proviennent de snapshots différents, sans champion actif du scope `lol/game_winner`, ou tant que l'artefact modèle n'a pas été vérifié. La prédiction exige en plus les UUID et empreintes exactes du calibrateur et de l'incertitude enregistrés avec le champion. Les probabilités de l'équipe B et leurs bornes sont construites comme les compléments exacts de celles de l'équipe A ; une propriété couvre les 101 valeurs de 0 à 1 et maintient les sommes égales à 1. Une abstention supprime les cotes publiables, les probabilités nulles ne produisent pas de cote infinie et le settlement n'accepte que `TEAM_A`, `TEAM_B` ou un void explicite. Le gate retourne 296 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 229 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le protocole reste volontairement binaire et fermé, tandis que la vérification physique de l'artefact demeure la responsabilité du registre avant activation du gate.
- **Commit/hash :** `251db68` (`feat(markets): add gated game winner plugin`).

## ML-013 — Service de prédiction pré-match

- **Statut :** `DONE`
- **Dépendances vérifiées :** le plugin `GAME_WINNER` `ML-012` et les feature snapshots reproductibles `FEAT-011` sont `DONE` ; le service utilise leurs contrats sans recalcul hors du pipeline temporel.
- **Fichiers créés/modifiés :** service et runtime `python/metiquo/models/predictions.py`, construction ciblée dans `python/metiquo/features/dataset.py`, migration `20260907_0025`, modèle ORM, exports et preuve PostgreSQL `tests/integration/test_prematch_predictions.py`.
- **Migrations :** création de `ml.prematch_predictions`. Chaque ligne conserve événement, équipes, feature snapshot, modèle, calibrateur, incertitude, cutoff, instant, probabilités et bornes A/B, confiance, état d'abstention, commit, empreinte stable d'inférence et empreinte propre à l'instant. Des clés étrangères, contraintes numériques, un trigger de cohérence et un trigger append-only protègent la preuve.
- **Commandes/tests exécutés :** Ruff, mypy strict, migration aller-retour, test PostgreSQL ciblé, puis gate global complet.
- **Résultat exact :** le service vérifie que le cutoff et l'instant de calcul précèdent le début planifié, que le champion a été entraîné strictement avant le cutoff et qu'il était déjà enregistré. Le loader relit le champion courant, vérifie physiquement son binaire via le registre, résout son artefact d'incertitude puis reconstruit le prédicteur. La feature candidate est calculée au cutoff exact ; un snapshot renvoyant un autre événement ou instant est refusé. La base exige que snapshot, équipes, cutoff, champion, calibrateur et incertitude correspondent encore au moment de l'insertion. La preuve entraîne le modèle sur la première game de la fixture, prédit la suivante avec un cutoff antérieur, puis répète la requête dix minutes plus tard : les deux lignes et leurs empreintes temporelles sont distinctes, tandis que le snapshot, la version modèle, les probabilités et l'empreinte d'inférence sont identiques. Toute tentative de modification échoue. Le gate retourne 297 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 232 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le décodage du binaire et la résolution de l'incertitude restent des adapters injectés, mais le loader impose leur passage par le registre vérifié avant toute inférence.
- **Commit/hash :** `5a43240` (`feat(ml): persist reproducible prematch predictions`).

## ML-014 — Pricing de série BO1/BO3/BO5 et BO2 conditionnel

- **Statut :** `DONE`
- **Dépendances vérifiées :** la prédiction pré-match `ML-013` et les règles canoniques de série `CNL-003` sont `DONE` ; le moteur accepte directement l'intervalle probabiliste historisé par le service.
- **Fichiers créés/modifiés :** moteur `python/metiquo/markets/series_pricing.py`, exports marchés, tests analytiques et simulation `tests/markets/test_series_pricing.py` ; les imports du service de prédiction ont aussi été découplés pour supprimer un cycle entre packages.
- **Migrations :** aucune ; seule la distribution `GAME_WINNER` reste publiable, tandis que les scores terminaux et nombres de games demeurent des détails internes calculés à la volée.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests de propriétés et simulation ciblés, puis gate global complet avec PostgreSQL réel.
- **Résultat exact :** BO1 conserve la probabilité de game ; BO3 et BO5 utilisent une énumération exacte jusqu'au nombre de victoires requis ; BO2 joue deux games et expose `TEAM_A`, `TEAM_B` et `DRAW` uniquement lorsque le format autorise le nul. À `p=0,60`, les probabilités équipe A obtenues sont respectivement `0,60000000`, `0,64800000`, `0,68256000` et `0,36000000`, avec `0,48000000` de nul en BO2. Une propriété couvre 101 probabilités pour les quatre formats et exige une somme exactement égale à 1. Les bornes d'incertitude sont propagées sur tous les coins de l'intervalle. Quand la side initiale est inconnue, les scénarios départ blue et départ red sont moyennés à poids égaux ; la preuve retrouve exactement la moyenne des deux distributions connues. Une simulation déterministe de 30 000 séries par format reste à moins d'un point de pourcentage de l'analytique. Format absent, BO non pris en charge ou règle de nul incohérente produisent une abstention sans prix. Le gate retourne 302 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 234 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'hypothèse d'indépendance conditionnelle entre games est explicite dans ce premier moteur et les marchés score exact/nombre de games restent désactivés.
- **Commit/hash :** `2ef7113` (`feat(markets): derive uncertainty-aware series pricing`).

## ML-015 — Explications structurées

- **Statut :** `DONE`
- **Dépendances vérifiées :** le service de prédiction immuable `ML-013` est `DONE` ; chaque explication exige son UUID de prédiction, sa version modèle et son feature snapshot exacts.
- **Fichiers créés/modifiés :** builder `python/metiquo/models/explanations.py` et suite `tests/model/test_explanations.py`.
- **Migrations :** aucune ; l'explication est une vue déterministe versionnée de preuves déjà immuables.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests de templates ciblés, puis gate global complet avec PostgreSQL réel.
- **Résultat exact :** le vocabulaire autorise uniquement les quatorze features du modèle tabulaire et leur associe des libellés contrôlés. Une preuve SHAP, native ou par coefficient doit contenir des contributions finies, sans doublon, et reconstruire la sortie du modèle depuis sa valeur de base dans une tolérance explicite. Les facteurs non nuls sont triés par magnitude puis par nom stable et ventilés en positifs/négatifs. Chaque phrase porte un identifiant de template, ses paramètres et au moins un champ structuré ; les contributions sont toujours affichées comme contributions du modèle et jamais comme causes. L'intervalle, la confiance, l'âge des données et toutes les features du modèle manquantes sont rendus par des templates fixes. Les valeurs brutes ne sont pas interpolées dans le texte : la fixture injecte une chaîne non fiable dans un champ et vérifie son absence de la narration. Les features de rumeur/absence et les explications rattachées au mauvais snapshot sont refusées. Deux constructions identiques produisent la même référence par hash. Le gate retourne 305 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 236 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'explication reste calculée à la demande depuis les preuves immuables, sans générateur de texte libre ni donnée externe.
- **Commit/hash :** `09bfb3d` (`feat(ml): render structured non-causal explanations`).

## ML-016 — API/UI modèles, train et promotion réels

- **Statut :** `DONE`
- **Dépendances vérifiées :** le lifecycle audité `ML-011`, les explications structurées `ML-015`, le dashboard `UI-007` et les mutations contractuelles `MCK-006` sont `DONE` ; la surface réelle réutilise leurs DTO sans branche spécifique dans le composant.
- **Fichiers créés/modifiés :** projection `python/metiquo/repositories/postgres_models.py`, routes réelles de lecture et d’administration, orchestration idempotente dans `python/metiquo/services/real_admin.py`, lifecycle de retrait explicite, migration `20260907_0026`, dashboard modèles, fixture Playwright réelle et test d’intégration PostgreSQL.
- **Migrations :** création de `ml.model_action_jobs` pour l’état observable des entraînements/décisions et de `ml.model_action_audits` pour la demande append-only ; extension contrôlée des événements de lifecycle avec l’action `retire`. Le downgrade conserve les retraits historiques via une contrainte antérieure `NOT VALID`, puis laisse `ML-011` supprimer normalement la table plus bas dans la chaîne.
- **Commandes/tests exécutés :** Ruff, mypy strict, test API PostgreSQL, cinq scénarios d’intégration et de migration successifs, Playwright réel ciblé, inspection et action d’entraînement dans le Navigateur, puis gate global `make check` avec PostgreSQL.
- **Résultat exact :** `/api/v1/models` et `/api/v1/backtests` exposent versions, métriques, baselines et rapports réels avec les mêmes enveloppes que le mock ; les détails et filtres partagent aussi les mêmes routes. La version publique réelle est l’UUID exact conservé dans chaque prédiction. Le dashboard affiche cet identifiant, les métriques persistées et les commandes d’entraînement, promotion et retrait. Chaque mutation crée un job idempotent et une trace sans stocker la clé brute. Le train délègue au workflow réel injecté et échoue explicitement s’il est absent. La promotion relit le benchmark du calibrateur, exige un gate promotable, les gains strictement positifs face à `competition_prior`, `recent_form` et `rating`, et au moins deux métriques dont une probabiliste primaire ; une fixture refusée retourne `409`, la fixture valide devient champion, puis son retrait est historisé. Le test Playwright prouve la promotion et le rafraîchissement du même dashboard sur DTO réels. Le gate retourne 306 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 240 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; ML-016 définit la frontière de workflow synchrone et observable, tandis que la commande reproductible et son assemblage de bout en bout restent le livrable explicite de `ML-017`.
- **Commit/hash :** `a14eb55` (`feat(ml): expose real model operations`).

## ML-017 — Gate P4 — cote juste bookmaker-free

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'API/UI réelle `ML-016` est `DONE` et sa frontière `RealModelTrainingWorkflow` est désormais satisfaite par l'orchestrateur concret ; les datasets, baselines, benchmark, ensemble, calibration, incertitude, rapport, registre et lifecycle livrés par `ML-001` à `ML-011` sont assemblés sans chemin parallèle.
- **Fichiers créés/modifiés :** workflow et artefact reproductible `python/metiquo/models/training.py`, fonction publique de rejeu du calibrateur, exports ML, commande `oe model-train`, cible `make model-train`, documentation opérateur et preuves unitaires/PostgreSQL.
- **Migrations :** aucune ; le gate publie dans les tables append-only et l'ObjectStore déjà versionnés jusqu'à la migration `20260907_0026`.
- **Commandes/tests exécutés :** commande exacte `make model-train MARKET=game_winner CODE_COMMIT=abcdef1 JSON=1`, test de rejeu ciblé, scénario PostgreSQL complet, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** le profil temporel par défaut réserve 20 périodes initiales, entraîne par fenêtres de validation de 10 périodes et garde 10 périodes de test final hors sélection. Le run de preuve couvre 40 observations OOF ; le gradient boosting sélectionné obtient `0,006829` de log loss et `0,006799` d'ECE, avec des gains stricts face à `competition_prior`, `recent_form` et `rating`. Le calibrateur Platt est choisi sur des prédictions OOS séparées. La commande émet les UUID et empreintes du dataset, des trois baselines, du benchmark, du calibrateur, de l'incertitude et de la version modèle. L'artefact JSON adressé par contenu conserve la recette déterministe, les vecteurs de développement, le préprocesseur train-only, le calibrateur et un exemple final dépourvu de label ; le test le recharge, entraîne à nouveau le candidat et retrouve exactement les probabilités brute et calibrée depuis le feature snapshot attendu, tout en refusant un autre UUID de snapshot. Un gate valide crée uniquement un `candidate` en attente d'approbation manuelle ; un modèle sans signal devient `blocked` et laisse le champion intact. Les noms de features bookmaker/cotes restent refusés avant entraînement et sont absents de l'artefact. Le gate retourne 309 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 243 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'artefact sérialise une recette et des vecteurs vérifiables au lieu d'un pickle exécutable, et la commande n'automatise jamais la décision humaine de promotion.
- **Commit/hash :** `4b18c23` (`feat(ml): complete reproducible training gate`).

## ODD-001 — Schéma odds append-only

- **Statut :** `DONE`
- **Dépendances vérifiées :** les conventions PostgreSQL `FND-004` et les DTO/scénarios mock `MCK-001` sont `DONE` ; le nouveau schéma reprend leurs UUID, vocabulaires fermés, UTC et décimaux sans dépendre d'un fournisseur concret.
- **Fichiers créés/modifiés :** modèles ORM `python/metiquo/db/odds_models.py`, migration `20260907_0027`, inventaire du head Alembic et test d'intégration PostgreSQL dédié.
- **Migrations :** création de `odds.providers`, `odds.provider_health`, `odds.events`, `odds.markets`, `odds.selections` et `odds.snapshots`. Les identités composées garantissent qu'un snapshot ne peut mélanger fournisseur, événement, marché ou sélection. Les contrôles de santé et snapshots possèdent des triggers communs interdisant UPDATE et DELETE.
- **Commandes/tests exécutés :** test PostgreSQL d'immutabilité et contraintes, cycle Alembic complet, démo d'ingestion depuis une base vide, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** chaque snapshot conserve les états fournisseur/événement/marché, le libellé et la ligne observés, une cote `NUMERIC(20,8)` supérieure ou égale à 1, l'instant fournisseur, l'instant d'enregistrement, la fiabilité temporelle, le statut informatif, une référence de payload brut, son SHA-256 facultatif, la provenance et une empreinte d'observation unique. Une observation non informative exige simultanément `captured_at` et `timestamp_reliable=true` ; une cote sans timestamp fiable n'est acceptée qu'avec `informational_only=true`. L'ordre de capture, les statuts, les participants, les règles de settlement et la cohérence des clés sont protégés en base. L'index demandé couvre exactement événement, marché, sélection et `captured_at`. La preuve insère une cote `2,25000000`, refuse `0,99000000`, refuse une observation signalable sans timestamp, accepte son équivalent informatif, puis fait échouer UPDATE et DELETE ainsi que la mutation d'un état de santé. Le gate retourne 310 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, mypy strict sur 246 fichiers et contrats sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; seules les observations historiques sont append-only à ce stade, tandis que les identités fournisseur restent le socle des adapters et de l'historisation livrés par `ODD-002` à `ODD-007`.
- **Commit/hash :** `babac85` (`feat(odds): add append-only odds schema`).

## MAP-001 — Schéma et modèle d’aliases datés

- **Statut :** `DONE`
- **Dépendances vérifiées :** les dimensions canoniques traçables `CNL-001` et le socle fournisseur `ODD-001` sont `DONE` ; un alias ne peut cibler qu'une équipe, une compétition ou un joueur réellement présent dans `core`.
- **Fichiers créés/modifiés :** modèle ORM `python/metiquo/db/mapping_models.py`, migration `20260907_0028`, chargement complet des métadonnées Alembic, inventaire du head et preuve PostgreSQL `tests/integration/test_entity_aliases.py`.
- **Migrations :** création de `core.entity_aliases` avec type et UUID canoniques, fournisseur, libellés brut et normalisé, fenêtre UTC semi-ouverte, provenance `auto`/`seeded`/`manual`, confiance, approbation, notes et instant de création. Une exclusion temporelle PostgreSQL empêche le même alias normalisé de se chevaucher chez un fournisseur et un type d'entité. Un trigger polymorphe vérifie l'existence de la cible dans `core.teams`, `core.competitions` ou `core.players`.
- **Commandes/tests exécutés :** Ruff et mypy ciblés, preuve des contraintes sur PostgreSQL, cycle Alembic complet, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** le test conserve deux UUID distincts pour l'équipe principale et son académie, accepte leurs aliases explicites distincts, puis date le passage de `Aurora Esports` à `Nova Aurora` pour la même équipe canonique. Il refuse qu'un second UUID revendique `aurora esports` pendant une fenêtre chevauchante, refuse une cible canonique absente et refuse une source manuelle dépourvue du couple approbateur/instant. Les fenêtres exigent `valid_to > valid_from`, la confiance reste dans `[0,1]` et un index couvre type, UUID canonique et bornes de validité. Le gate retourne 311 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 249 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'exclusion porte sur l'alias normalisé exact et n'introduit aucun rapprochement flou. La normalisation typographique sûre reste le livrable séparé de `MAP-002`.
- **Commit/hash :** `8e06ce7` (`feat(mapping): add dated canonical aliases`).

## MAP-002 — Normalisation sûre des noms

- **Statut :** `DONE`
- **Dépendances vérifiées :** le schéma d'aliases datés `MAP-001` est `DONE` ; la normalisation fournit désormais la forme exacte que ses résolveurs suivants pourront interroger sans modifier les identifiants canoniques déjà publiés.
- **Fichiers créés/modifiés :** package `python/metiquo/mapping`, règle fermée et versionnée `normalization.py`, exports publics et propriétés `tests/mapping/test_normalization.py`.
- **Migrations :** aucune ; `core.entity_aliases` conserve déjà `raw_alias`, `normalized_alias` et la fenêtre temporelle nécessaires.
- **Commandes/tests exécutés :** Ruff, mypy strict et 18 preuves ciblées, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `entity-name-typography-v1` applique NFKC, casse Unicode, espaces condensés et remplacement de toute ponctuation Unicode par un séparateur. La règle conserve les lettres accentuées, les symboles et chaque mot métier ; elle refuse un nom vide, composé uniquement de ponctuation ou contenant un caractère de contrôle invisible. Les formes composée et décomposée de `Équipe Élite` sont égales, mais `Equipe Elite` reste distinct. `Team Liquid` reste distinct de `Team Liquid Honda`, `Dplus` de `Dplus KIA`, `Karmine Corp` de `Karmine Corp Blue`, `Gen.G` de `Gen.G Academy`, `Aurora` de `Aurora 05` et `T1` de `T1A`. La comparaison publique est une égalité exacte des formes normalisées, sans distance ni rapprochement flou. Le gate retourne 329 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 252 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les accents absents et les tokens sponsor/academy ne sont volontairement pas effacés, car une absence de correspondance est moins dangereuse qu'une fusion erronée.
- **Commit/hash :** `836102e` (`feat(mapping): normalize entity names safely`).

## ODD-002 — Contrat OddsProvider

- **Statut :** `DONE`
- **Dépendances vérifiées :** le schéma append-only `ODD-001` est `DONE` ; le port reprend ses identités fournisseur/événement/marché/sélection et ses vocabulaires communs sans importer de modèle ORM ni d'adaptateur concret.
- **Fichiers créés/modifiés :** port contrôlable à l'exécution `python/metiquo/providers/contracts.py`, DTO fournisseur renforcés, export de compatibilité repository, identifiant de sélection dans le mock, contrat OpenAPI régénéré et suite partagée `tests/providers/odds_provider_contract.py`.
- **Migrations :** aucune ; `providerSelectionId` relie désormais le DTO normalisé à l'identité déjà persistée par `odds.selections`.
- **Commandes/tests exécutés :** Ruff, mypy et 17 tests de contrats ciblés, régénération OpenAPI, puis deux passages du gate global `make check`, dont le second depuis les artefacts de contrat enregistrés.
- **Résultat exact :** `OddsProvider` est un `Protocol` indépendant et contrôlable à l'exécution qui expose `list_events`, `get_event_markets`, `capture_snapshot` et `health`. Les événements refusent les participants dupliqués ; les marchés refusent les identifiants ou issues normalisées dupliqués ; chaque sélection conserve son identifiant fournisseur, son issue commune, son libellé et sa cote décimale. La suite réutilisable vérifie la fenêtre et le jeu des événements, l'unicité et la cohérence des marchés/sélections, l'appartenance fournisseur et l'ordre temporel des snapshots, l'identité du contrôle de santé, le tuple vide pour les marchés d'un événement inconnu, puis les erreurs de capture et de fenêtre. Un adaptateur de référence passe exactement cette suite sans qu'elle connaisse sa classe. Le scan de frontière interdit toute dépendance vers mock, import manuel ou futur flux licencié. Le gate retourne 333 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 257 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'ancien import `metiquo.repositories.contracts.OddsProvider` reste un export temporaire compatible, tandis que la source de vérité appartient désormais au package `providers`.
- **Commit/hash :** `20df453` (`feat(odds): formalize provider contract`).

## ODD-003 — MockOddsProvider réel du contrat

- **Statut :** `DONE`
- **Dépendances vérifiées :** le port et sa suite réutilisable `ODD-002` ainsi que les douze scénarios déterministes `MCK-003` sont `DONE` ; le mock consomme directement ce catalogue normatif.
- **Fichiers créés/modifiés :** projection temporelle de `MockOddsProvider` et injection facultative de `Clock` dans le bundle repository, plus preuve dédiée `tests/providers/test_mock_odds_provider.py`.
- **Migrations :** aucune ; les observations restent les DTO immuables du catalogue et aucune donnée n'est écrite.
- **Commandes/tests exécutés :** Ruff, mypy strict, 12 tests provider/repository ciblés, application de la suite exacte `assert_odds_provider_contract`, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** l'adaptateur n'expose que les événements déjà observés et possédant au moins un snapshot dont `captured_at` ne dépasse pas l'horloge injectée. Marché et capture utilisent la dernière observation disponible, tandis que chaque capture conserve tout l'historique connu dans l'ordre et recalcule `age_seconds` sans muter le catalogue. Une horloge placée juste avant le second prix retourne `4.20` et un seul UUID ; placée juste après, elle retourne `3.60` et les deux UUID originaux. Avancer l'horloge de cinq minutes fait passer le scénario stale de 600 à 900 secondes, tout en laissant sa fixture inchangée. Le contrôle de santé est daté au même instant, conserve le dernier succès observable et devient indisponible si aucune observation n'existe encore. La suite commune valide événements, marchés, sélections, captures, santé et erreurs sur le mock réel. Un scan du module refuse les clients HTTP, sockets, navigateurs et outils d'automatisation ; aucun accès réseau n'est exécuté. Le gate retourne 337 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 258 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; sans horloge explicite, le provider reste fixé à `catalog.reference_time` pour préserver le comportement déterministe existant.
- **Commit/hash :** `6a56a46` (`feat(odds): make mock provider time-aware`).

## ODD-004 — ManualImportOddsProvider

- **Statut :** `DONE`
- **Dépendances vérifiées :** le port fournisseur et sa suite commune `ODD-002` sont `DONE` ; l'adaptateur manuel produit exclusivement les mêmes `ProviderEvent`, `ProviderMarket`, `ProviderSelection`, `OddsCaptureResult` et `ProviderHealth`.
- **Fichiers créés/modifiés :** adapter `python/metiquo/providers/manual_import.py`, exports publics, format opérateur `docs/manual-odds-import.md` et preuves `tests/providers/test_manual_import_provider.py`.
- **Migrations :** aucune ; la publication PostgreSQL append-only reste la responsabilité du service d'historisation `ODD-007`. Le provider maintient un état atomique en mémoire pour normaliser les documents avant cette frontière.
- **Commandes/tests exécutés :** Ruff, mypy strict, 10 tests provider/contrat ciblés, Prettier et CSpell sur le format opérateur, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** CSV UTF-8 et liste JSON partagent vingt-trois champs stricts pour fournisseur logique, événement, début, participants, marché, sélection, cote décimale, capture, fiabilité temporelle, règles et provenance. Le CSV exige exactement l'en-tête et son ordre documentés ; JSON refuse clés supplémentaires et lignes non objet. Toutes les lignes sont validées avant publication, avec une erreur structurée par numéro, code, champ et message. Une fixture cumulant cote `0.50`, mauvais fournisseur et capture future retourne les trois erreurs, zéro document et zéro observation visible. La cohérence des identités événement/marché/sélection et l'unicité d'une observation à un instant sont aussi vérifiées contre l'état existant. La clé d'idempotence documentée est `sha256:<digest>` des octets exacts : le second import retourne `duplicate=true` sans ajouter de ligne. Une capture non fiable est forcée à `informational_only=true`. Les UUID provider sont déterministes, les prix et probabilités restent décimaux, et le document CSV valide passe toute la suite `OddsProvider`. Le gate retourne 343 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 260 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; cette étape valide et expose atomiquement un document sans anticiper le stockage PostgreSQL transactionnel et append-only prévu explicitement par `ODD-007`.
- **Commit/hash :** `ccf9d9f` (`feat(odds): add atomic manual import provider`).

## ODD-005 — LicensedOddsFeedProvider boundary

- **Statut :** `DONE`
- **Dépendances vérifiées :** le port structurel et sa suite commune `ODD-002` sont `DONE` ; la nouvelle base abstraite reprend exactement ses quatre opérations et ses DTO normalisés sans dépendance vers un transport ou un fournisseur.
- **Fichiers créés/modifiés :** frontière `python/metiquo/providers/licensed_feed.py`, exports publics, guide d'intégration future `docs/licensed-odds-feed.md` et squelette de contrat `tests/providers/test_licensed_feed_boundary.py`.
- **Migrations :** aucune ; le type `licensed_feed` est déjà réservé dans le schéma odds, mais aucun fournisseur concret n'est créé ou activé.
- **Commandes/tests exécutés :** Ruff, mypy strict et 11 tests de frontière ciblés, Prettier et CSpell sur le guide, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `LicensedOddsFeedProvider` est une classe abstraite qui exige `list_events`, `get_event_markets`, `capture_snapshot` et `health` et satisfait structurellement `OddsProvider` dès qu'un adaptateur complète ces méthodes. Sa configuration commune ne contient que le code logique, une référence d'accord et la confirmation explicite des droits ; elle normalise les valeurs, refuse les identités ambiguës et bloque toute activation sans confirmation contractuelle. Le module de production ne contient ni URL, ni valeur d'authentification, ni client réseau, et le choix `ODDS_PROVIDER` n'est pas étendu avant l'existence d'un adaptateur autorisé et testé. Le produit reste donc compilable et fonctionnel sans implémentation licenciée concrète. Le gate retourne 350 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 262 fichiers sont verts.
- **Blocker éventuel :** aucun pour la frontière ; tout adaptateur concret reste conditionné par un contrat validé, une documentation officielle et des tests d'intégration enregistrés.
- **ADR éventuel :** aucun ; le transport et les secrets seront propres au futur adaptateur afin de ne pas figer aujourd'hui une API inexistante.
- **Commit/hash :** `5f250d8` (`feat(odds): define licensed feed boundary`).

## ODD-006 — StakeAuthorizedProvider désactivé

- **Statut :** `DONE`
- **Dépendances vérifiées :** le port `OddsProvider` de `ODD-002` est `DONE` ; le squelette désactivé en reprend toute la surface sans produire d'événement, de marché ou de snapshot.
- **Fichiers créés/modifiés :** `DisabledProvider`, `StakeAuthorizedProvider`, quatre flags de configuration serveur, exemple d'environnement, scan statique `infra/scripts/check_provider_compliance.py`, branchement dans le gate `Makefile`, guide de conformité et preuves de démarrage/dépôt.
- **Migrations :** aucune ; le type réservé `stake_authorized` ne crée ni n'active aucun fournisseur en base.
- **Commandes/tests exécutés :** Ruff, mypy strict, 18 tests de configuration/provider ciblés, exécution autonome du scan de conformité, Prettier et CSpell sur le guide, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `STAKE_PROVIDER_ENABLED` et les confirmations d'autorisation écrite, de juridiction licite et de validation juridique valent `false` par défaut. Une activation dépourvue d'un seul gate échoue au chargement de `Settings`; même les quatre valeurs à `true` restent refusées tant qu'aucune implémentation autorisée n'est livrée. Le squelette satisfait structurellement `OddsProvider`, retourne des listes vides, refuse toute capture et expose exclusivement un état `unavailable` daté avec le motif réglementaire complet. Le scan exécuté par chaque `make check` couvre les sources de production et bloque les signatures d'adresse Stake, solveur CAPTCHA, proxy résidentiel, contournement géographique, cookie bookmaker, navigateur furtif et automatisation de mise ; une fixture synthétique prouve chaque règle tandis que le dépôt courant est propre. Le gate retourne 357 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, lint, contrats et mypy strict sur 268 fichiers sont verts.
- **Blocker éventuel :** aucun pour la désactivation ; l'activation réelle reste volontairement bloquée par l'absence d'autorisation, de validation juridique et d'implémentation approuvée.
- **ADR éventuel :** aucun ; les trois conditions de conformité et l'absence d'adaptateur concret sont des portes cumulatives, pas une simple bascule opérationnelle.
- **Commit/hash :** `7d39f26` (`feat(odds): enforce disabled Stake provider gate`).

## ODD-007 — Capture et historisation des cotes

- **Statut :** `DONE`
- **Dépendances vérifiées :** les captures déterministes `MockOddsProvider` de `ODD-003` et les documents atomiques `ManualImportOddsProvider` de `ODD-004` sont `DONE` ; le service persiste directement leur contrat commun.
- **Fichiers créés/modifiés :** identités UUID partagées `python/metiquo/providers/identity.py`, service transactionnel `python/metiquo/services/odds_capture.py`, exports publics, adaptation de l'import manuel, guide opérateur et preuve PostgreSQL `tests/integration/test_odds_capture_history.py`.
- **Migrations :** aucune ; le schéma append-only, les clés composées, l'empreinte unique et les colonnes d'observation livrés par `ODD-001` couvrent le besoin sans nouvelle structure.
- **Commandes/tests exécutés :** Ruff, mypy strict, deux passages des trois scénarios PostgreSQL ciblés, tests providers existants, Prettier et CSpell sur le guide, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `OddsCaptureService` valide entièrement événement, marchés, sélections, fournisseur et ordre temporel avant d'ouvrir une transaction. Il crée ou actualise les identités fournisseur→événement→marché→sélection, puis ajoute les observations avec cote, états, ligne, libellé, instant, fiabilité, référence/hash de payload et provenance. Une empreinte SHA-256 canonique et les conflits PostgreSQL rendent le rejeu exact idempotent. Le scénario mock insère `4,20`, ignore son rejeu puis ajoute `3,60` ; le scénario manuel conserve le SHA-256 exact du document et ses quatre identifiants externes. Une troisième preuve conserve séparément une première cote, sa confirmation identique à l'instant suivant, puis un changement simultané de cote, statut événement/marché, ligne et libellé. Les trois lignes restent chronologiques et aucune valeur antérieure n'est écrasée. La déduplication physique d'un intervalle identique reste volontairement inactive afin de préserver chaque confirmation observée. Le gate retourne 360 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, scan conformité, contrats et mypy strict sur 271 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; l'empreinte inclut l'identifiant immuable de snapshot et la provenance, tandis que le conflit global protège aussi contre le rejeu d'un historique fournisseur déjà vu.
- **Commit/hash :** `909fbd7` (`feat(odds): persist append-only capture history`).

## ODD-008 — Fraîcheur et admissibilité de marché

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'historique append-only `ODD-007` est `DONE` ; le gate consomme ses snapshots immuables et recalcule leur âge au moment exact de chaque décision.
- **Fichiers créés/modifiés :** politique et gate `python/metiquo/markets/admissibility.py`, exports marchés, nouvelles abstentions normatives, configuration globale et surcharges provider/marché/phase, contrat OpenAPI/TypeScript régénéré, guide et dix tests de marché dédiés.
- **Migrations :** aucune ; la décision est calculée à partir des timestamps et états déjà enregistrés dans `odds.snapshots`.
- **Commandes/tests exécutés :** Ruff, mypy strict, 30 tests ciblés de marché/configuration/contrats, génération OpenAPI, puis deux passages du gate global `make check` avec PostgreSQL réel ; le premier a produit le diff TypeScript attendu, le second depuis ce contrat enregistré est entièrement vert.
- **Résultat exact :** `ODDS_MAX_AGE_SECONDS` reste le SLA global et des dictionnaires JSON permettent des surcharges par provider, type de marché et phase, avec priorité provider→marché→phase→global et durées strictement positives. À la borne exacte de 90 secondes, le marché est admissible ; à 91 secondes, `ODDS_STALE` le bloque. Le gate exige le statut `open`, un événement pré-match non commencé, une capture antérieure au calcul, un même périmètre événement/marché, la sélection demandée et toutes les issues nécessaires au no-vig. Le marché partiel n'est accepté que si une stratégie marque explicitement sa compatibilité. Les captures informatives sont bloquées et la phase live retourne toujours `LIVE_BETTING_OUT_OF_SCOPE`. Les nouvelles raisons d'abstention sont reflétées dans le contrat client généré. Le gate retourne 370 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, scan conformité, contrats et mypy strict sur 273 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les surcharges les plus proches du fournisseur priment de façon déterministe, et le live ne peut pas être activé par une simple valeur de SLA.
- **Commit/hash :** `1ded8bb` (`feat(odds): gate market admissibility`).

## ODD-009 — Health provider et API odds history

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'historique append-only `ODD-007`, son gate de fraîcheur `ODD-008` et le contrat de lecture mock `MCK-005` sont `DONE` ; l'adaptateur réel réutilise les mêmes `OddsSnapshot`, `ProviderHealth` et métadonnées de réponse.
- **Fichiers créés/modifiés :** historisation des contrôles dans `OddsCaptureService`, projections PostgreSQL odds dans les repositories canonique/admin, enrichissement du contrat santé et des routes réelles, contrat OpenAPI/TypeScript régénéré, indicateurs dans l'écran Santé data, guide opérateur et preuve API `tests/integration/test_odds_history_api.py`.
- **Migrations :** aucune ; `odds.provider_health`, les identités fournisseur et `odds.snapshots` append-only livrés par `ODD-001` portent déjà toutes les données nécessaires.
- **Commandes/tests exécutés :** tests ciblés provider/repositories/API, Ruff, ESLint, Prettier, CSpell, TypeScript et mypy strict, génération OpenAPI, puis gate global `make check` sur PostgreSQL réel depuis les contrats enregistrés.
- **Résultat exact :** chaque tentative de capture ajoute un contrôle de santé. Un succès enregistre la dernière capture ; un échec sans historique devient `unavailable`, tandis qu'un échec après succès devient `degraded` sans modifier ni supprimer les snapshots existants. L'API admin réunit Oracle's Elixir et tous les providers odds et expose `lastCaptureAt`, `ageSeconds`, `failureCount` et `freshness`, avec le SLA provider puis global. `GET /api/v1/events/{eventId}/odds-history` reconstruit chronologiquement les identités, cotes décimales, probabilités implicites, états, âges et provenances PostgreSQL ; `asOf` est la dernière capture. La preuve réelle publie une cote, confirme `fresh`, force ensuite une panne, retrouve exactement la même cote et confirme `degraded`, 30 secondes d'âge et un échec. Le gate retourne 371 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, scan conformité, contrats et mypy strict sur 274 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; tant que `MAP-003` n'a pas résolu les identités externes, la lecture repose sur l'identifiant événement déjà partagé, sans rapprochement implicite dangereux.
- **Commit/hash :** `3ffc775` (`feat(odds): expose provider health history`).

## MAP-003 — Score de matching événement

- **Statut :** `DONE`
- **Dépendances vérifiées :** la normalisation typographique sûre `MAP-002`, l'historisation des événements fournisseur `ODD-007` et les événements canoniques `CNL-003` sont `DONE` ; le score relie leurs contrats sans rapprochement flou.
- **Fichiers créés/modifiés :** moteur `python/metiquo/mapping/event_matching.py`, exports mapping, modèles d'audit odds, migration `20260907_0029`, raccord de l'historique odds canonique, guide et sept fixtures de scoring, adaptation des preuves de migration et du parcours API PostgreSQL.
- **Migrations :** `20260907_0029` crée `odds.event_mapping_attempts` et `odds.event_mapping_candidate_scores`, leurs contraintes, index et protections append-only. Chaque tentative conserve statut, événement sélectionné éventuel, score supérieur, orientation, version et motif ; chaque candidat conserve son rang et les quatre composantes.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests ciblés scoring/migrations/API canonique, démonstration d'ingestion depuis une base vide, puis gate global `make check` sur PostgreSQL réel.
- **Résultat exact :** `event-match-v1` applique les poids équipes `0,60`, heure `0,20`, compétition `0,15` et format `0,05`. Les équipes utilisent uniquement l'égalité normalisée ou un alias daté ; un ordre A/B inversé obtient le même score et échange ensuite `TEAM_A`/`TEAM_B`. L'heure vaut `1` à cinq minutes, `0,75` à trente minutes, `0,25` à deux heures puis `0`. Un score `>= 0,95` est automatique, `>= 0,75` passe en revue et le reste est rejeté ; deux candidats à `0,05` ou moins restent en revue. `TBD`, `Winner of`, `Loser of` et `To be determined` sont refusés. Seul `auto_matched` expose un identifiant et autorise le remapping, ce qui bloque explicitement toute prédiction ambiguë. La preuve intégrée capture un événement sous un UUID fournisseur distinct, persiste les quatre scores à `1`, le résout puis retrouve ses cotes via l'UUID canonique. Le gate retourne 378 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, scan conformité, contrats et mypy strict sur 277 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; les bandes horaires et la marge de proximité appartiennent à la politique versionnée initiale et pourront évoluer sous une nouvelle version sans réécrire l'audit.
- **Commit/hash :** `0cc7b23` (`feat(mapping): score provider events safely`).

## MAP-004 — File de revue mapping et actions

- **Statut :** `DONE`
- **Dépendances vérifiées :** le score persistant `MAP-003` et la file opérateur `UI-009` sont `DONE` ; les routes réelles réutilisent les mêmes contrats que le mode mock.
- **Fichiers créés/modifiés :** états et audit PostgreSQL de revue, repository et service de mutation réels, routes admin, résolution manuelle de l'historique odds, contrats OpenAPI/TypeScript, interface de revue et journal d'audit, guide opérateur et preuves API/E2E.
- **Migrations :** `20260907_0030` crée `odds.mapping_reviews` et `odds.mapping_audits`. Une revue référence exactement une tentative immuable ; le journal impose action, acteur, motif, empreinte d'idempotence unique et aperçu JSON, puis interdit toute mise à jour ou suppression par trigger.
- **Commandes/tests exécutés :** tests API et repository mock, preuve PostgreSQL ciblée, génération OpenAPI, Ruff, mypy strict, ESLint, Prettier, CSpell, TypeScript, tests composants, deux scénarios Playwright de revue, puis gate global `make check` sur PostgreSQL réel depuis le contrat enregistré.
- **Résultat exact :** toute décision `review` crée automatiquement une tâche `pending` avec candidats et quatre composantes de score enregistrés. L'API réelle liste la file, exige un candidat explicite pour approuver, permet le rejet et crée des alias manuels datés vers une entité canonique validée. Chaque mutation peut être rejouée par clé sans doublon et publie acteur, motif et impact dans le journal commun. Une approbation rend les snapshots provider lisibles sous l'événement canonique et applique l'inversion A/B du candidat, sans modifier aucun snapshot ni signal historique. L'écran envoie désormais l'identifiant candidat séparément, cible l'équipe correcte pour l'alias et affiche le nombre d'observations touchées. La preuve réelle approuve une revue, en rejette une autre, rejoue l'approbation, crée l'alias et vérifie trois audits pour deux snapshots inchangés. Le gate retourne 379 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 280 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; la tentative et ses scores restent append-only, tandis que seule la ligne d'état de revue est mutable afin de représenter la décision courante sans réécrire sa preuve.
- **Commit/hash :** `cd58db5` (`feat(mapping): add audited review workflow`).

## MAP-005 — Mapping canonique des marchés

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'historique de capture `ODD-007` et le registre de capacités fermé par défaut `CNL-006` sont `DONE` ; le mapping complète leur preuve de règles sans activer de nouveau plugin implicitement.
- **Fichiers créés/modifiés :** moteur structurel `python/metiquo/mapping/market_mapping.py`, exports publics, modèles odds, migration `20260907_0031`, guide de mapping et treize fixtures unitaires/PostgreSQL, plus adaptation des preuves de migration.
- **Migrations :** `20260907_0031` crée `odds.market_rules` et `odds.market_mapping_attempts`. Les références de règlement et toutes les tentatives sont append-only ; une tentative inconnue conserve le libellé et le descripteur provider JSON sans renseigner de type, période ou règle canonique.
- **Commandes/tests exécutés :** Ruff, mypy strict, tests de conventions DB, douze fixtures structurelles, preuve PostgreSQL de mapping/stockage/immutabilité, cycle Alembic puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** une référence versionnée active doit correspondre exactement au type, à la période, à la présence d'une ligne, à l'unité, au nombre et à l'ensemble des issues ainsi qu'aux politiques remake, forfait et annulation. Le libellé n'est jamais lu par la décision : deux libellés différents passent avec la même structure, tandis que `Match winner` associé à un type inconnu reste `unknown`. Une règle séparée est nécessaire pour une issue `DRAW`; référence absente, inconnue ou inactive et toute divergence structurelle ferment le marché avec un motif stable. `require_mapped()` refuse alors toute structure, ce qui empêche le marché d'atteindre prédiction ou pricing. L'enregistrement de règle est idempotent à signature identique et refuse une redéfinition. Le gate retourne 392 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 284 fichiers sont verts.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** aucun ; le registre ne pré-enregistre que des signatures explicitement fournies et ne déduit jamais une règle à partir d'un texte commercial.
- **Commit/hash :** `047b824` (`feat(mapping): resolve markets structurally`).

## MAP-006 — Gate P5 — événement coté résolu

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'historique et la santé provider `ODD-009`, les décisions événement auditées `MAP-004` et le mapping structurel fermé `MAP-005` sont `DONE` ; le pipeline les réutilise sans voie de contournement vers le pricing.
- **Fichiers créés/modifiés :** gate et orchestration `python/metiquo/services/odds_mapping.py`, projection structurelle des marchés provider, rapport de capture enrichi, contrats provider/import manuel/mock, OpenAPI et client TypeScript généré, guide opérateur et preuve PostgreSQL `tests/integration/test_resolved_odds_gate.py`.
- **Migrations :** aucune ; le gate relit les tentatives de mapping et snapshots append-only déjà enregistrés par P5 sans modifier leur schéma ni leur contenu.
- **Commandes/tests exécutés :** deux scénarios PostgreSQL ciblés puis 44 tests providers, contrats, capture et API ; Ruff, mypy strict, Prettier et CSpell ; génération OpenAPI ; deux passages du gate global `make check`, le premier confirmant les 394 tests avant de signaler le diff client attendu, le second depuis le contrat enregistré entièrement vert.
- **Résultat exact :** le contrat `ProviderMarket` transporte désormais l'unité et les politiques explicites de remake, forfait et annulation, et l'import manuel exige ces 27 colonnes. `ResolvedOddsPipeline` capture une seule fois l'état provider, résout l'événement, mappe exactement les marchés capturés et remet un contexte pricing uniquement si l'identité canonique, tous les marchés et au moins un snapshot horodaté fiable sont enregistrés. La preuve manuelle insère deux observations, autorise le pricing puis rejoue le document avec zéro insertion et les mêmes identifiants immuables. Une compétition ambiguë reste en revue malgré un marché résolu ; le provider mock atteint le mapping mais son marché à une seule issue reste structurellement inconnu. Les deux chemins lèvent un refus explicite avant pricing. La file UI réelle d'approbation/rejet et son audit restent couvertes par `MAP-004`. Le gate retourne 394 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 286 fichiers sont verts.
- **Blocker éventuel :** aucun ; P5 est fermé et la phase P6 peut démarrer par `VAL-001`.
- **ADR éventuel :** aucun ; le contexte de sortie est volontairement minimal et ne calcule pas encore de probabilité ou de prix, responsabilités de P6.
- **Commit/hash :** `98c96a5` (`feat(mapping): gate resolved odds for pricing`).

## VAL-001 — Probabilité implicite et no-vig

- **Statut :** `DONE`
- **Dépendances vérifiées :** le mapping structurel `MAP-005` est `DONE` et fournit le domaine canonique exact des issues avant tout calcul de prix.
- **Fichiers créés/modifiés :** moteur `python/metiquo/pricing/no_vig.py`, exports pricing, guide numérique `docs/no-vig-pricing.md` et douze tests manuels/de propriétés dans `tests/pricing/test_no_vig.py`.
- **Migrations :** aucune ; ce ticket introduit des valeurs immuables de calcul sans persistance avant les politiques et opportunités des tickets suivants.
- **Commandes/tests exécutés :** Ruff et mypy strict ciblés, 36 tests pricing/finance/admissibilité/série, Prettier et CSpell, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `implied_probability()` applique `q = 1/O` en précision décimale fixe. `proportional-v1` normalise les probabilités brutes par leur overround et enregistre sa version dans chaque résultat. Les domaines équipe A/équipe B, équipe A/nul/équipe B et over/under sont les seuls ensembles reconnus comme mutuellement exclusifs et exhaustifs. Une cote non finie ou inférieure à `1`, un doublon, une issue inattendue ou un marché incomplet est refusé ; seule une stratégie future déclarant explicitement la compatibilité partielle peut franchir ce dernier contrôle, et sa sortie doit encore fournir une probabilité par cote et sommer à `1` dans la tolérance `1E-24`. Les preuves couvrent l'exemple manuel `4,00`/`1,25`, un marché avec nul et 625 combinaisons représentatives de cotes. Le gate retourne 406 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 289 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-002` peut consommer ces probabilités bookmaker normalisées.
- **ADR éventuel :** aucun ; seule la normalisation proportionnelle est activée pour le MVP, les autres méthodes devant annoncer une nouvelle version et leurs capacités explicites.
- **Commit/hash :** `92f1a14` (`feat(pricing): normalize bookmaker margin`).

## VAL-002 — Cote juste, edge, EV et EV prudente

- **Statut :** `DONE`
- **Dépendances vérifiées :** les prédictions pré-match immuables `ML-013` fournissent les probabilités centrale et basse ; `VAL-001` fournit la cote offerte et sa probabilité bookmaker no-vig dans un même objet validé.
- **Fichiers créés/modifiés :** moteur `python/metiquo/pricing/value.py`, validation renforcée de `NoVigQuote`, exports pricing, guide `docs/value-pricing.md` et cinq tests numériques dans `tests/pricing/test_value.py`.
- **Migrations :** aucune ; le ticket calcule des résultats immuables en mémoire, avant la politique persistée de `VAL-003` et les opportunités suivantes.
- **Commandes/tests exécutés :** Ruff et mypy strict ciblés, 17 tests pricing, Prettier et CSpell, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** `value-pricing-v1` consomme directement une `NoVigQuote`, une probabilité modèle centrale et sa borne basse ordonnée. Il applique `fair_odds = 1/p`, `edge = p - p_book_no_vig`, `EV = p*O - 1` et `EV_prudente = p_low*O - 1` en `Decimal` de précision locale fixe. L'exemple SFG à `4,00`, `30 %` et `27 %` produit une cote juste `3,333…`, un edge d'environ `6,19 %`, une EV de `20 %` et une EV prudente de `8 %`. À `p=0`, la cote juste est explicitement absente et signalée non bornée plutôt que sérialisée en infini, avec les deux EV à `-1` ; à `p=1`, elle vaut exactement `1`. Une preuve sur les 101 valeurs centésimales confirme formules, monotonie de la cote juste et ordre EV prudente/EV. Le gate retourne 411 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 291 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-003` peut désormais versionner les seuils appliqués à ces métriques.
- **ADR éventuel :** aucun ; l'absence de cote juste à probabilité zéro est une représentation finie et explicite que le futur gate transformera en abstention.
- **Commit/hash :** `3e2e6ab` (`feat(pricing): compute fair odds and value`).

## VAL-003 — Configuration versionnée des seuils

- **Statut :** `DONE`
- **Dépendances vérifiées :** les valeurs serveur typées de `FND-003` couvrent les seuils globaux ; les métriques exactes de `VAL-002` sont `DONE` et prêtes à être comparées à une politique résolue.
- **Fichiers créés/modifiés :** domaine et résolution `python/metiquo/pricing/policy.py`, repository PostgreSQL audité, modèles `python/metiquo/db/pricing_models.py`, migration `20260907_0032`, contrat `Value`, OpenAPI/client TypeScript, scénario mock, guide et preuves unitaires/PostgreSQL.
- **Migrations :** `20260907_0032` crée `signals.value_policies` et `signals.value_policy_audits`, leurs contraintes, index, références de révision et triggers append-only. Les seuils, surcharges, frontières temporelles et empreintes sont conservés sans mise à jour possible.
- **Commandes/tests exécutés :** Ruff, mypy strict, 43 tests pricing/contrats/mock, 46 tests ciblés avec migrations PostgreSQL, génération OpenAPI, TypeScript et 20 composants, reconstruction depuis base vide, puis deux passages du gate global `make check`. Le premier a identifié l'attente historique de révision `0031`, corrigée et vérifiée de nouveau par quatre tests ciblés avant le second passage vert.
- **Résultat exact :** chaque politique enregistre `min_edge`, `min_ev`, `min_conservative_ev`, `max_odds_age_seconds`, `min_mapping_confidence`, la fin du tuning et le début du test final. Toute frontière où le tuning atteint ou dépasse le test final est refusée en Python et en base. La résolution applique global, marché, compétition puis bucket, chaque niveau ne remplaçant que ses champs déclarés et publiant les scopes effectivement utilisés. Une version identique est idempotente, une redéfinition est interdite et toute version après la première doit référencer la précédente. Création et révision ajoutent acteur, motif et document complet à l'audit ; les tests prouvent que `UPDATE` et `DELETE` échouent physiquement. Tous les signaux `Opportunity` transportent désormais `value.policyVersion`, y compris le catalogue mock et le contrat généré. Le gate retourne 416 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 297 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-004` peut appliquer ces seuils avec les autres garde-fous d'admission.
- **ADR éventuel :** aucun ; la priorité `global → marché → compétition → bucket` est enregistrée comme règle déterministe initiale, et tout changement de contenu exige une nouvelle version.
- **Commit/hash :** `63dd714` (`feat(pricing): version signal threshold policies`).

## VAL-004 — Garde-fous d’admission

- **Statut :** `DONE`
- **Dépendances vérifiées :** la fraîcheur et l’état de marché `ODD-008`, le matching événement `MAP-003`, le champion de production `ML-011`, le registre de capacités `CNL-006` et la politique résolue `VAL-003` sont `DONE` ; le gate compose leurs sorties typées sans nouvelle heuristique.
- **Fichiers créés/modifiés :** décision ordonnée `python/metiquo/pricing/admission.py`, exports pricing, deux motifs d’abstention précis, contrat OpenAPI/client TypeScript régénéré, guide `docs/value-admission.md`, test de stabilité du contrat et seize scénarios dédiés dans `tests/pricing/test_admission.py`.
- **Migrations :** aucune ; le gate produit une décision immuable à partir des états, timestamps, métriques et seuils déjà versionnés.
- **Commandes/tests exécutés :** Ruff, mypy strict, 37 tests pricing ciblés, 25 tests contrats/admission, génération OpenAPI, TypeScript, Prettier et CSpell, puis gate global `make check` isolé avec PostgreSQL réel. Une première tentative chevauchée avec un processus résiduel a confirmé une collision Alembic sur la base partagée ; la relance unique après terminaison est entièrement verte.
- **Résultat exact :** `ValueAdmissionGate` exécute toujours le même ordre public : capacité, qualité source, champion, mapping événement, règles marché, marché ouvert, événement non commencé, cutoff strictement antérieur au départ, âge des cotes, confiance du mapping, edge, EV puis EV prudente. Il évalue tous les contrôles afin de publier une preuve complète, ordonnée et sans doublon, mais un seul échec rend `admitted=false`. Une source non fraîche, un modèle non champion, un marché suspendu ou réglé, un événement déjà commencé, un cutoff invalide et des cotes trop anciennes ne passent jamais. Les bornes exactes de la politique sont admises ; une EV centrale insuffisante et une EV prudente positive mais sous le seuil ont désormais leurs propres motifs, distincts de l’EV prudente négative. Le gate retourne 432 tests Python, 20 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 299 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-005` peut transformer ces décisions refusées en abstentions de première classe jusque dans l’interface.
- **ADR éventuel :** aucun ; l’ordre constitue une surface publique stable pour l’audit, sans court-circuit qui masquerait les causes secondaires.
- **Commit/hash :** `58d5b66` (`feat(pricing): enforce ordered admission guards`).

## VAL-005 — Abstention de première classe

- **Statut :** `DONE`
- **Dépendances vérifiées :** la matrice d’admission `VAL-004` et les estimations de couverture, confiance et distance au domaine `ML-008` sont `DONE` ; leurs motifs sont réunis sans transformer un refus attendu en exception système.
- **Fichiers créés/modifiés :** vocabulaire et ordre public des abstentions, invariants `Quality`, moteur `python/metiquo/pricing/abstention.py`, raccord de l’ordre au gate d’admission, libellés UI exhaustifs, fiche signal, guide `docs/value-abstention.md` et scénarios Python/TypeScript dédiés.
- **Migrations :** aucune ; la persistance append-only des abstentions appartient à `VAL-006`, tandis que ce ticket ferme leur représentation métier et leur présentation.
- **Commandes/tests exécutés :** Ruff, mypy strict, 65 tests pricing/contrats/mock ciblés, TypeScript et cinq tests web, génération OpenAPI sans diff de schéma, Prettier, CSpell et trois scénarios Playwright de fiche signal, puis gate global `make check` avec PostgreSQL réel.
- **Résultat exact :** les quinze raisons SFG sont conservées dans `SFG_ABSTENTION_REASONS` et les extensions déjà requises par les contrôles de marché/pricing restent contractuelles. `ValueDecisionEngine` retourne soit une value admise, soit une `AbstentionDecision` non vide ; un blocage ML peut donc produire une décision valide avec `evaluated_value=None`. `LOW_DATA_COVERAGE` devient `INSUFFICIENT_HISTORY`, les codes OOD convergent vers `OUT_OF_DISTRIBUTION`, les causes amont et admission sont réunies, triées par l’ordre public et débarrassées des doublons. Un code bloquant inconnu est refusé à la frontière. `Quality` exige désormais exactement zéro motif pour une décision publiable et au moins un motif unique et ordonné sinon. Le dashboard et la fiche signal affichent les libellés français de chacun des 22 codes, avec exhaustivité vérifiée par le type généré. Le gate retourne 438 tests Python, 21 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 301 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-006` peut persister les valeurs calculées et les abstentions sans changer leur sémantique.
- **ADR éventuel :** aucun ; l’abstention reste une décision structurante prévue par la SFG, désormais rendue explicite plutôt que redéfinie.
- **Commit/hash :** `7008a5e` (`feat(pricing): make abstention a first-class outcome`).

## VAL-006 — Persistence append-only predictions/signals

- **Statut :** `DONE`
- **Dépendances vérifiées :** les prédictions pré-match append-only `ML-013`, les abstentions structurées `VAL-005` et l'historique coté immuable `ODD-007` sont `DONE` ; la preuve de mapping événement ajoute la liaison canonique exacte entre cote et prédiction.
- **Fichiers créés/modifiés :** modèle et repository `signals.signals`, migration `20260908_0033`, exports pricing, guide `docs/signal-persistence.md`, adaptation des preuves de migration et scénario PostgreSQL `tests/integration/test_signal_persistence.py`.
- **Migrations :** `20260908_0033` crée `signals.signals` avec références restrictives vers snapshot de cote, prédiction, tentative de mapping et version de politique. Les contrôles ferment les cinq grades, l'état calculé/non calculé, les motifs, probabilités, métriques, fraîcheur et empreinte. Un trigger valide les sources avant insertion ; un second rejette tout `UPDATE` ou `DELETE`.
- **Commandes/tests exécutés :** Ruff et mypy ciblés, preuve intégrée signaux/migrations/prédictions, puis gate global `make check` avec PostgreSQL réel, contrat OpenAPI synchronisé et client TypeScript régénéré sans diff.
- **Résultat exact :** chaque publication recharge sa politique, son snapshot horodaté fiable, sa prédiction immuable et sa résolution automatique ou manuellement approuvée. L'événement fournisseur doit correspondre au snapshot, l'événement canonique à la prédiction, l'orientation A/B et la confiance au candidat retenu, la cote et les trois probabilités à leurs sources, et l'âge à `computed_at - captured_at`. Une value admise exige une prédiction activée ; une abstention sans calcul est `BLOCKED`, tandis que `NO_EDGE` conserve ses métriques. Les primitives forment un SHA-256 unique et un UUID déterministe : un replay exact retourne la même ligne, un nouvel instant ou état ajoute un signal. `reproduce()` recalcule probabilité implicite, cote juste, edge, EV et EV prudente et revérifie confiance, âge et empreinte. La preuve rejoue une value, ajoute un blocage stale, refuse une cote forgée par SQL puis prouve l'interdiction physique de mise à jour et suppression. Le gate retourne 439 tests Python, 21 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 304 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-007` peut projeter les grades admissibles en opportunités réelles tout en gardant `NO_EDGE` et `BLOCKED` pour le diagnostic.
- **ADR éventuel :** aucun ; une correction publie un nouveau signal avec de nouvelles preuves et ne dispose d'aucune voie de réécriture silencieuse.
- **Commit/hash :** `48f5360` (`feat(pricing): persist immutable signals`).

## VAL-007 — Projection Opportunités et APIs réelles

- **Statut :** `DONE`
- **Dépendances vérifiées :** la persistance immuable `VAL-006`, le contrat de lecture mock `MCK-005` et les écrans opportunités/détail `UI-004` et `UI-006` sont `DONE` ; le mode réel réutilise le même `Opportunity` sans copie de DTO.
- **Fichiers créés/modifiés :** projection `PostgresOpportunityRepository`, routes liste/détail/explication réelles, filtrage diagnostic partagé avec le mock, diagnostics de prédiction enregistrés, migration `20260908_0034`, guide `docs/real-opportunities.md`, README et preuves API/PostgreSQL étendues.
- **Migrations :** `20260908_0034` ajoute `data_coverage` et `out_of_distribution_distance` à `ml.prematch_predictions`. Les anciennes lignes peuvent rester nulles afin de ne pas inventer de diagnostics rétroactifs ; le trigger exige les deux valeurs exactes pour chaque nouvelle prédiction et la projection ignore les preuves historiques incomplètes.
- **Commandes/tests exécutés :** Ruff, mypy ciblé, 15 tests mock/réel/migrations/signaux, génération OpenAPI et client TypeScript sans diff, puis gate global `make check` sur PostgreSQL réel.
- **Résultat exact :** les routes réelles `/api/v1/opportunities`, détail et explication recomposent événement canonique, marché et snapshot provider, prédiction et diagnostics ML, métriques immuables, qualité et métadonnées `real`. La liste normale contient seulement `STRONG_VALUE`, `VALUE` et `WATCH`, triés par EV prudente décroissante puis calcul récent ; filtres compétition, équipe, marché, grade, edge, EV, confiance, fraîcheur et dates sont identiques au mock. Une demande explicite `grade=NO_EDGE` ou `grade=BLOCKED` ouvre le diagnostic des signaux calculés sans les compter comme opportunités ; une abstention antérieure au calcul n'est pas déguisée en `Value`. La preuve publie deux snapshots successifs à `1,80` puis `2,00`, confirme le nouvel ordre, les clés DTO mock/réel identiques, le filtre d'EV, le détail lié au bon snapshot, l'explication `ODDS_STALE` et le refus d'un signal non calculé. Le gate retourne 439 tests Python, 21 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 306 fichiers sont verts.
- **Blocker éventuel :** aucun ; `VAL-008` peut maintenant faire apparaître un nouveau snapshot/signal sans remplacer silencieusement la fiche déjà ouverte.
- **ADR éventuel :** aucun ; une preuve legacy sans diagnostics est omise explicitement jusqu'à recalcul, choix plus sûr qu'une valeur de couverture ou distance fabriquée.
- **Commit/hash :** `9c81ab4` (`feat(api): project real opportunities`).

## VAL-008 — Gestion changement de cote en UI

- **Statut :** `DONE`
- **Dépendances vérifiées :** l'historique append-only `ODD-007`, les signaux immuables `VAL-006` et les écrans dashboard/détail `UI-004` et `UI-005` sont `DONE` ; la projection réelle `VAL-007` expose un nouveau signal lors d'un recalcul sans modifier l'ancien.
- **Fichiers créés/modifiés :** polling React Query du dashboard et de la fiche signal, rapprochement strict marché/sélection, repères de snapshot, guide `docs/odds-change-ui.md`, tests unitaires de présentation et scénarios Playwright opportunités/détail.
- **Migrations :** aucune ; les nouveaux snapshots et signaux utilisent les tables append-only existantes, tandis que ce ticket ne change que leur actualisation et leur présentation.
- **Commandes/tests exécutés :** TypeScript et tests web ciblés, ESLint ciblé, 11 scénarios Playwright opportunités/détail, gate global `make check` sur PostgreSQL réel, suite Playwright complète puis preuve enrichie du second signal rejouée seule.
- **Résultat exact :** les opportunités et historiques sont actualisés toutes les 30 secondes et la santé provider toutes les 60 secondes. Les réponses précédentes restent rendues pendant le refetch ; les lignes et cartes sont indexées par `signalId`, et Playwright prouve que le même nœud de ligne demeure monté pendant une requête bloquée. La cote principale reste celle du snapshot du signal ; seule une observation plus récente du même `marketId` et de la même sélection déclenche `Cote mise à jour`, avec son prix et son mouvement séparés. La fiche et son explication sont immuables par identifiant, seul l'historique est actualisé, et la table marque simultanément `Snapshot du signal` et `Dernière cote`. Le scénario de `4,20` à `3,60` confirme l'ancien prix, le nouveau prix et l'apparition d'un second `signalId` après polling sans remplacement de l'ancien. Le gate retourne 439 tests Python, 22 tests composants et 9 tests anti-fuite réussis ; format, conformité provider, contrats et mypy strict sur 306 fichiers sont verts. Les 38 scénarios Playwright passent, dont la preuve enrichie rejouée seule après sa dernière modification.
- **Blocker éventuel :** aucun ; `VAL-009` peut fermer P6 avec le parcours numérique complet jusqu'à l'UI.
- **ADR éventuel :** aucun ; le polling mesuré suffit au besoin actuel et évite une infrastructure streaming sans exigence métier correspondante.
- **Commit/hash :** `1dd4d2b` (`feat(ui): preserve signals across odds refreshes`).

## VAL-009 — Gate P6, signal value complet

- **Statut :** `DONE`
- **Dépendances vérifiées :** `VAL-007` et `VAL-008` sont `DONE` sur la branche autoritative `codex/val-009-p6-value-gate`, reprise depuis `d8b2429`. Le parcours utilise les captures et mappings P5 ainsi que les prédictions pré-match et politiques P6 persistées.
- **Fichiers créés/modifiés :** orchestrateur `python/metiquo/services/value_pipeline.py`, commande `oe value-evaluate`, cibles Make, transaction partagée du repository de signaux et de la fraîcheur, modèle et migration d'audit, guide `docs/value-gate.md`, README et tests PostgreSQL du gate.
- **Migrations :** `20260908_0035` crée `signals.value_evaluations` append-only avec références aux preuves, signal éventuel, grade, motifs, seuils résolus, empreintes et horodatage. Un refus de mapping conserve une évaluation sans fabriquer de signal calculé.
- **Commandes/tests exécutés :** `make test-value` avec PostgreSQL 18 jetable local, `make check` sur la même instance, 11 scénarios Playwright opportunités/détail et inspection de la fiche outsider dans le navigateur en mode mock explicite.
- **Résultat exact :** 56 tests du gate, 449 tests Python globaux, 22 tests composants et 9 tests anti-fuite réussis ; format, lint, conformité provider, contrats et mypy strict sur 309 fichiers passent. Le service recharge les preuves et calcule `VALUE`, `NO_EDGE` ou `BLOCKED` sans grade fourni par l'appelant. Le modèle doit rester champion, les capacités actives, les sources fraîches, le mapping résolu et la capture fiable avec ses deux issues complètes. Le cutoff ne peut dépasser la capture. Les cas stale, suspended, ambigu, incomplet, source périmée, capacité désactivée et orientation inversée sont couverts. Un échec d'insertion d'audit annule aussi le signal. Un replay exact retrouve les mêmes identifiants ; mise à jour et suppression physiques de l'audit sont refusées. L'outsider synthétique coté `8,00`, avec `p=0,40` et `p_low=0,154268`, donne une cote juste `2,50`, une EV `2,20` et une EV prudente `0,234144`, reproduites depuis le signal et visibles via l'API réelle. Cette fixture démontre le calcul, sans constituer un résultat financier réel.
- **Blocker éventuel :** aucun pour P6 ; le parcours game winner limite explicitement la période à la game prédite ou à une série BO1 et refuse l'assimilation d'une probabilité de game à une série BO3. Les grades plus fins nécessiteraient des seuils versionnés supplémentaires. P7 démarre par `PAP-001`.
- **ADR éventuel :** aucun ; l'audit séparé permet de conserver les abstentions précoces tout en respectant les références obligatoires du signal historique.
- **Commit/hash :** `1058559` (`feat(pricing): orchestrate audited value decisions`).

## PAP-001 — Schéma Paper Ledger

- **Statut :** `DONE`
- **Dépendances vérifiées :** `VAL-006`, `FND-004` et le gate de phase `VAL-009` sont `DONE`.
- **Fichiers créés/modifiés :** `paper_models.py`, migration `20260908_0036`, imports Alembic, tests physiques du ledger et attentes de migration, guide `docs/paper-ledger.md`.
- **Migrations :** `signals.paper_bets` conserve une décision par signal avec cote exacte, évaluation P6, prédiction, modèle, politique, règles, montant fictif, devise, acteur et empreintes. `signals.settlements` conserve les révisions de règlement, leurs prédécesseurs, sources et raisons. Les deux tables refusent toute modification et suppression.
- **Commandes/tests exécutés :** cinq tests PostgreSQL ledger/migrations/gate ingestion, puis les deux tests ledger rejoués après ajout du cas de source en quarantaine ; Ruff, mypy strict ciblé, Prettier et CSpell.
- **Résultat exact :** les cinq tests passent, puis les deux tests enrichis passent en 10,70 secondes. L'insertion SQL directe refuse une cote non horodatée, un prix forgé, un montant non fini, une entrée après début et une source de règlement en quarantaine. Le P&L est contrôlé depuis montant et cote observée. Une correction conserve la séquence `pending_review`, perte `−10`, gain corrigé `70` avec acteur et motif ; la perte initiale reste lisible. Le cycle complet upgrade/downgrade/upgrade et le gate ingestion sur une base créée vide passent avec la révision 36.
- **Blocker éventuel :** aucun ; `PAP-002` ajoute le service de création et sa bankroll fictive. Les triggers exigent une source validée pour un règlement définitif ; les plugins des tickets suivants doivent encore interpréter son résultat.
- **ADR éventuel :** aucun ; séparer décision et révisions de règlement préserve l'historique prévu par la SFG.
- **Commit/hash :** `9ce5f3a` (`feat(paper): add immutable ledger schema`).

## PAP-002 — Création contrôlée de paper bets

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-001` et `VAL-005` sont `DONE` ; l'admission actuelle réutilise le parcours `VAL-009` dans la transaction du ledger.
- **Fichiers créés/modifiés :** `python/metiquo/paper/creation.py`, transaction publique du gate value, commande `oe paper-create`, paramètres de bankroll typés et exemple d'environnement, tests PostgreSQL de création/concurrence/CLI, guide ledger.
- **Migrations :** aucune ; les preuves de bankroll et la référence de réévaluation utilisent l'audit JSON immuable de la décision.
- **Commandes/tests exécutés :** 16 tests PostgreSQL création/value, test CLI réel ajouté et rejoué après correction de son import de module, 11 tests de configuration, Ruff et mypy strict ciblés, Prettier et CSpell.
- **Résultat exact :** les 16 tests passent en 62,58 secondes ; le test CLI passe ensuite en 7,52 secondes et les 11 tests de configuration passent. Le service impose un montant explicite, une devise configurée, un signal admis et une nouvelle admission au moment de l'entrée. Un modèle retiré ou une cote stale bloque l'entrée sans écriture partielle. Un replay identique conserve sa réponse initiale ; une clé réutilisée avec un autre payload ou une seconde décision sur le même signal est refusée. Le disponible déduit les mises ouvertes et les positions en revue, puis ajoute une seule fois le dernier règlement. Deux créations concurrentes de `8` avec une limite d'exposition `10` produisent exactement une entrée. Le capital initial ne peut être augmenté par simple changement de configuration après la première entrée. La CLI réelle crée le pari et renvoie un conflit métier structuré en cas de montant modifié.
- **Blocker éventuel :** aucun ; l'auto-paper et Kelly restent désactivés. `PAP-003` peut interpréter les résultats game winner, avant le job et les API réelles des tickets suivants.
- **ADR éventuel :** aucun ; les créations sont manuelles dans ce MVP et ne contactent aucune API d'exécution bookmaker.
- **Commit/hash :** `df09e12` (`feat(paper): create controlled fictitious entries`).

## PAP-003 — Settlement GAME_WINNER

- **Statut :** `DONE`
- **Dépendances vérifiées :** `ML-012`, `PAP-001` et `CNL-002` sont `DONE`.
- **Fichiers créés/modifiés :** moteurs et preuves de règlement `paper/game_settlement.py`, `paper/settlement_rules.py`, fixtures `tests/paper/test_game_settlement.py`, guide ledger.
- **Migrations :** aucune ; le moteur produit une décision immuable destinée au job `PAP-005` et aux révisions du ledger.
- **Commandes/tests exécutés :** 18 nouvelles fixtures de règlement et les cinq tests du plugin game winner via `python -m pytest`, Ruff et mypy strict ciblés, Prettier et CSpell.
- **Résultat exact :** les 23 tests passent en 2,44 secondes. Le gain et la perte respectent l'orientation de sélection. Les neuf combinaisons remake/forfait/annulation et `settle`/`void`/`review` appliquent la politique référencée. Source non validée ou future, game incorrecte, règle inconnue, résultat absent, incomplet ou contradictoire restent `pending_review`. Une même preuve et les mêmes règles donnent exactement la même décision et la même empreinte ; aucun P&L n'est inventé par ce moteur.
- **Blocker éventuel :** aucun ; `PAP-004` ajoute le règlement série, puis `PAP-005` charge les preuves depuis PostgreSQL et persiste les règlements.
- **ADR éventuel :** aucun ; le moteur pur interprète les preuves et le job réalise leurs lectures et leur audit transactionnel.
- **Commit/hash :** `daead10` (`feat(paper): settle game winner with recorded rules`).

## PAP-004 — Settlement SERIES_WINNER

- **Statut :** `DONE`
- **Dépendances vérifiées :** `ML-014`, `PAP-001` et `CNL-003` sont `DONE`.
- **Fichiers créés/modifiés :** `paper/series_settlement.py`, 13 fixtures série et guide ledger.
- **Migrations :** aucune ; les décisions utilisent le même contrat immuable et les mêmes règles référencées que le moteur game winner.
- **Commandes/tests exécutés :** tests paper et pricing série via `python -m pytest`, Ruff, mypy strict ciblé, Prettier et CSpell.
- **Résultat exact :** les 36 tests passent en 1,97 seconde, dont 13 nouveaux scénarios série. Les scores terminaux BO1/BO3/BO5 produisent gain/perte, et le nul BO2 exige une troisième issue déclarée. Le vainqueur doit confirmer le score core. Score incomplet, impossible, vainqueur contradictoire ou non résolu, format changé, série écourtée et source non validée restent en revue. Une annulation sans règle explicite reste en revue ; une politique `void` référencée permet le void. Les replays produisent la même décision.
- **Blocker éventuel :** aucun ; `PAP-005` peut raccorder les moteurs au chargement OE et aux révisions du ledger.
- **ADR éventuel :** aucun ; les formats pairs ont un domaine explicite à trois issues, sans extrapoler une règle de push implicite.
- **Commit/hash :** `dacd4c4` (`feat(paper): settle series from terminal scores`).

## PAP-005 — Job de règlement depuis OE

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-003`, `PAP-004` et `OE-020` sont `DONE`.
- **Fichiers créés/modifiés :** service `paper/settlement_job.py`, preuve d'événement figée à la création, verrou bankroll partagé, configuration délai/reprises, CLI `paper-settle`, cibles Make et cinq tests PostgreSQL d'arrivée/règlement/reprise/CLI.
- **Migrations :** aucune ; les preuves de résultat et les corrections utilisent les révisions append-only de `signals.settlements`.
- **Commandes/tests exécutés :** tests d'arrivée et de création, correction du typage enum au retour du DTO, puis `make test-paper` sur PostgreSQL réel ; Ruff, mypy strict ciblé, Prettier et CSpell.
- **Résultat exact :** les 45 tests paper passent en 42,20 secondes. Le parcours crée une entrée, attend une nouvelle publication raw, exécute le vrai builder canonique, respecte le délai puis règle le BO1 gagné à `70` pour une mise `10` et une cote `8`. Le replay conserve trois révisions au total : attente de résultat, attente de délai, règlement. Une correction OE ne remplace pas ce gain automatiquement ; une action motivée ajoute ensuite la perte `−10` en quatrième révision. La source stale maintient `pending_review`. Une connexion défaillante deux fois reprend au troisième essai ; une panne persistante s'arrête au troisième et apparaît en échec dans le rapport. La CLI traite le pari puis annonce zéro décision à traiter lors du passage suivant. Le statut et le P&L proviennent du résultat OE et du moteur, jamais d'un choix manuel du résultat.
- **Blocker éventuel :** aucun ; l'activation d'un scheduler récurrent appartient à P8. Les anciennes décisions sans preuve d'événement restent en revue. Le parcours réel conserve la restriction P6 au modèle game winner et aux BO1 pour les marchés de série.
- **ADR éventuel :** aucun ; le lot transactionnel et sa CLI sont utilisables avant l'orchestrateur de jobs P8, sans exécution bookmaker.
- **Commit/hash :** `78ab603` (`feat(paper): run audited OE settlement jobs`).

## PAP-006 — Closing line proxy et CLV

- **Statut :** `DONE`
- **Dépendances vérifiées :** `ODD-007` et `PAP-001` sont `DONE` ; la preuve d'horaire immuable ajoutée dans `PAP-005` définit la clôture.
- **Fichiers créés/modifiés :** projection `paper/closing_line.py`, deux scénarios PostgreSQL utilisant la vraie capture d'import manuel, cible `test-paper` et guide de méthode.
- **Migrations :** aucune ; le proxy est une projection déterministe des snapshots append-only et de l'horaire figé du ledger.
- **Commandes/tests exécutés :** deux tests PostgreSQL CLV, Ruff, mypy strict ciblé, Prettier et CSpell.
- **Résultat exact :** les deux tests passent en 7,58 secondes. La capture à `4` trente secondes avant le début produit un CLV de `1` pour une entrée à `8`. Une cote suspendue plus récente, une cote post-start et une cote importée après le début avec timestamp rétroactif sont toutes exclues. Le replay donne la même preuve et ne change pas l'entrée à `8`. Sans observation suffisamment récente, le CLV reste null avec `CLOSING_TOO_OLD` ; avant l'événement il est indisponible avec `EVENT_NOT_STARTED`. La requête groupée conserve les identifiants et empreintes sans reconstruire de prix.
- **Blocker éventuel :** aucun ; `PAP-007` peut agréger le CLV disponible avec son nombre d'observations et exposer séparément les indisponibilités.
- **ADR éventuel :** aucun ; la méthode explicite est un ratio de prix observé, limité à une fenêtre de 90 secondes par défaut, et ne prétend pas être la clôture officielle du bookmaker.
- **Commit/hash :** `6c9894c` (`feat(paper): derive observed closing line proxy`).

## PAP-007 — Métriques financières honnêtes

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-005` et `PAP-006` sont `DONE` ; les décisions, résultats et proxies de clôture proviennent des repositories PostgreSQL.
- **Fichiers créés/modifiés :** moteur `paper/metrics.py`, service `paper/reporting.py`, commande `paper-report`, configuration de clôture, modèle de rapport, guide `docs/paper-financial-metrics.md`, tests de calcul manuel et de rapport réel. Correction transversale de l'identité d'équipe dans le pricing, la projection et la preuve de création paper.
- **Migrations :** `20260908_0037` ajoute les rapports financiers append-only. `20260908_0038` fige `selected_team_id` et exige sa cohérence avec la sélection canonique et la prédiction lors de toute nouvelle publication. Les lignes anciennes restent inchangées et explicitement non vérifiées lorsqu'elles ne disposent pas de cette preuve.
- **Commandes/tests exécutés :** quatre tests de métriques, 26 tests PostgreSQL signal/value/création/règlement/rapport, Ruff et mypy strict ciblés ; contrôle global `make check` avec PostgreSQL 18 réel, incluant migrations, gate ingestion et compatibilité OpenAPI.
- **Résultat exact :** les 26 tests PostgreSQL passent en 78,03 secondes et mypy ciblé passe sur 201 fichiers. Le calcul manuel confirme une perte nette de `10` pour `40` de mises réglées, soit un yield de `−0,25`, un drawdown de `30` et un intervalle par blocs `[-1 ; 0,5]`. La fixture intégrée confirme une perte de `10`, un yield de `−1` et un CLV de `−0,2`, dans les deux orientations possibles des équipes du modèle. Le test a révélé que l'ordre UUID du modèle pouvait différer de l'ordre Blue/Red canonique ; la probabilité et le règlement sont maintenant liés à l'identité d'équipe, avec refus SQL d'une identité forgée et reproduction déterministe. Aucune performance réelle n'est déduite de ces fixtures.
- **Validation globale :** `make check` réussit : 503 tests Python en 215,59 secondes, tests composants, contrôles de format, lint, orthographe, typage et client OpenAPI verts.
- **Blocker éventuel :** aucun ; `PAP-008` complète l'audit des opportunités non prises, mouvements de cote et corrections.
- **ADR éventuel :** aucun ; les agrégats sont matérialisés hors requête web, avec méthode, tailles d'échantillon, motifs d'indisponibilité, preuves et empreintes.
- **Commit/hash :** `824c803` (`feat(paper): report observed financial metrics and bind team identity`).

## PAP-008 — Anti-biais et immutabilité reporting

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-007` est `DONE` avec contrôle global vert ; les politiques et leur audit immuables sont déjà validés par `VAL-003`.
- **Fichiers créés/modifiés :** `paper/reporting_audit.py`, raccord au rapport matérialisé, tests PostgreSQL de complétude/correction/changement de cote, cible `test-paper` et documentation des conventions.
- **Migrations :** aucune ; le rapport stocke son audit et son empreinte dans les documents append-only de la migration 37.
- **Commandes/tests exécutés :** test de complétude d'abord en échec sur l'absence d'audit, puis huit tests rapport/politiques ; après ajout du changement de cote, les deux scénarios d'audit enrichis ; Ruff, mypy strict ciblé, Prettier et CSpell.
- **Résultat exact :** les huit tests passent en 13,15 secondes, puis les deux scénarios enrichis passent en 8,48 secondes ; mypy passe sur dix fichiers. Les signaux pris, non pris, les réévaluations d'entrée et les abstentions précoces sont conservés séparément. Une perte de `10` corrigée en gain de `70` conserve les deux révisions et l'ajustement de `80`, avec auteur, motif, preuves et rapport antérieur inchangé. Une cote passée de `8` à `4` avant l'entrée refuse l'ancien signal et reste dans l'audit avec une variation de `−0,5`, une opportunité non prise, zéro pari et aucun ROI numérique. Le slippage des entrées réussies vaut zéro sous la règle du snapshot exact ; ce fait n'est pas présenté comme une absence de coût d'exécution réelle. La suppression physique des signaux, évaluations, règlements et rapports échoue.
- **Blocker éventuel :** aucun ; `PAP-009` raccorde les API et écrans réels à ces services et projections.
- **ADR éventuel :** aucun ; les seuils restent versionnés hors fenêtre finale et le reporting n'optimise aucune politique.
- **Commit/hash :** `df762fa` (`feat(paper): preserve complete reporting audit`).

## PAP-009 — UI/API paper trading réels

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-008` et `UI-010` sont `DONE`. Le mode réel utilise les services de création/règlement et le rapport matérialisé P7.
- **Fichiers créés/modifiés :** routes `api/paper_routes.py`, repository paginé `postgres_paper.py`, DTO et OpenAPI/client généré, motif de demande dans la preuve de règlement, dashboard, fiche, panneau financier et formulaire de vérification OE ; tests PostgreSQL et Playwright.
- **Migrations :** aucune ; les nouveaux champs DTO de CLV sont des projections des captures existantes. Les rapports et règlements restent append-only.
- **Commandes/tests exécutés :** six tests API réelle/mutations mock, 31 tests API/contrats/OpenAPI après ajout des deux routes au contrat attendu, six tests API/règlement après ajout de l'audit du motif, puis scénario API enrichi avec CLV et comparaison mock/réel ; TypeScript, Ruff, mypy, ESLint, build Next et cinq tests Playwright paper.
- **Résultat exact :** les six tests API/règlement passent en 21,43 secondes, les 31 tests API/contrats en 7,88 secondes, puis le scénario API enrichi passe en 6,08 secondes. Les 22 tests composants et les cinq scénarios Playwright passent, ces derniers en 13,2 secondes. Le serveur crée une décision, retourne `pending_review` sans résultat, refuse un gain fourni, puis règle une perte de `10` depuis OE ; la fiche expose le proxy de clôture observé et le rapport retourne un ROI de `−1` avec `n=1`. Le motif est conservé et les clés des DTO mock/réel sont identiques. Le navigateur montre pertes, CLV, effectifs, rapport complet et vérification OE sans champ de résultat manuel en mode réel. Le bilan utilise le rapport global ; la liste est paginée. Kelly et l'auto-paper restent désactivés.
- **Blocker éventuel :** aucun pour le ticket ; les fixtures Playwright valident le transport et l'UI, tandis que PostgreSQL valide le parcours serveur. Aucune performance financière réelle n'est revendiquée. `PAP-010` doit fermer le gate de phase.
- **ADR éventuel :** aucun ; réutilisation des mêmes DTO et composants avec lecture des agrégats hors requête web.
- **Commit/hash :** `5007a30` (`feat(paper): connect real ledger API and interface`).

## PAP-010 — Gate P7, validation financière après démarrage

- **Statut :** `DONE`
- **Dépendances vérifiées :** `PAP-009` et les tickets `PAP-001` à `PAP-008` sont `DONE`.
- **Fichiers créés/modifiés :** commande `make paper-gate`, script `demo_paper_gate.py`, export contrôlé du rapport de fixture via le test API, vérification d'empreintes du gate, exemple généré et guide `docs/paper-gate.md`.
- **Migrations :** aucune nouvelle ; le gate reconstruit toutes les migrations dans sa propre base vide, ensuite supprimée.
- **Commandes/tests exécutés :** test PostgreSQL du gate, `make paper-gate OUTPUT=docs/examples/paper-gate-fixture.json`, Ruff/mypy et documentation vérifiée ; `make check` de phase, correction contrôlée de la référence mock et nouveau contrôle global complet.
- **Résultat exact :** le test du gate passe en 9,91 secondes. La commande génère le rapport `aa101645-bf6b-547c-b620-7394bd898f10` depuis le parcours réel de services alimenté par fixtures, avec entrée à `8`, clôture à `4`, perte de `10`, audit des captures et vérification des empreintes. La sortie classe explicitement l'exemple `fixture=true` et `financialPerformanceValidated=false`. La commande de règlement, le refus du résultat fourni à la main et la parité DTO sont exercés par le parcours API réutilisé.
- **Validation globale :** 507 tests Python passent en 240,37 secondes, avec 22 tests composants et 9 tests anti-fuite ; format, lint, typage et client OpenAPI sont verts. Le premier contrôle avait isolé une seule référence mock obsolète. Retirer uniquement les deux nouveaux champs CLV du JSON reproduisait exactement son ancienne empreinte ; la référence a donc été actualisée après cette vérification, puis ses 13 tests et le contrôle global complet ont passé. Les cinq parcours navigateur paper validés par `PAP-009` restent la preuve UI de cette phase, sans changement UI dans `PAP-010`.
- **Blocker éventuel :** aucun pour le gate technique P7. La performance financière après collecte effective reste non validée ; les fixtures ne constituent aucun backtest financier réel. Cette réserve n'empêche pas le travail d'exploitation et de sécurité P8.
- **ADR éventuel :** aucun ; le gate réutilise les services et les fixtures prévues, dans une base éphémère et sans bookmaker externe.
- **Commit/hash :** `a89054b` (`test(paper): validate financial gate on empty database`).

## OPS-001 — Table jobs et worker PostgreSQL

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-008`, `FND-004` et le gate P7 sont `DONE`.
- **Fichiers créés/modifiés :** modèle `ops_models.py`, migration 39, file `worker/queue.py`, runner et handlers paper, contexte de job, cycle du worker et point d'entrée réel ; tests PostgreSQL, attentes de migration et guide `docs/worker.md`.
- **Migrations :** `20260908_0039` crée `ops.jobs`, les index de prise/bail et le trigger qui interdit de modifier une requête ou de supprimer l'historique. Les champs de suivi restent modifiables sous contrôle du propriétaire du bail.
- **Commandes/tests exécutés :** tests écrits avant la file, tests PostgreSQL queue/migrations/gate ingestion ; correction de l'attente de schéma vide, puis sept tests queue/migrations/worker ; après ajout du verrou d'exécution, cinq tests queue/worker ; Ruff et mypy strict ciblés.
- **Résultat exact :** les sept tests passent en 7,28 secondes, puis les cinq tests enrichis passent en 4,81 secondes. Deux workers concurrents obtiennent exactement un propriétaire ; un bail expiré est repris avec une nouvelle tentative et un nouveau jeton. L'ancien propriétaire ne peut ni renouveler ni terminer le job. Un handler qui détient encore son verrou empêche la reprise concurrente sans consommer de tentative supplémentaire. Le vrai handler financier publie un rapport et conserve son identifiant ; un type inconnu échoue explicitement. Un job futur attend son horaire. Modifier le payload ou supprimer l'historique échoue en SQL. Les migrations aller/retour et le gate ingestion passent avec le schéma 39.
- **Blocker éventuel :** aucun ; `OPS-002` ajoute les verrous de portée entre jobs différents. Les politiques de reprise et l'annulation contrôlée appartiennent à `OPS-003`, la planification à `OPS-004`.
- **ADR éventuel :** aucun ; file PostgreSQL, baux, verrous et handlers idempotents sans broker externe.
- **Commit/hash :** `bc413bc` (`feat(ops): run jobs through PostgreSQL leases`).

## OPS-002 — Advisory locks et unicité métier

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OPS-001` et `OE-021` sont `DONE`.
- **Fichiers créés/modifiés :** verrous communs `foundation/locks.py`, prise de file et runner, synchronisation OE directe et backfill, entraînement et transitions de modèle ; tests de concurrence, perte de session et modèle.
- **Migrations :** aucune ; advisory locks PostgreSQL partagés avec la clé historique provider/année du backfill.
- **Commandes/tests exécutés :** huit tests PostgreSQL verrous/queue/backfill/gate ingestion ; assertion d'entraînement concurrent d'abord en échec, puis neuf tests verrous/modèles/règlement ; Ruff, mypy ciblé et contrôles documentaires.
- **Résultat exact :** les huit premiers tests passent en 35,71 secondes ; les neuf tests complémentaires passent en 24,80 secondes. Deux jobs d'une même année se sérialisent sans consommer de tentative pour l'attente, tandis qu'une autre année avance. Le timeout est borné, une session propriétaire terminée libère son verrou, la réentrance backfill/sync fonctionne et une exception libère la ressource. Entraînement et promotion partagent la portée `model:lol:game_winner` ; la tentative concurrente échoue sans publication, puis le parcours complet candidat/champion et candidat bloqué réussit. Le règlement conserve ses verrous transactionnels par bankroll et ligne paper, déjà utilisés par les appels directs et les jobs. Ruff et mypy passent sur les fichiers concernés.
- **Blocker éventuel :** aucun ; `OPS-003` ajoute la politique de reprise et l'annulation contrôlée.
- **ADR éventuel :** aucun ; verrous par session pour les traitements longs, transactionnels pour les mutations atomiques, sans service externe.
- **Commit/hash :** `715204e` (`feat(ops): serialize business operations by resource`).

## OPS-003 — Retries, reprise et annulation

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OPS-001` est `DONE` ; les protections de portée `OPS-002` sont validées.
- **Fichiers créés/modifiés :** politique de retry, file, runner et token d'annulation ; points de contrôle du lot paper, commandes `jobs show/cancel/rerun`, modèle de relance et tests PostgreSQL/worker.
- **Migrations :** `20260908_0040` ajoute la référence au job original et le motif de relance, protégés contre les modifications. La relance crée une requête distincte, sans réinitialiser le job terminé.
- **Commandes/tests exécutés :** tests écrits avant la politique ; trois tests worker, dix tests PostgreSQL reprise/queue/verrous/migrations, puis dix tests CLI/reprise/règlement/gate ingestion ; Ruff et mypy ciblés.
- **Résultat exact :** les trois tests worker passent en 0,32 seconde ; les dix tests PostgreSQL initiaux en 12,19 secondes ; les dix tests complémentaires en 52,65 secondes. Une erreur transitoire est planifiée à nouveau avec délais 10 minutes, 30 minutes, 2 heures et jitter déterministe borné ; une entrée invalide reste permanente même si l'appelant autorise une nouvelle tentative. Le maximum d'essais mène à `dead`, une erreur permanente à `failed`. L'annulation fonctionne en attente, pendant un handler, lors de l'arrêt coopératif et après disparition du propriétaire. La course annulation/fin conserve les références déjà publiées sans annoncer un succès. Une relance motivée a un nouvel identifiant, reste idempotente et conserve son parent immuable. Les commandes n'affichent pas le payload privé. Ruff et mypy passent.
- **Blocker éventuel :** aucun ; `OPS-004` raccorde ces mécanismes à la planification des services réels.
- **ADR éventuel :** aucun ; annulation aux frontières atomiques, sans effacer les unités métier déjà commises. Le bail expiré ne permet jamais à un ancien propriétaire de terminer le job.
- **Commit/hash :** `d4960d0` (`feat(ops): bound retries and control job cancellation`).

## OPS-004 — Planification

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OPS-002` et `OPS-003` sont `DONE`.
- **Fichiers créés/modifiés :** scheduler UTC PostgreSQL et boucle indépendante du traitement long, handlers catalogue/sync/audit/contrôle approfondi, configuration et exemple d'environnement, opérations OE partagées, confirmation de contenu inchangé et preuve de fraîcheur ; tests de créneaux, concurrence et parcours réel alimenté par fixture.
- **Migrations :** aucune ; les clés de créneau utilisent la file existante et les confirmations sont liées au run et au snapshot existants.
- **Commandes/tests exécutés :** test de planification d'abord en échec ; 17 tests scheduler/fraîcheur, puis contrôle CLI/gate/configuration ; correction de lecture JSON des délais dans l'exemple d'environnement, 16 tests configuration/worker, 13 tests PostgreSQL sync/reprise/verrous/promotion/règlement, puis huit tests finaux scheduler/sync/gate/worker ; Ruff et mypy ciblés.
- **Résultat exact :** les 17 tests passent en 3,98 secondes ; le contrôle élargi isole la lecture de configuration avec 31 tests réussis et un échec, corrigé ensuite. Les 16 tests passent en 0,55 seconde ; les 13 tests PostgreSQL en 25,23 secondes ; les huit tests finaux en 34,32 secondes. Deux schedulers ne créent qu'un job actif par portée annuelle ; un redémarrage après huit jours ne produit pas les créneaux manqués en rafale. Les valeurs initiales sont 3 heures pour l'année courante, un mois pour catalogue/années closes, un jour pour les sources ayant déjà changé de hash validé, 5 minutes pour règlement et rapport paper. Toutes sont configurables, ainsi que le retry 10 minutes/30 minutes/2 heures avec jitter. La panne du scheduler n'arrête pas le worker. Un checksum fiable inchangé évite le transfert et un nouveau chargement, après vérification locale complète ; le snapshot et son manifeste restent inchangés, la preuve récente est conservée dans le run. Le miroir privé ne confirme pas une fraîcheur distante. Les handlers réels sync/contrôle exécutés avec un transport de fixture conservent les références attendues ; un manifeste altéré est refusé. Le contrôle approfondi vérifie aussi l'empreinte du schéma. Le gate P2 et la CLI OE restent verts.
- **Régression complémentaire :** un test ajouté avant correction révèle qu'une panne de chargement après validation du fichier pouvait laisser le run principal en succès. La clôture de cette tentative est maintenant corrigée en échec ; la fraîcheur reste dégradée. Les deux scénarios sync et le gate ingestion passent ensuite, soit trois tests en 31,41 secondes.
- **Blocker éventuel :** aucun ; les preuves réseau du test utilisent un transport de fixture identifié, sans prétendre à une disponibilité externe mesurée. `OPS-005` centralise l'audit immuable.
- **ADR éventuel :** aucun ; scheduler interne, file PostgreSQL et clés UTC persistées, sans Airflow ni service de messages.
- **Commit/hash :** `473ac8c` (`feat(ops): schedule OE checks and paper jobs`).

## OPS-005 — Audit immuable

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-006` et `OPS-001` sont `DONE`.
- **Fichiers créés/modifiés :** modèle du journal central, migration 41, contexte transactionnel, liaison HTTP/CLI/worker, audit des modes effectifs et guide `docs/operational-audit.md` ; tests d'immutabilité, rollback, confidentialité, trace paper et chaîne de politiques.
- **Migrations :** `20260908_0041` crée `ops.audit_events`, ses index de cible/trace et vingt triggers sur les mutations critiques. UPDATE, DELETE et TRUNCATE du journal sont refusés. Les journaux métier antérieurs sont conservés.
- **Commandes/tests exécutés :** tests d'audit écrits avant le modèle ; deux tests initiaux après correction d'une fixture provider sans date, dix tests audit/migrations/queue/CLI/paper/modèle ; cinq tests audit/paper/gate ingestion ; 29 tests audit/migrations/sync/API/worker ; extension quarantaine/backfill/politiques, correction du rollback de la migration encore en développement et six tests finaux ; Ruff et mypy ciblés.
- **Résultat exact :** les deux tests initiaux passent en 2,42 secondes ; les dix tests en 17,72 secondes ; les cinq tests en 38,96 secondes ; les 29 tests en 14,02 secondes ; les six derniers en 35,99 secondes. Un changement et son audit sont atomiques, y compris lors d'un rollback. Acteur et trace restent liés à la requête ; la création paper vérifie la correspondance avec `X-Trace-Id`. Les payloads privés et l'URL de base ne sont pas copiés. Les heartbeats inchangés n'encombrent pas le journal. La chaîne de seuils conserve la référence de politique précédente et son auteur. Les changements de configuration conservent avant/après sans doublonner un état identique. Le gate ingestion passe avec les triggers sur source, quarantaine et backfill. Les migrations et les contrôles statiques sont verts.
- **Blocker éventuel :** aucun ; `OPS-006` unifie la lecture du nouveau journal avec les projections admin. Les opérations de sessions Owner seront raccordées à l'audit lors de `SEC-002` ; l'état d'authentification actuel et les mutations locales sont déjà tracés.
- **ADR éventuel :** aucun ; audit dans la transaction SQL pour couvrir les appels directs, avec contexte explicite et références sélectionnées. Les journaux détaillés restent la source des preuves métier.
- **Commit/hash :** `f622671` (`feat(ops): audit critical mutations transactionally`).

## OPS-006 — System status et observabilité

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OE-020`, `ODD-009`, `ML-011` et `OPS-001` sont `DONE`.
- **Fichiers créés/modifiés :** service et DTO de supervision, métriques HTTP, logs JSON API/worker/ingestion/pricing, projections SQL paginées jobs/audit, fraîcheur admin, panneau opérationnel, contrats générés et guide `docs/observability.md` ; tests unitaires, PostgreSQL et navigateur.
- **Migrations :** aucune ; les mesures lisent les preuves existantes sans réécrire l'historique.
- **Commandes/tests exécutés :** tests de masquage, compteurs et statut écrits avant raccordement ; cinq tests PostgreSQL supervision/sync/admin en 13,13 secondes ; neuf tests traces/modèle/file avec trois échecs ensuite corrigés ; cinq tests finaux sync/supervision/audit/modèle ; 63 tests API/contrats/configuration/mock/worker ; 22 tests composants ; quatre tests Playwright admin avec build Next ; Ruff, mypy et TypeScript, puis correction et contrôle ESLint.
- **Résultat exact :** les cinq tests PostgreSQL finaux passent en 16,50 secondes ; les 63 tests passent en 13,14 secondes ; les 22 composants et quatre parcours navigateur passent, ces derniers en 36 secondes avec démarrage des serveurs. Une panne OE conserve la lecture du snapshot validé et dégrade la source ; une confirmation future est refusée. Une confirmation de hash inchangé actualise aussi la santé admin et devient stale hors SLA. La durée mesurée du job de fixture est de deux secondes. Les audits centraux et anciens restent lisibles avec pagination, références et trace, sans payload privé. Le contrôle élargi a révélé l'ancienne attente limitée aux audits de modèles, maintenant adaptée à leur inclusion dans le journal central. Les traces de calcul portent snapshot, modèle et durée. Les contrats OpenAPI sont régénérés ; les douze scénarios mock conservent leur empreinte existante. La capture navigateur du panneau a été inspectée sans débordement.
- **Blocker éventuel :** aucun ; les sauvegardes sont honnêtement `not_configured` et seront raccordées à leurs preuves par `OPS-008`. Les compteurs API sont limités au processus courant ; les autres agrégats concernent l'historique conservé. Le gate P8 vérifiera la supervision complète après les sauvegardes et la sécurité.
- **ADR éventuel :** aucun ; journaux JSON corrélés et agrégats SQL, sans SaaS obligatoire. Les logs de calcul ne prétendent pas remplacer l'audit de commit.
- **Commit/hash :** `d20bef1` (`feat(ops): expose measured operational health`).

## OPS-007 — Alertes

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OPS-006` est `DONE`.
- **Fichiers créés/modifiés :** règles et moniteur d'alertes, état PostgreSQL, scheduler et handler réel, configuration et transmission Compose des paramètres worker/supervision ; tests unitaires, migrations et parcours worker/audit/qualité, guide d'observabilité.
- **Migrations :** `20260908_0042` crée les états de déduplication avec horodatages cohérents. Les notifications utilisent le journal central append-only existant, dans la même transaction que leur état.
- **Commandes/tests exécutés :** règles écrites avant leur implémentation ; dix tests règles/worker/planification/migrations, puis quinze tests alertes réelles/lecture admin/gate ingestion/configuration ; Ruff, mypy, validation Compose et contrôles documentaires.
- **Résultat exact :** les dix premiers tests passent en 9,47 secondes et les quinze tests complémentaires en 51,67 secondes. Deux contrôles concurrents d'une base vide produisent trois apparitions, aucune répétition au redémarrage, trois rappels après six heures, puis trois résolutions uniques. Une horloge ancienne ne rouvre pas l'incident. Le vrai handler conserve quatre identifiants d'alerte avec la trace et l'acteur du job ; une confirmation valide postérieure résout la qualité bloquante sans supprimer son anomalie historique. L'audit admin affiche cet événement. Le scheduler ajoute un seul job d'alertes actif ; migrations aller/retour, gate ingestion, configuration et contrôles statiques passent.
- **Blocker éventuel :** aucun ; les sauvegardes non configurées déclenchent une alerte explicite en attendant `OPS-008`. La fréquence de contrôle est de cinq minutes, le seuil mapping de dix et le rappel de six heures, tous configurables. Les notifications restent locales ; l'exécution dépend du worker.
- **ADR éventuel :** aucun ; déduplication SQL persistée, résolutions et réapparitions explicites, sans dépendance SaaS.
- **Commit/hash :** `e6402d3` (`feat(ops): persist deduplicated local alerts`).

## OPS-008 — Sauvegardes

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-005`, `OE-002` et `ML-010` sont `DONE`.
- **Fichiers créés/modifiés :** service de sauvegarde, dépôt de blobs partagés, export PostgreSQL et chiffrement age, supervision, CLI `oe backup`, cible Make, scheduler et handler ; configuration, image Python et volumes Compose, contrats générés, tests et guide `docs/backups.md`.
- **Migrations :** `20260908_0043` crée les preuves de sauvegarde et leur audit central. Une preuve terminée est immuable ; seule sa disponibilité peut être retirée par rétention. L'historique ne peut être supprimé.
- **Commandes/tests exécutés :** tests de mode et d'interruption d'abord en échec, puis corrections ; 30 tests sauvegardes/alertes/supervision/scheduler/migrations/worker/configuration/Compose ; trois tests de sauvegarde étendus à la rétention interrompue et à son audit ; construction de l'image `metiquo-ops008:local` et test CLI en conteneur ; Ruff, mypy, TypeScript et contrôles documentaires.
- **Résultat exact :** les 30 tests passent en 31,23 secondes. Les trois tests étendus passent ; le premier essai du test d'image échoue sur sa configuration d'environnement, ensuite corrigée. Le test final en conteneur passe en 13,89 secondes : deux vraies commandes exécutées en utilisateur non privilégié, racine en lecture seule et volumes séparés produisent un dump et un index, sans recopier les blobs au second passage. Les sauvegardes en clair et chiffrées utilisent un vrai PostgreSQL 18 et age ; le déchiffrement restitue le dump custom. Les fichiers manquants ou corrompus sont refusés et visibles dans la supervision. Une tentative interrompue devient un échec historique, sans empêcher le succès suivant. La rétention conserve deux preuves dans le test, journalise un échec de suppression simulé et le reprend au passage suivant. Le mode mock est refusé avant SQL, le stockage externe non chiffré et les chemins imbriqués sont refusés, l'annulation conserve son état. Ruff et mypy passent sur 378 sources ; les contrats générés et TypeScript sont valides.
- **Blocker éventuel :** aucun pour le backend filesystem du MVP. L'objet modèle de ce smoke test est une fixture, sans prétention d'entraînement réel ni de performance financière. La restauration et la reconstruction canonique sont la prochaine étape `OPS-009`. Une erreur de rétention laisse la nouvelle sauvegarde valide et produit un avertissement audité ; les limites concernant les fichiers orphelins sont documentées.
- **ADR éventuel :** aucun ; vue PostgreSQL exportée pour cohérence DB/références, objets immuables partagés et vérifiés, clé publique seule dans le worker, clé privée séparée pour la restauration. Le volume de quarantaine est maintenant explicitement persistant dans Compose.
- **Commit/hash :** `a44e511` (`feat(ops): back up database and immutable objects`).

## OPS-009 — Restauration et reconstruction

- **Statut :** `DONE`
- **Dépendances vérifiées :** `OPS-008` et `OE-025` sont `DONE`.
- **Fichiers créés/modifiés :** service et commande `oe restore`, client `pg_restore`, transmission de l'empreinte d'index par CLI/worker, récupération de projection raw manquante et reconstruction core ; tests PostgreSQL et conteneur, guide `docs/restore.md`, workflow de restauration périodique.
- **Migrations :** aucune ; la restauration conserve la révision et les preuves du dump, puis ajoute un événement d'audit dans la copie.
- **Commandes/tests exécutés :** test des frontières d'abord en échec faute de service ; exercices PostgreSQL en clair/chiffré, qui révèlent ensuite un défaut de reconstruction ; correction sous verrou de chargement ; six tests restauration/CLI/chargement raw ; douze tests restauration/sauvegardes/gate ingestion/games/frontières ; construction de l'image `metiquo-ops009:local`, puis douze tests commande en conteneur/configuration ; Ruff, mypy et vérifications documentaires.
- **Résultat exact :** les six tests passent en 44,67 secondes, les douze tests élargis en 82,06 secondes, et les douze tests conteneur/configuration en 18,75 secondes. Les vrais dumps sont restaurés avec PostgreSQL 18 en transaction unique. Mauvaise empreinte, mauvais destinataire privé et blob corrompu sont refusés avant création de base. Une base existante ou un dossier existant n'est pas remplacé. La reconstruction depuis les fichiers raw rétablit douze clés et empreintes, conserve les douze révisions historiques et matérialise la game ; la base source reste identique. Le défaut initial provenait d'une tentative de recréer la révision 1 après perte de projection : la dernière révision est maintenant reprise avant rejeu, dans la même transaction. Le test d'image exécute deux sauvegardes puis une restauration réelle avec racine readonly et volumes séparés ; toutes ses bases éphémères sont supprimées. Mypy passe sur 382 sources ; Ruff, format et orthographe sont verts.
- **Blocker éventuel :** aucun pour l'exercice technique du MVP. La preuve porte sur les fixtures identifiées, dont un objet modèle, et ne prétend pas valider une installation privée ou la performance d'un modèle. Le workflow hebdomadaire est écrit mais ne s'exécutera qu'après publication sur la branche par défaut ; aucune exécution distante n'est inventée. Un échec après création SQL conserve la cible de test pour diagnostic, sans la déclarer valide.
- **ADR éventuel :** aucun ; nouvelles cibles obligatoires, empreinte conservée séparément, chiffrement vérifié avant SQL et base de test uniquement. `SEC-001` à `SEC-005` précèdent maintenant `OPS-010`, conformément aux dépendances du gate P8.
- **Commit/hash :** `3c638af` (`feat(ops): restore verified backups into isolated test targets`).

## SEC-001 — Garde AUTH_MODE

- **Statut :** `DONE`
- **Dépendances vérifiées :** `FND-003` et `FND-007` sont `DONE`.
- **Fichiers créés/modifiés :** mode d'authentification typé, frontière de publication et d'origine navigateur, liste explicite de CIDR privés, validation de fabrique API ; configuration Compose et exemple d'environnement, tests de configuration/démarrage/ports et guide `docs/security.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** douze tests de frontières écrits avant implémentation ; 32 tests initiaux ; ajout du vrai refus de démarrage serveur et du contrôle de correspondance des ports Compose ; 50 tests API/worker/configuration/Compose, puis 34 tests finaux après corrections de typage ; Ruff, mypy, format et contrôles documentaires.
- **Résultat exact :** les 32 tests initiaux passent en 6,03 secondes, les 50 tests élargis en 14,01 secondes et les 34 tests finaux en 9,67 secondes. Une adresse publique, une interface générique ou une origine navigateur externe sans authentification bloque le démarrage. Les plages privées ne sont acceptées qu'après déclaration explicite et les plages globales/réservées sont refusées. IPv4 et IPv6 loopback passent. La fabrique réévalue les paramètres injectés ; la configuration invalide fait sortir le vrai serveur avant son démarrage. Compose publie API, web et gateway sur la même adresse que celle transmise au garde. Ruff et mypy passent sur 384 sources ; le mode mock local reste utilisable.
- **Blocker éventuel :** aucun ; `SEC-002` implémente maintenant les sessions Owner. Jusqu'à ce raccordement, `AUTH_MODE=owner` refuse le démarrage API avec `AUTH_OWNER_UNAVAILABLE`, sans laisser croire qu'une authentification absente protège les routes. Les redirections externes et tunnels doivent être déclarés conformément à leur exposition réelle.
- **ADR éventuel :** aucun ; absence de confiance implicite aux noms DNS privés ou au mode développement. Les ports Docker internes sont distingués de leur publication sur l'hôte.
- **Commit/hash :** `000bfd2` (`feat(security): refuse unauthenticated public exposure`).

## SEC-002 — Compte Owner et sessions

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `SEC-001` et `FND-004` sont `DONE`.
- **Fichiers créés/modifiés :** service Owner, contrats et routes de connexion, middleware API, bootstrap/réinitialisation CLI, écran de connexion et proxy Next, configuration Compose, documentation sécurité et tests PostgreSQL/navigateur. Les mutations réelles utilisent l'identité Owner authentifiée dans l'audit.
- **Migrations :** `20260908_0044` crée le compte unique et les sessions dans `ops`, avec empreintes privées exclues de l'audit, identité immuable et interdiction de réactiver/supprimer l'historique révoqué.
- **Commandes/tests exécutés :** tests d'intégration écrits avant le service ; corrections du trigger de révision et de la réponse Problem Details ; exercice CLI/Chromium via `RUN_OWNER_BROWSER=1` ; tests sessions/API/migrations/configuration/Compose ; régressions administration/paper et gate ingestion ; Playwright administration/navigation ; Ruff, mypy, TypeScript strict, ESLint, contrats OpenAPI, format et orthographe.
- **Résultat exact :** l'exercice Owner passe en 24,03 secondes et les dix parcours mock administration/navigation en 24,0 secondes. La série finale de huit tests PostgreSQL/API/gate passe en 66,31 secondes ; les migrations/configuration/Compose passent dans la série préalable (22 succès, un test ensuite corrigé car il cherchait `id` au lieu du contrat `aliasId`). Deux requêtes concurrentes produisent une seule rotation. L'expiration absolue reste identique malgré quatre rotations actives. Réinitialisation, déconnexion et expiration invalident les sessions ; l'ancien cookie ne reste utilisable que dans la grâce bornée. L'API refuse les lectures privées sans session. Le navigateur ne peut lire le cookie HTTP-only ; HTTPS impose Secure et le préfixe `__Host-`. Le mot de passe de fixture et les tokens ne sont ni stockés en clair ni inscrits dans l'audit. Le test de mutation réelle conserve `owner:<uuid>` malgré un reviewer fourni par le client. Mypy passe sur 393 sources ; types frontend et lint passent ; la régénération des contrats est stable une fois les nouveaux contrats indexés.
- **Blocker éventuel :** aucun ; les comptes créés sont des fixtures de test, aucun identifiant personnel n'est inventé. `SEC-003` ajoute les protections HTTP avant l'exposition de production.
- **ADR éventuel :** bibliothèque maintenue `argon2-cffi==25.1.0` avec Argon2id ; session opaque aléatoire de 256 bits, SHA-256 seul en base, durée inactive 30 minutes, absolue 12 heures, rotation 15 minutes et grâce 10 secondes. Le mot de passe est saisi sans écho ou lu depuis un fichier serveur protégé.
- **Commit/hash :** `c0c42d8` (`feat(security): implement Owner login and rotating sessions`).

## SEC-003 — Protection HTTP

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `SEC-002` est `DONE`.
- **Fichiers créés/modifiés :** protection ASGI, limiteur partagé, proxy Next avec nonce CSP et borne des corps, transmission explicite CSRF dans les mutations, documentation des origines et tests HTTP/Chromium. L'inventaire OpenAPI inclut les trois routes Owner introduites par SEC-002.
- **Migrations :** `20260908_0045` crée trois compteurs au maximum dans `ops.http_rate_limits`, indépendants de l'IP et du nom fourni, réutilisés entre instances et redémarrages.
- **Commandes/tests exécutés :** preuve d'abord en échec faute de limiteur ; six tests PostgreSQL/API/migrations ; parcours Owner avec PostgreSQL et Chromium ; onze tests navigateur CSP/navigation/admin ; test final CSP enrichi du thème et des corps excessifs ; 45 tests élargis HTTP/API/migrations/gate ingestion/Compose/configuration/OpenAPI ; 22 tests composants ; Ruff, mypy, TypeScript strict, ESLint, format, orthographe et `make openapi-check`.
- **Résultat exact :** les six premiers tests passent en 13,72 secondes. Les onze tests navigateur passent en 52,7 secondes ; le parcours CSP final passe en 15,3 secondes, sans erreur console/hydratation. Les 45 tests élargis passent en 70,36 secondes et les 22 composants passent. Le contrôle d'origine refuse absent/null/étranger en mode Owner et les mutations sans en-tête CSRF ; CORS reste fermé et une déconnexion forgée ne détruit pas la session. Douze tentatives concurrentes sur deux limiteurs ne laissent passer que cinq connexions ; une nouvelle instance conserve le budget consommé. Les réponses 429 portent Retry-After. Des corps excessifs, y compris transmis par morceaux, sont refusés avant parsing. Une exception contenant un secret de fixture produit uniquement un problème générique. Les scripts inline reçoivent tous le nonce du rendu ; un nonce client est remplacé, la page suivante reçoit un nonce différent, le thème/navigation/mutation autorisée fonctionnent. Les contrats restent stables, mypy passe sur 397 sources, et les refus précoces sont intégrés aux compteurs HTTP.
- **Blocker éventuel :** aucun. Les fenêtres de limitation sont fixes en UTC (5/minute et 20/quart d'heure pour login, 60/minute pour les autres mutations). En mode disabled local, les appels serveur sans métadonnées navigateur restent possibles et les compteurs sont en mémoire ; la protection Owner persiste ses compteurs en base.
- **ADR éventuel :** approche CSRF AJAX par en-tête obligatoire, origine exacte et CORS fermé, suivant OWASP ; CSP de scripts avec nonce dynamique et strict-dynamic suivant Next.js, styles inline conservés pour le thème et les composants. Documentation API en JSON, sans page interactive dépendante d'un CDN. HTTPS ajoute HSTS ; les secrets/permissions de déploiement sont traités par SEC-004.
- **Commit/hash :** `417bcab` (`feat(security): enforce HTTP request and browser protections`).

## SEC-004 — Secrets et conteneurs

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `FND-005`, `OE-006` et `ODD-005` sont `DONE` ; le parcours Owner protégé de `SEC-003` est disponible.
- **Fichiers créés/modifiés :** chargement de fichiers secrets dans Settings, surcharge Compose de production, exclusions du contexte Docker et des journaux, scanner Gitleaks et cible Make, documentation et tests de configuration, conteneurs, PostgreSQL, bundle public et contrôle positif du scanner.
- **Migrations :** aucune. Les mots de passe et règles SCRAM initdb concernent une nouvelle base ; une base déjà initialisée exige une migration opérateur contrôlée, documentée sans suppression de données.
- **Commandes/tests exécutés :** tests de fichiers secrets d'abord en échec ; build des images `metiquo-sec004:local` et `metiquo-sec004-web:local` ; test de l'UID et des permissions réelles ; démarrage et suppression d'une stack PostgreSQL UUID propre ; build Next avec deux secrets sentinelles ; Gitleaks 8.30.1 sur sources et 269 commits locaux ; injection d'une clé synthétique détectée ; 25 tests finaux secrets/conteneurs/Compose/configuration/logs ; Ruff, mypy, Prettier et orthographe.
- **Résultat exact :** les huit tests incluant le build Next passent en 10,02 secondes ; l'exercice PostgreSQL/scanner passe avec quatre tests en 12,29 secondes ; la série finale de 25 tests passe en 13,64 secondes. API/worker lisent le fichier secret avec UID 10001, sans capacité Linux, sous no-new-privileges ; app/raw/secret restent readonly et tmpfs est inscriptible. Le web utilise UID 1000 et ne reçoit aucun credential backend. PostgreSQL démarre non-root avec la surcharge de production, refuse TCP sans mot de passe et accepte le secret monté. Tous les volumes UUID de ces exercices sont supprimés. Le bundle réel et les logs ne contiennent aucun des deux secrets serveur sentinelles. Gitleaks ne trouve aucune fuite sur les 613 sources présentes ni l'historique local après examen de deux faux positifs, exclusivement des UUID de fixture à valeur et chemin exacts. Le contrôle positif retourne bien un échec et son rapport masque intégralement la clé synthétique. Mypy passe sur 402 sources ; lint, format et orthographe passent.
- **Blocker éventuel :** aucun pour le mécanisme livré. Aucun secret personnel ni déploiement existant n'a été modifié. Les fichiers secrets de production restent à fournir par l'opérateur ; le test utilise uniquement des valeurs synthétiques et une base neuve. Compose monte des fichiers et ne chiffre pas leur stockage hôte. Les sauvegardes externes privées sont chiffrées par le mécanisme OPS-008.
- **ADR éventuel :** variables de chemins `DATABASE_URL_FILE`/`OE_GOOGLE_DRIVE_BEARER_FILE`, fichiers bornés et variables directes mutuellement exclusives ; aucun secret transmis au web/gateway ; seule la publication du gateway subsiste en production. Scanner officiel Gitleaks 8.30.1, archive Windows vérifiée par SHA-256 `d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e`. SEC-005 rend son installation et les scans de dépendances/images reproductibles en CI.
- **Commit/hash :** `f18c283` (`feat(security): isolate server secrets and harden production containers`).

## SEC-005 — Scans CI sécurité

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `FND-010` et `SEC-004` sont `DONE`.
- **Fichiers créés/modifiés :** installateur vérifiant les archives officielles, adaptateurs stricts des rapports, politique sans exception, orchestrateur `make scan-security`, job CI bloquant avec conservation des preuves, verrous Python/frontend et Go du gateway, images Python/web/PostgreSQL/Caddy corrigées, tests de politique et de TLS réel, `docs/security-scans.md`.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** test initial en échec faute de module de politique ; audits pip-audit/pnpm/Trivy/Gitleaks réels ; reconstruction des quatre familles d'images puis `make docker-build` ; `make scan-security` ; 16 tests de sauvegarde/restauration/conteneurs/politique ; 14 tests finaux de politique/Compose/conteneurs et TLS vérifié ; Ruff, mypy, Prettier, orthographe, génération des contrats inchangée après correction du verrou frontend.
- **Résultat exact :** les 16 tests passent en 52,85 secondes et les 14 tests finaux en 23,57 secondes. Le gate complet passe dans `data/security/20260907T110342Z-c375607f/summary.json`, avec 626 sources, aucune fuite dans les fichiers ou l'historique et aucune vulnérabilité bloquante. La base Trivy est datée du 7 septembre 2026 ; les rapports portent les identifiants SHA des cinq services (API et worker partagent le runtime). Aucune exception n'est utilisée. Les 360 occurrences non bloquantes restent dans les rapports : 92 élevées sans version corrigée, 101 moyennes, 154 faibles et 13 de sévérité inconnue, avec doublons entre services. Les tests refusent réellement une alerte critique avec le code 1 et un rapport absent avec le code 2, une base périmée/future et une exception expirée ou hors version. La sauvegarde et la restauration exécutent les outils PostgreSQL natifs dans le runtime readonly. Le gateway recompilé sert le web et l'API via TLS dont le certificat local est vérifié. Tous les conteneurs et réseaux UUID de ces exercices sont supprimés. Mypy passe sur 407 sources ; format, lint ciblé et orthographe passent.
- **Blocker éventuel :** aucun pour le mécanisme livré. La CI distante n'a pas encore exécuté ce commit local et la protection de branche reste à vérifier au gate de release QA-005. Les alertes non bloquantes ne sont pas assimilées à une absence totale de vulnérabilités. Le profil MinIO optionnel doit être ajouté au périmètre de scan avant toute activation hors MVP filesystem.
- **ADR éventuel :** criticité, preuves et expiration des exceptions sont décrites dans `docs/security-scans.md`. `js-yaml` 4.3.1 corrige les deux avis détectés sans changer les contrats. Les composants inutilisés vulnérables sont retirés des runtimes ; les outils PostgreSQL restent identifiés par leurs packages. Caddy conserve sa version 2.11.4 mais verrouille les correctifs transitifs et Go 1.26.6. Aucun contournement du scanner ni acceptation de risque n'a été ajouté pour obtenir le passage.
- **Commit/hash :** `f9039d8` (`feat(security): enforce audited dependencies and container release policy`).

## OPS-010 — Gate P8 : exploitation fiable

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `OPS-009`, `SEC-005` et `OPS-007` sont `DONE`.
- **Fichiers créés/modifiés :** synchronisation manuelle en file depuis l'API, reçu HTTP 202 additif et suivi du job dans l'interface, clé conservée lors d'une réponse réseau perdue, réseau sortant et volume de travail du worker, annulation coopérative du streaming/validation/staging et des outils de backup, identité distincte des tentatives de sync, contrôle des résolutions d'alertes, exercice de migration sur copie restaurée, arrêt des pools API, runbook et configuration TLS persistante. Les logs métier survivent à Alembic et l'audit central conserve aussi l'impact des décisions de mapping.
- **Migrations :** aucune nouvelle migration ; l'exercice migre une copie N-1 vers la tête courante.
- **Commandes/tests exécutés :** tests d'abord en échec pour le téléchargement dans l'API, le dossier temporaire readonly, la reprise automatique après échec, la résolution prématurée d'une alerte par relecture d'ancien raw, l'annulation du flux et le module de migration absent. Puis tests API/PostgreSQL, transport, reprise, alertes, backup/restauration, SIGTERM dans le conteneur, TLS vérifié, Playwright complet, `make docker-build`, `make scan-security` et `make check` avec PostgreSQL et toutes les images de test. La première suite complète révèle trois régressions : attentes anciennes de fraîcheur/identité et loggers désactivés par Alembic ; les corrections et l'impact d'audit sont vérifiés avant la relance complète.
- **Résultat exact :** `make check` sort avec le code 0 : 584 tests Python passent en 593,27 secondes, neuf tests anti-fuite et 22 composants passent, mypy valide 415 sources, TypeScript/lint/format/orthographe et contrats OpenAPI passent. Deux exercices optionnels sont explicitement exclus de cette invocation (Owner navigateur et sentinelles du bundle), déjà prouvés dans SEC-002/SEC-004. Les 43 parcours Playwright passent en 1,3 minute, avec un parcours Owner réservé à son exercice séparé. Les dix tests backup/restauration/migration passent en 37,62 secondes et les sept contrôles des conteneurs en 50,19 secondes : écriture du worker sous racine readonly, restauration réelle, TLS vérifié et arrêt SIGTERM avec sortie 0 sans arrêt forcé. La copie N-1 contenant un snapshot est migrée vers la tête, avec références intactes et source inchangée. Le scan final `data/security/20260907T120447Z-f712b31a/summary.json` passe : 635 fichiers, aucune fuite ni vulnérabilité bloquante, aucune exception ; 360 occurrences non bloquantes restent signalées. Les journaux locaux de validation sont `data/security/ops-final-check.log`, `ops-e2e.log` et `ops-security-gate.log`.
- **Blocker éventuel :** aucun pour le gate d'exploitation local documenté. La CI distante, la performance, les parcours réels restants et la recette exhaustive sont traités par QA-001 à QA-007 ; le MVP complet n'est pas encore déclaré terminé. Aucune source/cote financière supplémentaire n'est inventée.
- **ADR éventuel :** l'API conserve le contrat 200 des résultats historiques et ajoute un reçu 202 pour les nouveaux jobs réels. Les écritures de fichiers restent au worker. Chaque tentative possède son run immuable ; les relances ne réutilisent plus une clé raw déjà consommée par un échec.
- **Commit/hash :** `a752e43` (`feat(ops): complete queued ingestion and operational recovery gate`).

## QA-001 — Performance API et N+1

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `VAL-007`, `PAP-009` et `OPS-006` sont `DONE` ; gate P8 `a752e43` validé.
- **Fichiers créés/modifiés :** projection SQL des événements jointe aux signaux, santé des providers groupée, pagination SQL des collections réelles et historiques, chargement borné des candidats de mapping, empreintes de schéma calculées par fenêtre SQL, filtre des backtests sans période représentable, benchmark reproductible et `docs/performance.md` avec mesures et plans archivés.
- **Migrations :** aucune ; les plans observés utilisent les index existants et leurs coûts restent sous la cible sur le scénario documenté.
- **Commandes/tests exécutés :** diagnostic sur base UUID neuve puis supprimée, comparaison des projections avec les lectures antérieures, trois tests initialement en échec (N+1 providers/signaux et pagination), test en échec d'une période de modèle réduite à un instant ; suites ciblées PostgreSQL/API, `make lint typecheck openapi-check`, benchmark réel ASGI/PostgreSQL avec 100 mesures après cinq échauffements par route et plans EXPLAIN après les mesures.
- **Résultat exact :** les six premiers tests passent en 20,99 secondes, les dix tests HTTP/registre/paper en 46,11 secondes, les cinq tests performance/backtest en 17,45 secondes et les 22 tests finaux incluant publication, value et workflow modèle en 104,40 secondes. Les types Python passent sur 419 sources, les types frontend et lint/format/orthographe passent, OpenAPI reste inchangé. Le benchmark `data/performance/20260907T123917Z-242530ec/report.json` passe sans charge de tests/build concurrente : douze routes, toutes les réponses 200, p95 maximal 126,74 ms pour la page des opportunités. La base contient 1 002 séries, 1 001 modèles, 1 100 signaux, 100 paper bets, 1 002 runs, 1 000 anomalies, 1 001 jobs et 150 providers synthétiques. Le nombre de requêtes reste constant lorsque les providers ou signaux augmentent ; la page SQL ne construit que ses 20 DTO et conserve son total au-delà du dernier offset. Les preuves sont archivées dans `docs/evidence/qa-001/`. Le plan SQL le plus lent prend 27,14 ms ; aucune nouvelle migration n'est nécessaire pour ce scénario. La base et les objets temporaires du benchmark ont été supprimés.
- **Blocker éventuel :** aucun.
- **ADR éventuel :** filtrage et pagination avant DTO, sans cache de fraîcheur ; les cotes les plus récentes ouvrent l'historique et le graphe ordonne sa tranche par date. Les résultats de capacité ne constituent pas une validation statistique ou financière et ne couvrent pas le rendu navigateur ou un réseau externe.
- **Commit/hash :** `f70b46e` (`perf(api): bound historical reads and remove per-row queries`).

## QA-002 — Stabilité visuelle et régression

- **Statut :** `DONE`.
- **Dépendances vérifiées :** `UI-011` et `VAL-008` sont `DONE` ; QA-001 est figé dans `f70b46e`.
- **Fichiers créés/modifiés :** dimensions conservées par le composant commun de chargement, catalogue responsive, grilles et métadonnées stables des cartes opérationnelles/financières, suite Playwright retardée et contrôles de thèmes/mouvement/graphe, huit références d'images Windows/Linux, contrôle TypeScript des tests navigateur, `docs/visual-stability.md` et rapport avec empreintes des preuves.
- **Migrations :** aucune.
- **Commandes/tests exécutés :** 24 tests initiaux avec cinq échecs de dimensions/CLS ; test composant en échec confirmant la disparition du conteneur dimensionné ; corrections puis 31 contrôles visuels/accessibilité ciblés ; extension au graphe lors du retour réseau ; suite Playwright complète, génération et inspection des captures puis comparaisons sans mise à jour sous Windows et dans le navigateur Linux officiel ; composants, ESLint, TypeScript strict et formats. Le nouveau contrôle des types détecte aussi une option de capture ignorée et une ancienne erreur de typage des messages de console ; les deux sont corrigées et les captures vérifiées de nouveau.
- **Résultat exact :** 70 tests complets Windows passent en 111,18 secondes ; un parcours Owner reste réservé à son exercice PostgreSQL. Les comparaisons finales passent avec 27 tests Windows en 61,82 secondes et 33 tests Linux en 83,33 secondes, sans échec ni nouvelle tentative. Les 23 tests composants passent. Le CLS maximal vaut 0,023898 sur les deux navigateurs, sous le seuil de 0,05. Les panneaux opérationnels conservent exactement 514/1 182 pixels de hauteur et les panneaux financiers 808/2 852 pixels sur desktop/mobile. Aucun avertissement, erreur de console/hydratation ou débordement global n'est observé sur les parcours instrumentés. Les graphes restent montés pendant l'actualisation, les thèmes sauvegardés sont présents dès les images peintes et le changement de préférence annule l'animation des squelettes. ESLint et types frontend/navigateur passent. Les résultats et empreintes sont archivés dans `docs/evidence/qa-002/report.json` ; les trois références Linux préexistantes restent strictement identiques.
- **Blocker éventuel :** aucun pour ce scénario. Le navigateur Linux teste le même build Next/API local ; le build serveur Linux et la CI distante restent des vérifications de release. Les contrats réels synthétiques ne sont aucune preuve financière. L'exercice Owner et les fautes réseau complètes restent traités dans leurs gates dédiés.
- **ADR éventuel :** mêmes conteneurs et emplacements avant/après chargement ; absence de mesure affichée explicitement. Les captures de panneaux excluent le chrome fixe du shell uniquement pendant la capture ; les mesures utilisent la page intacte. La suite TypeScript couvre désormais aussi les sources Playwright.
- **Commit/hash :** commit dédié `fix(ui): preserve loading geometry and verify visual stability` ; hash ajouté au ticket suivant.
