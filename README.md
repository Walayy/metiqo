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

Ce logiciel n’exécute aucun pari réel et ne garantit aucun gain.
