# Metiquo — Pack Codex

Ce dossier contient les documents à placer idéalement dans `docs/specs/` du repository avant de lancer Codex.

- `00_SFG_METIQUO.md` : SFG normative.
- `01_CODEX_MASTER_PLAN.md` : découpage exécutable, tickets, gates et critères de DONE.
- `02_IMPLEMENTATION_BACKLOG.yaml` : version machine-readable du backlog (158 tickets).
- `03_TRACEABILITY.md` : couverture des 34 exigences `SFG-*` détectées dans la SFG.
- `04_FIRST_PROMPT_FOR_CODEX.md` : prompt initial à copier dans Codex.

## Utilisation

1. Copier les 5 fichiers dans `docs/specs/` de ton repo.
2. Ouvrir Codex à la racine du repo.
3. Lui envoyer le contenu de `04_FIRST_PROMPT_FOR_CODEX.md`.
4. Le laisser travailler par tickets et vérifier `docs/progress.md` et les gates de milestone.

La génération de ce pack vérifie automatiquement qu’aucun identifiant normatif `SFG-...` de la SFG n’est sans couverture dans le backlog.
