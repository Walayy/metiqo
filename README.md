# Metiquo

Metiquo est un projet personnel Dockerisé de pricing et de détection de value betting esport. Le MVP initial couvre exclusivement League of Legends et utilise Oracle’s Elixir comme unique source statistique LoL.

La spécification normative se trouve dans [`docs/specs/00_SFG_METIQUO.md`](docs/specs/00_SFG_METIQUO.md). Le plan d’exécution et le backlog se trouvent dans le même dossier. L’avancement vérifié est consigné dans [`docs/progress.md`](docs/progress.md).

Le dépôt est actuellement au stade des fondations. Les commandes d’installation et de démarrage seront ajoutées par les tickets dédiés ; aucune commande non encore implémentée n’est présentée comme fonctionnelle.

## Outillage

- Node.js `24.20.0` et pnpm `11.25.0` ;
- Python `3.13.14` et uv ;
- TypeScript strict, ESLint, Prettier et Playwright ;
- Ruff, mypy et pytest.

Les dépendances sont installées exclusivement depuis les lockfiles avec `pnpm install --frozen-lockfile` et `uv sync --frozen`.

## Configuration serveur

Copier `.env.example` vers `.env`, puis remplacer uniquement les valeurs propres à l’environnement local. Le chargement typé est centralisé dans `metiquo.config` ; une valeur absente, incohérente ou invalide interrompt le démarrage avec le nom de la variable concernée, sans afficher sa valeur sensible.

`DISPLAY_TIMEZONE` contrôle uniquement le rendu. Les instants internes restent en UTC.

## Base de données

Après avoir défini `DATABASE_URL` pour une base PostgreSQL vide, appliquer les migrations avec `uv run alembic upgrade head`. La révision initiale crée uniquement les schémas logiques `raw`, `core`, `odds`, `features`, `ml`, `signals` et `ops` ; elle n’insère aucune donnée.

Ce logiciel n’exécute aucun pari réel et ne garantit aucun gain.
