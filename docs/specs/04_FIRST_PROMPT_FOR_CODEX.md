# Prompt initial à donner à Codex — Metiquo

Tu travailles sur **Metiquo**, un projet personnel Dockerisé de pricing/value betting esport dont le périmètre MVP initial est **League of Legends**.

Avant de modifier quoi que ce soit, lis intégralement et dans cet ordre :

1. `docs/specs/00_SFG_METIQUO.md`
2. `docs/specs/01_CODEX_MASTER_PLAN.md`
3. `docs/specs/02_IMPLEMENTATION_BACKLOG.yaml`
4. `docs/specs/03_TRACEABILITY.md`

La **SFG est la source de vérité normative**. Le plan et le backlog précisent uniquement l’ordre d’exécution. En cas de divergence, la SFG gagne.

## Mission

Construis le MVP personnel de Metiquo en suivant les tickets et leurs dépendances, sans sauter les gates. Tu peux avancer automatiquement d’un ticket débloqué au suivant. Ne me demande pas de confirmer chaque ticket. Arrête-toi uniquement si :

- un secret/credential réellement nécessaire manque ;
- une source tierce ne permet pas de valider le chemin réel ;
- une décision explicitement humaine/juridique de la SFG est requise ;
- tu rencontres une contradiction réelle entre exigences.

Dans ces cas, implémente quand même tout ce qui peut être testé avec les fixtures prévues, marque précisément ce qui reste non validé en réel, et ne fabrique jamais un succès.

## Règles absolues

- Oracle’s Elixir est l’unique source statistique LoL.
- Aucune donnée future ne peut entrer dans une feature : le cutoff est obligatoire et les tests anti-leakage sont bloquants.
- Le modèle indépendant n’utilise pas les cotes bookmaker comme features.
- Raw snapshots, odds snapshots, predictions, signals, paper bets, évaluations publiées et audit restent immuables/append-only conformément à la SFG.
- Mock et réel utilisent les mêmes DTO, endpoints et composants UI, avec stockage isolé.
- Aucun historique financier ne doit être inventé : ROI/CLV financiers utilisent uniquement des cotes réellement observées et horodatées.
- N’implémente aucun scraper Stake, aucun contournement anti-bot/CAPTCHA/géoblocage, aucun proxy de contournement, aucun cookie de compte bookmaker et aucune mise réelle automatisée. `StakeAuthorizedProvider` reste explicitement désactivé.
- Pas de Kubernetes, Kafka, Airflow, Spark, Redis/Celery ou feature store au MVP sans ADR et besoin mesuré.
- Ne choisis pas un modèle complexe par prestige : il doit être comparé aux baselines et validé en walk-forward/calibration.
- N’utilise pas un split aléatoire comme split principal.
- N’active aucun marché sans le capability gate complet.
- N’ajoute pas CS2, Dota 2, billing, multi-tenant ou SaaS public avant les gates prévues.

## Discipline d’exécution

Crée `docs/progress.md` s’il n’existe pas. Pour chaque ticket, inscris :

- ID et titre ;
- statut `TODO | IN_PROGRESS | BLOCKED | DONE` ;
- dépendances vérifiées ;
- fichiers créés/modifiés ;
- migrations ;
- commandes/tests réellement exécutés ;
- résultat exact ;
- blocker éventuel ;
- ADR éventuel ;
- commit/hash si disponible.

Un ticket n’est `DONE` que si ses critères d’acceptation sont satisfaits **et que ses tests ont réellement passé**. Pas de faux `success`, pas de placeholder caché, pas de `TODO` dans un chemin déclaré terminé, sauf les squelettes explicitement gated dans les documents.

## Démarrage

1. Inspecte l’état actuel du repository.
2. Compare-le à la SFG et au backlog : ne détruis pas du code déjà conforme.
3. Identifie le premier ticket non réalisé dont les dépendances sont satisfaites. Si le repo est vide, commence par `FND-001`.
4. Implémente ce ticket complètement, teste-le, mets à jour `docs/progress.md`, puis continue avec le prochain ticket débloqué.
5. À chaque gate (`MCK-007`, `OE-025`, `FEAT-014`, `ML-017`, `MAP-006`, `VAL-009`, `PAP-010`, `OPS-010`, `QA-007`), exécute la suite de validation du milestone et enregistre les preuves avant de poursuivre.
6. Le but final de cette séquence est `QA-007` : **recette complète du MVP personnel**. Les phases P10/P11 ne doivent pas être lancées avant cette gate.

Commence maintenant par l’inspection du repository et l’exécution du premier ticket réellement nécessaire. Ne réécris pas les spécifications : implémente-les.
