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
- **Commit/hash :** en attente.
