# Metiquo — Plan d’implémentation exécutable pour Codex

**Document dérivé de la SFG Metiquo v1.0 — 4 septembre 2026**  
**But :** transformer la SFG en ordre de travail déterministe, vérifiable et exploitable par un agent de développement.

> Règle de priorité : en cas de divergence, `00_SFG_METIQUO.md` prévaut. Ce plan précise l’exécution mais ne modifie pas les exigences fonctionnelles.

## 1. Contrat de travail de Codex

Codex doit respecter les règles suivantes pendant toute l’implémentation :

1. Lire la SFG, ce plan, le backlog YAML et la matrice de traçabilité avant la première modification.
2. Exécuter les tickets dans l’ordre des dépendances. Ne pas marquer un ticket `DONE` parce que le code “semble correct” : lancer les tests prévus et enregistrer le résultat.
3. Utiliser `docs/progress.md` comme journal d’exécution : ticket, fichiers modifiés, commandes lancées, résultat, dette éventuelle, hash/commit si disponible.
4. Ne jamais remplacer une exigence par un mock caché. Le mock n’est autorisé que lorsque `APP_DATA_MODE=mock` ou dans les fixtures/tests.
5. Ne jamais utiliser une autre source statistique LoL qu’Oracle’s Elixir.
6. Ne jamais coder de scraper Stake, de contournement anti-bot/CAPTCHA/géoblocage, de rotation de proxy, de réutilisation de cookies bookmaker ou de placement automatique de pari.
7. Ne pas utiliser la cote bookmaker comme feature du modèle indépendant `game_winner`.
8. Toute feature de production requiert un cutoff explicite et doit prouver `max_input_time < cutoff`.
9. Préserver l’immutabilité prescrite : raw snapshots, odds snapshots, predictions, signals, paper bets, évaluations publiées et audit ne sont jamais réécrits silencieusement.
10. Ne pas introduire Kubernetes, Kafka, Airflow, Spark, Redis/Celery ou feature store au MVP sans ADR démontrant un besoin mesuré.
11. Les versions de bibliothèques ne sont volontairement pas inventées ici : au bootstrap, choisir des versions stables compatibles disponibles, puis les figer dans `pnpm-lock.yaml` et `uv.lock`.
12. Si un détail technique non normé doit être choisi, prendre la solution la plus simple compatible avec la SFG et documenter le choix dans un ADR uniquement s’il est structurant.
13. Si une exigence est impossible à satisfaire dans l’environnement courant (secret absent, source tierce inaccessible), implémenter le comportement déterministe prévu, les fixtures et les tests; noter le blocker sans fabriquer un succès.
14. Ne pas commencer les marchés LoL supplémentaires avant la recette MVP `QA-007`.
15. Ne pas commencer multi-user, billing, CS2 ou Dota 2 avant les gates correspondantes.

## 2. Définition universelle de DONE

Un ticket est `DONE` uniquement si :

- le code de production est présent et typé ;
- les migrations nécessaires existent et ont été testées ;
- les tests unitaires/intégration/E2E demandés ont réellement passé ;
- aucune fixture de test n’est utilisée silencieusement en mode réel ;
- les logs et erreurs ne divulguent aucun secret ;
- la documentation opérationnelle ou API est mise à jour si le comportement change ;
- `docs/progress.md` contient la preuve d’exécution ;
- aucune exigence SFG couverte par le ticket n’est contredite ;
- aucun `TODO`, `pass`, faux retour “success”, valeur placeholder ou implémentation désactivée ne subsiste dans le chemin considéré comme terminé, sauf squelette explicitement prévu (`LicensedOddsFeedProvider`, `StakeAuthorizedProvider`, SaaS/multi-game gated).

## 3. Architecture cible non négociable sans ADR

```text
repo/
├── apps/web/                  # Next.js / React / TypeScript
├── services/api/              # FastAPI
├── services/worker/           # worker Python
├── packages/contracts/        # client/DTO générés ou partagés
├── packages/ui/               # design system
├── packages/config/           # config frontend partagée sans secrets
├── python/metiquo/
│   ├── data_sources/
│   ├── ingestion/
│   ├── canonical/
│   ├── features/
│   ├── markets/
│   ├── models/
│   ├── pricing/
│   ├── signals/
│   ├── paper/
│   └── ops/
├── infra/compose/
├── infra/gateway/
├── infra/scripts/
├── tests/fixtures/
├── tests/integration/
├── tests/model/
├── tests/e2e/
└── docs/
```

Flux métier de référence :

```text
Oracle’s Elixir -> catalogue -> download -> validation -> raw snapshot
    -> canonique LoL -> features as-of -> dataset -> modèle calibré
    -> prediction / fair price

OddsProvider -> odds snapshots -> mapping event/market

prediction + mapped odds -> no-vig -> edge/EV -> guards/abstention
    -> signal/opportunity -> paper bet -> settlement -> metrics/CLV
```

## 4. Blueprint de persistance

Les migrations détaillées seront écrites par Codex, mais les familles suivantes doivent exister et conserver les invariants indiqués :

| Schéma | Tables/familles minimales | Invariants |
|---|---|---|
| `raw` | source_catalog, snapshots, ingestion_runs, quality_issues, quarantine_items, row revisions/staging | snapshots immuables, SHA-256, current pointer atomique, audit |
| `core` | games, series, teams, players, competitions, patches, game_team_stats, game_player_stats, roster_observations, entity_aliases | provenance vers raw, révisions historisées, ambiguïtés non forcées |
| `odds` | providers, events, markets, selections, snapshots, provider health, mappings/reviews | snapshots append-only, captured_at, market status/rules |
| `features` | definitions, feature_sets, feature_snapshots, invalidations | cutoff, max_input_time, hash/version, immutable snapshots |
| `ml` | datasets, training_runs, model_versions, calibrators/artifact refs, predictions, evaluations | walk-forward, hashes, champion unique, predictions immuables |
| `signals` | signals, paper_bets, settlements | input snapshot IDs, policy version, append-only |
| `ops` | jobs, audit_events, incidents/alerts, config versions, backup manifests | jobs reprenables, audit append-only |

## 5. Milestones utilisateur

| Milestone | Résultat démontrable | Gate |
|---|---|---|
| M0 | Repo + Compose + API/Web/Worker démarrent | FND-010 |
| M1 | Application complète en mock, 12 scénarios, UX stable | MCK-007 |
| M2 | OE robuste: catalogue, snapshots, DQ, backfill, stale/require-fresh | OE-025 |
| M3 | Canonique + feature snapshots sans fuite temporelle | FEAT-014 |
| M4 | Modèle `game_winner` calibré + fair odds + série | ML-017 |
| M5 | Odds provider + mapping sûr | MAP-006 |
| M6 | Value signal complet + abstention | VAL-009 |
| M7 | Paper trading + settlement + CLV/metrics | PAP-010 |
| M8 | Jobs, sécurité, sauvegarde/restauration | OPS-010 |
| MVP | 22 critères SFG §31 vérifiés | QA-007 |

## 6. Ordre d’exécution détaillé

### P0 — Garde-fous et fondations

Rendre le dépôt reproductible, Dockerisé et strict avant toute logique métier.

#### `FND-001` — Initialiser le monorepo

**Dépendances :** aucune  
**Traçabilité SFG :** `SFG-INFRA-001`

**Livrables**

- Arborescence conforme à la SFG: apps/web, services/api, services/worker, packages/contracts, packages/ui, packages/config, python/metiquo, infra, tests, docs.
- Gitignore, EditorConfig, README minimal, fichiers de version et scripts racine.

**DONE quand**

- Le dépôt se clone et possède tous les répertoires attendus sans code métier factice.
- Aucun notebook n’est requis par la production.

**Tests / preuves**

- Vérification arborescence
- git status propre après bootstrap

#### `FND-002` — Figer l’outillage et les dépendances

**Dépendances :** `FND-001`  
**Traçabilité SFG :** `SFG-INFRA-001`

**Livrables**

- Workspace pnpm pour TypeScript.
- Projet Python géré par uv et uv.lock.
- TypeScript strict, Ruff, type checker Python, pytest, Playwright.
- Versions stables compatibles choisies au moment de l’implémentation puis verrouillées dans les lockfiles; aucune version n’est inventée dans cette spécification.

**DONE quand**

- Installation reproductible depuis zéro avec les lockfiles.
- Aucune dépendance ajoutée sans usage identifié.

**Tests / preuves**

- pnpm install --frozen-lockfile
- uv sync --frozen

#### `FND-003` — Créer la configuration typée

**Dépendances :** `FND-002`  
**Traçabilité SFG :** `SFG-MOCK-002`, `SFG-SEC-001`

**Livrables**

- Configuration serveur unique avec validation au démarrage.
- Variables APP_ENV, APP_DATA_MODE, DATABASE_URL, OBJECT_STORE_*, DISPLAY_TIMEZONE, OE_*, ODDS_PROVIDER, ODDS_MAX_AGE_SECONDS, seuils de signal.
- .env.example sans secret.

**DONE quand**

- Une variable invalide provoque une erreur lisible avant démarrage.
- Tous les timestamps internes sont UTC; Europe/Paris ne sert qu’au rendu.

**Tests / preuves**

- Tests config valide/invalide
- Scan .env.example pour absence de secret

#### `FND-004` — Créer PostgreSQL et les schémas logiques

**Dépendances :** `FND-003`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- Alembic initial.
- Schémas PostgreSQL raw, core, odds, features, ml, signals, ops.
- Extension(s) strictement nécessaires seulement.
- Convention d’ID, created_at, updated_at et timestamps UTC.

**DONE quand**

- Une base vide migre jusqu’à HEAD.
- Une migration downgrade est fournie lorsque raisonnablement possible.
- Les schémas existent sans données mock.

**Tests / preuves**

- alembic upgrade head sur DB vide
- test downgrade/upgrade sur migration N-1

#### `FND-005` — Créer Docker Compose minimal

**Dépendances :** `FND-004`  
**Traçabilité SFG :** `SFG-INFRA-001`, `SFG-SEC-001`

**Livrables**

- Services web, api, worker, postgres.
- Profils mock, production, object-store; gateway/minio seulement dans leurs profils.
- Healthchecks et volumes persistants postgres_data, raw_snapshots, model_artifacts, backups.
- Images non root lorsque possible.

**DONE quand**

- docker compose config valide.
- Le profil mock démarre sans service externe.
- Aucun Kafka, Kubernetes, Airflow, Spark, Redis/Celery ni feature store.

**Tests / preuves**

- docker compose --profile mock up -d --build
- healthcheck postgres/api/web

#### `FND-006` — Créer les primitives transverses

**Dépendances :** `FND-002`, `FND-004`  
**Traçabilité SFG :** `SFG-PRICE-001`, `SFG-OPS-001`

**Livrables**

- IDs opaques par domaine.
- Clock injectable pour tests.
- Types Money/DecimalOdds/Probability/UTC datetime.
- Erreurs métier structurées.
- Journal JSON avec trace_id et correlation ids.

**DONE quand**

- Aucun calcul financier ne repose sur float non contrôlé si la précision décimale est nécessaire.
- Tests déterministes grâce à l’horloge injectable.

**Tests / preuves**

- Unit tests primitives
- Typecheck

#### `FND-007` — Squelette FastAPI et contrat OpenAPI

**Dépendances :** `FND-003`, `FND-006`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- FastAPI /health, /ready, /api/v1/system/status.
- Format d’erreur RFC7807 ou équivalent.
- DTO Pydantic séparés des ORM.
- Génération OpenAPI versionnée.

**DONE quand**

- /health ne dépend pas des sources externes.
- /ready échoue si DB/migrations indisponibles.
- Le schéma OpenAPI est exportable en CI.

**Tests / preuves**

- pytest API health/ready
- openapi generation smoke test

#### `FND-008` — Squelette worker

**Dépendances :** `FND-003`, `FND-004`, `FND-006`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- Process worker séparé du serveur web.
- Interface JobHandler et contexte de job.
- Pas encore de scheduler métier; seulement le lifecycle.

**DONE quand**

- Le worker démarre et s’arrête proprement sans job.
- Aucun calcul lourd dans le process web.

**Tests / preuves**

- worker startup/shutdown test

#### `FND-009` — Makefile et commandes développeur

**Dépendances :** `FND-005`, `FND-007`, `FND-008`  
**Traçabilité SFG :** `SFG-INFRA-001`

**Livrables**

- make up/down, db-migrate, lint, typecheck, test, test-e2e, openapi, format.
- Cibles futures OE réservées mais non simulées.

**DONE quand**

- README documente un parcours local reproductible.
- Les commandes CI utilisent les mêmes scripts que localement.

**Tests / preuves**

- make lint
- make test

#### `FND-010` — CI de base et discipline ADR

**Dépendances :** `FND-009`  
**Traçabilité SFG :** `SFG-INFRA-001`, `SFG-SEC-001`

**Livrables**

- Pipeline lint frontend, TS strict, Python lint/typecheck, unit tests, migration test, Docker build.
- Template ADR dans docs/adr.
- CODEOWNERS facultatif si utile; pas de processus lourd.

**DONE quand**

- Aucun changement structurant de la liste SFG §33 n’est accepté sans ADR.
- CI rouge bloque la fusion.

**Tests / preuves**

- CI locale/simulateur si disponible

### P1 — Contrats, mock et interface

Livrer une démonstration complète sans aucune source externe, avec les mêmes contrats que le réel.

#### `MCK-001` — Définir les contrats de domaine

**Dépendances :** `FND-007`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-ODDS-001`

**Livrables**

- Enums jeu, marché, période, sélection, grade, freshness, abstention, statut provider/marché/event.
- DTO Opportunity, Event, Market, OddsSnapshot, Prediction, Value, Quality, ModelSummary, BacktestSummary, PaperBet, MappingReview.
- Contrats versionnés dans packages/contracts / équivalent généré depuis OpenAPI.

**DONE quand**

- Mock et réel pourront implémenter exactement ces mêmes DTO.
- Aucun DTO ne dépend d’un ORM ou du HTML d’un bookmaker.

**Tests / preuves**

- Contract tests
- OpenAPI compatibility test

#### `MCK-002` — Implémenter l’isolation mock/réel

**Dépendances :** `FND-003`, `MCK-001`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-MOCK-002`

**Livrables**

- DataMode explicite propagé dans les réponses.
- Repositories/factories distincts.
- Guard: real refuse un provider mock comme source de vérité.
- Base ou schéma mock séparé du réel.

**DONE quand**

- Aucune requête Oracle/bookmaker ne part en mode mock.
- Impossible de lire/écrire des données mock via le contexte real.

**Tests / preuves**

- Tests isolation croisée
- test démarrage real+mock provider => échec

#### `MCK-003` — Créer les 12 scénarios mock normatifs

**Dépendances :** `MCK-001`, `MCK-002`  
**Traçabilité SFG :** `SFG-MOCK-001`

**Livrables**

- Seed déterministe pour: faible value, outsider value, odds stale, marché suspendu, mapping ambigu, OE incomplet, modèle stale, forte incertitude, sync échouée avec snapshot valide, changement de cote, void, résultat incohérent/quarantaine.

**DONE quand**

- Même seed => mêmes IDs, timestamps relatifs contrôlés et mêmes valeurs.
- Chaque scénario est adressable en test.

**Tests / preuves**

- Snapshot tests données mock
- Property test déterminisme

#### `MCK-004` — Implémenter repositories/services mock

**Dépendances :** `MCK-003`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-ODDS-001`

**Livrables**

- MockOpportunityRepository, MockEventRepository, MockModelRepository, MockPaperRepository, MockDataHealthRepository, MockMappingRepository.
- MockOddsProvider conforme au contrat futur.

**DONE quand**

- Aucun code UI ne branche directement sur des fixtures.
- Tous les appels passent par les mêmes services que le réel.

**Tests / preuves**

- Unit/contract tests mocks

#### `MCK-005` — Exposer toutes les lectures API en mock

**Dépendances :** `MCK-004`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-UX-001`

**Livrables**

- GET opportunities/detail/explanation.
- GET events/detail/markets/odds-history.
- GET models/backtests.
- GET paper-bets.
- GET admin data sources/runs/quality/jobs.
- GET mappings pending.

**DONE quand**

- Pagination/filtres typés.
- Chaque réponse métier contient dataMode, freshness/asOf et version lorsque pertinente.

**Tests / preuves**

- API tests filtres/pagination/404/empty/error

#### `MCK-006` — Exposer mutations mock contrôlées

**Dépendances :** `MCK-005`  
**Traçabilité SFG :** `SFG-OPS-001`, `SFG-MOCK-001`

**Livrables**

- Actions mock sync, train, promote, retire, paper bet, settle, mapping approve/reject/alias.
- Idempotency key sur mutations sensibles.
- Audit mock cohérent.

**DONE quand**

- Double soumission même idempotency key ne duplique pas l’effet.
- Les actions retournent des états réalistes sans appeler l’extérieur.

**Tests / preuves**

- API idempotency tests

#### `MCK-007` — Gate P1 — démo mock complète

**Dépendances :** `MCK-006`, `UI-011`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-MOCK-002`, `SFG-UX-002`

**Livrables**

- Script de seed et scénario demo.
- E2E couvrant parcours critiques.
- README “démarrer en mock”.

**DONE quand**

- Une machine neuve peut lancer la démo via Docker Compose sans Internet métier.
- Zéro erreur console/hydratation sur parcours clé.

**Tests / preuves**

- docker compose --profile mock up -d --build
- make test-e2e

#### `UI-001` — Initialiser le frontend et le design system

**Dépendances :** `FND-002`, `MCK-001`  
**Traçabilité SFG :** `SFG-UX-003`

**Livrables**

- Next.js/React/TypeScript strict.
- Tailwind, primitives accessibles, tokens spacing/radius/typography/elevation.
- Client TypeScript généré depuis OpenAPI.
- TanStack Query.
- Motion légère uniquement pour micro-interactions.

**DONE quand**

- Pas de duplication manuelle des DTO backend.
- Composants de base navigables au clavier.

**Tests / preuves**

- pnpm typecheck
- component smoke tests

#### `UI-002` — Thème et shell sans flash

**Dépendances :** `UI-001`  
**Traçabilité SFG :** `SFG-UX-001`, `SFG-UX-002`

**Livrables**

- Thème système avec stratégie anti-FOUC.
- Navigation: Opportunités, Événements, Paper trading, Modèles & backtests, Données, Administration, Paramètres.
- Badge MOCK/REAL persistant.

**DONE quand**

- Aucun flash clair/sombre.
- Aucun warning d’hydratation.
- Navigation responsive.

**Tests / preuves**

- Playwright console/hydration test
- visual screenshot light/dark

#### `UI-003` — Bibliothèque d’états distants

**Dépendances :** `UI-001`  
**Traçabilité SFG :** `SFG-UX-002`

**Livrables**

- Composants loading/skeleton, empty, recoverable error, blocking error, stale, permission denied, mock, offline/reconnecting.
- Skeletons aux dimensions réservées.

**DONE quand**

- Aucun spinner infini.
- Le contenu précédent reste visible pendant refetch lorsque sûr.

**Tests / preuves**

- Component state matrix test

#### `UI-004` — Dashboard Opportunités

**Dépendances :** `MCK-005`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-UX-001`, `SFG-UX-003`

**Livrables**

- Résumé santé, compteur opportunités, dernière MAJ, filtres, table/cartes, tri EV prudente, changement de cote, grade, temps avant début.
- Colonnes normatives de la SFG.
- État no opportunity explicite.

**DONE quand**

- Filtres et tri sont stables et partageables par URL si pertinent.
- Pas de couleur seule pour signifier positif/négatif.

**Tests / preuves**

- Playwright filtres/tri/empty/stale

#### `UI-005` — Fiche événement

**Dépendances :** `MCK-005`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-UX-001`, `SFG-UX-003`

**Livrables**

- Participants/format, courbe odds, marchés supportés/non supportés, probabilités/intervalles, facteurs, données manquantes, roster attendu/confiance, model version, snapshot OE, timeline signal, bouton paper bet uniquement.

**DONE quand**

- Aucun CTA de mise réelle.
- Graphiques ont un résumé textuel accessible.

**Tests / preuves**

- Playwright event detail
- a11y checks

#### `UI-006` — Fiche signal et explicabilité UI

**Dépendances :** `MCK-005`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-UX-001`

**Livrables**

- Sections prix marché, prix modèle, facteurs structurés, risques/incertitude, qualité/fraîcheur, historique, règlement paper.
- Raisons d’abstention visibles.

**DONE quand**

- Aucun langage “garanti/lock/sûr”.
- Contributions modèles ne sont pas présentées comme causalité.

**Tests / preuves**

- Content assertions
- accessibility test

#### `UI-007` — Modèles et backtests UI

**Dépendances :** `MCK-005`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-UX-001`

**Livrables**

- Champion/challengers, métriques, calibration, performance temporelle/segment, baselines, capacité marchés, promotions.
- Faible échantillon signalé.

**DONE quand**

- Le modèle/version affiché correspond au DTO.
- Pas de graphique sans alternative textuelle.

**Tests / preuves**

- Playwright models/backtests

#### `UI-008` — Santé data et administration UI

**Dépendances :** `MCK-005`, `MCK-006`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-UX-001`, `SFG-OPS-001`

**Livrables**

- Catalogue, dernière tentative/succès, fraîcheur année, hash actif, lignes/plage dates, schéma, anomalies, quarantaine, jobs, sync contrôlée.

**DONE quand**

- Les actions affichent progress/resultat sans polling agressif.
- Erreurs récupérables et bloquantes différenciées.

**Tests / preuves**

- Playwright admin data states

#### `UI-009` — File de mapping UI

**Dépendances :** `MCK-005`, `MCK-006`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-MAP-001`, `SFG-OPS-001`

**Livrables**

- Événement brut, candidats, score par composante, raisons, aliases, approve/reject/create dated alias, impact preview.

**DONE quand**

- Une ambiguïté mock reste bloquante jusqu’à action explicite.
- Action auditée.

**Tests / preuves**

- Playwright mapping review

#### `UI-010` — Paper trading UI mock

**Dépendances :** `MCK-005`, `MCK-006`, `UI-002`, `UI-003`  
**Traçabilité SFG :** `SFG-PAPER-002`

**Livrables**

- Liste/detail paper bets, P&L mock, statuts pending/won/lost/push/void/pending_review.
- Création depuis signal admissible.

**DONE quand**

- Les pertes sont visibles comme les gains.
- Aucune exécution réelle.

**Tests / preuves**

- Playwright paper bet flow

#### `UI-011` — Micro-interactions, responsive et accessibilité

**Dépendances :** `UI-004`, `UI-005`, `UI-006`, `UI-007`, `UI-008`, `UI-009`, `UI-010`  
**Traçabilité SFG :** `SFG-UX-002`, `SFG-UX-003`

**Livrables**

- Transitions 120–220 ms, opacity/transform, hover/focus/pressed, reduced motion.
- Desktop/tablette/mobile.
- Navigation clavier, contrastes AA, aria-live raisonnable, targets tactiles.

**DONE quand**

- CLS cible <0,05 sur pages clés en test.
- Aucune table ne nécessite zoom navigateur.
- Focus visible partout.

**Tests / preuves**

- Playwright desktop/mobile
- axe ou équivalent
- visual regression

**Interdiction de passage P2 :** tant que la démo mock complète ne passe pas, ne pas brancher l’UI directement sur Oracle’s Elixir.

### P2 — Oracle's Elixir

Rendre l'historique LoL reproductible, versionné, idempotent, observable et sûr.

#### `OE-001` — Modèle raw: catalogue, snapshots, runs et qualité

**Dépendances :** `FND-004`  
**Traçabilité SFG :** `SFG-DATA-002`, `SFG-OPS-001`

**Livrables**

- Tables raw.source_catalog, raw.snapshots, raw.ingestion_runs, raw.quality_issues, raw.quarantine_items, raw.row_revisions/équivalent.
- Contraintes uniqueness et statut.
- Liens d’audit/provenance.

**DONE quand**

- Migration testée.
- Aucun snapshot validé ne peut être écrasé.

**Tests / preuves**

- DB constraint tests

#### `OE-002` — ObjectStore filesystem adressé par hash

**Dépendances :** `OE-001`  
**Traçabilité SFG :** `SFG-DATA-002`

**Livrables**

- Interface ObjectStore.
- Backend filesystem /data.
- Layout year=YYYY/sha256=... avec source.bin/source.csv/manifest/schema/quality-report.
- Écriture temporaire puis promotion atomique.

**DONE quand**

- Un objet existant avec même hash est réutilisé, jamais muté.
- Le stockage est indépendant du chemin temporaire.

**Tests / preuves**

- Object store unit/integration tests

#### `OE-003` — Découverte du catalogue Oracle’s Elixir

**Dépendances :** `OE-001`  
**Traçabilité SFG :** `SFG-DATA-001`

**Livrables**

- Fetcher de la page officielle de téléchargements.
- Extraction des liens Google Drive et IDs.
- Association annuelle avec règles explicites et testées.
- Détection changement ID, doublon, disparition, ambiguïté.
- Persistance discovered_at/last_confirmed/payload hash.

**DONE quand**

- Aucune autre source statistique LoL n’est interrogée.
- Une ambiguïté ne remplace jamais silencieusement le catalogue actif.

**Tests / preuves**

- HTML fixtures de découverte
- tests changement/doublon/missing

#### `OE-004` — Catalogue de secours versionné

**Dépendances :** `OE-003`  
**Traçabilité SFG :** `SFG-DATA-001`

**Livrables**

- config/oracles_elixir_sources.yml.
- Entrée bootstrap 2026 avec ID 1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm marquée validated-bootstrap/mutable.
- Fallback seulement si landing page inaccessible.

**DONE quand**

- Le fallback ne masque jamais une divergence détectée.
- L’origine bootstrap est visible dans audit/health.

**Tests / preuves**

- fallback selection tests

#### `OE-005` — Contrat SourceTransport

**Dépendances :** `OE-001`, `FND-006`  
**Traçabilité SFG :** `SFG-DATA-003`

**Livrables**

- SourceRef, SourceMetadata, DownloadReceipt.
- Protocol probe/download.
- Timeouts, taille max, redirections et policy retry passés par config.

**DONE quand**

- Tous les transports satisfont les mêmes contract tests.

**Tests / preuves**

- transport contract tests

#### `OE-006` — GoogleDriveApiTransport

**Dépendances :** `OE-005`  
**Traçabilité SFG :** `SFG-DATA-003`, `SFG-SEC-001`

**Livrables**

- Transport Drive API lorsque credentials autorisés présents.
- Téléchargement streaming/chunked.
- Classification structurée des erreurs quota/rate/permission/not found.

**DONE quand**

- Aucun secret loggé.
- Une erreur quota n’écrit jamais un snapshot.

**Tests / preuves**

- mocked Drive API tests
- secret redaction test

#### `OE-007` — GoogleDrivePublicHttpTransport

**Dépendances :** `OE-005`  
**Traçabilité SFG :** `SFG-DATA-003`

**Livrables**

- Fallback HTTP public autorisé.
- Redirections bornées.
- Détection pages HTML quota/consent/login.
- Pas de contournement de quota.

**DONE quand**

- Une réponse HTML même HTTP 200 est refusée.
- Aucun mécanisme de bypass.

**Tests / preuves**

- fixtures quota/consent/html200

#### `OE-008` — MirrorTransport et LocalFixtureTransport

**Dépendances :** `OE-005`, `OE-002`  
**Traçabilité SFG :** `SFG-DATA-007`, `SFG-MOCK-002`

**Livrables**

- Mirror du dernier snapshot privé validé; aucune invention de fraîcheur.
- Transport fixtures pour CI.
- Priorité de transports explicite.

**DONE quand**

- Le miroir ne peut être déclaré fresh si la source n’a pas été confirmée.
- Fixtures n’existent pas en mode real comme source de vérité.

**Tests / preuves**

- contract tests

#### `OE-009` — Téléchargeur sûr en streaming

**Dépendances :** `OE-005`  
**Traçabilité SFG :** `SFG-DATA-002`, `SFG-DATA-003`

**Livrables**

- .part dans même volume, streaming, SHA-256 pendant flux, limites taille/durée, fsync, rename atomique.
- Détection MIME/magic/compression.
- Nettoyage des temporaires après échec.

**DONE quand**

- Jamais de chargement du fichier entier en RAM.
- Aucun .part n’est visible par l’ingestion.

**Tests / preuves**

- large-stream fixture
- interruption cleanup test

#### `OE-010` — Taxonomie d’erreurs et retries

**Dépendances :** `OE-006`, `OE-007`, `OE-009`  
**Traçabilité SFG :** `SFG-DATA-003`, `SFG-OPS-001`

**Livrables**

- Exceptions SourceNotFound, PermissionDenied, QuotaExceeded, RateLimited, Timeout, UnexpectedHtmlResponse, UnexpectedContentType, ChecksumMismatch, ArchiveCorrupted, SchemaIncompatible, DataQualityFailed, AtomicPromotionFailed.
- Backoff exponentiel+jitter seulement transitoires.

**DONE quand**

- Chaque erreur conserve type/contexte/tentatives/transport/retryability.
- Aucun retry agressif permanent.

**Tests / preuves**

- error mapping tests
- retry policy tests

#### `OE-011` — Manifeste et empreintes de snapshot

**Dépendances :** `OE-009`  
**Traçabilité SFG :** `SFG-DATA-002`, `SFG-ML-003`

**Livrables**

- manifest.json avec provider, year, file id, timestamps, transport, byteSize, sha256, content type, compression, encoding, delimiter, schema fingerprint, rowCount, dates min/max, quality, code version.
- schema.json.
- Hash vérifié après stockage.

**DONE quand**

- Le manifeste suffit à identifier le dataset exact consommé.
- Hash incohérent bloque promotion.

**Tests / preuves**

- manifest roundtrip test
- checksum reread test

#### `OE-012` — Validation physique

**Dépendances :** `OE-009`, `OE-011`  
**Traçabilité SFG :** `SFG-DATA-003`

**Livrables**

- Refus corps vide, HTML/JSON d’erreur, type incompatible, archive cassée, header CSV absent, colonnes incohérentes, chute de taille implausible, checksum incorrect.
- Détection encodage/délimiteur sans correction silencieuse.

**DONE quand**

- Chaque rejet produit diagnostic et aucune promotion.

**Tests / preuves**

- fixtures physical invalid cases

#### `OE-013` — Contrat de schéma évolutif

**Dépendances :** `OE-012`  
**Traçabilité SFG :** `SFG-DATA-008`, `SFG-MARKET-001`

**Livrables**

- Définition colonnes cœur requises, optionnelles, additives, capacités par marché.
- Schema fingerprint et diff.
- Conservation des nouvelles colonnes dans raw.
- Blocage ciblé des capacités si colonne requise manque.

**DONE quand**

- Une colonne additive ne casse pas ingestion.
- Une colonne retirée ne déclenche pas une hypothèse silencieuse.

**Tests / preuves**

- fixture additive
- fixture missing-core
- schema diff tests

#### `OE-014` — Data Quality métier

**Dépendances :** `OE-013`  
**Traçabilité SFG :** `SFG-DATA-008`

**Livrables**

- Contrôles IDs, dates, participants, clés naturelles, équipes distinctes, side, plages numériques, résultat, remakes/forfeits/incomplets, structure équipe/joueur, diff vs précédent, suppression massive.
- Severity blocking/capability-only.
- quality-report.json.

**DONE quand**

- Toutes les règles donnent un code stable.
- Pas de suppression massive silencieuse.

**Tests / preuves**

- DQ fixtures
- property ranges tests

#### `OE-015` — Quarantaine

**Dépendances :** `OE-014`, `OE-002`  
**Traçabilité SFG :** `SFG-DATA-002`, `SFG-OPS-001`

**Livrables**

- Nouveau contenu invalide conservé séparément avec cause.
- Dernier snapshot validé reste actif.
- Promotion manuelle seulement via action explicitement auditée si prévue; aucune auto-promotion.

**DONE quand**

- Un snapshot quarantined ne peut être lu comme current.
- UI/API peut afficher le diagnostic.

**Tests / preuves**

- quarantine state tests

#### `OE-016` — Promotion atomique du snapshot

**Dépendances :** `OE-011`, `OE-014`, `OE-015`  
**Traçabilité SFG :** `SFG-DATA-002`

**Livrables**

- Écriture manifeste/objets puis transaction DB.
- Pointeur current mis à jour seulement après succès complet.
- Rollback si promotion échoue.

**DONE quand**

- Crash avant commit laisse l’ancien snapshot current.
- Run succeeded seulement après commit.

**Tests / preuves**

- fault injection promotion tests

#### `OE-017` — Staging et chargement raw tabulaire

**Dépendances :** `OE-016`  
**Traçabilité SFG :** `SFG-DATA-004`

**Livrables**

- Staging raw.oe_staging_<run_id> ou équivalent transactionnel.
- Lecture Polars/stream adaptée au fichier.
- Clé naturelle + row hash.
- Statistiques inserted/updated/unchanged/quarantined.

**DONE quand**

- Relancer le même snapshot ne duplique aucune ligne.
- Le staging est nettoyé de façon sûre.

**Tests / preuves**

- double-load idempotency test

#### `OE-018` — Historiser les révisions de lignes

**Dépendances :** `OE-017`  
**Traçabilité SFG :** `SFG-DATA-005`

**Livrables**

- Upsert canonique source avec version/revision.
- Avant/après ou hash historique.
- Source snapshot et run pour chaque révision.
- Aucune suppression issue seulement de l’absence dans un fichier potentiellement tronqué.

**DONE quand**

- Une correction d’une ligne connue est détectée et historisée.
- Une ligne inchangée ne crée pas de fausse révision.

**Tests / preuves**

- retroactive row change test

#### `OE-019` — Diff année courante et invalidation

**Dépendances :** `OE-018`  
**Traçabilité SFG :** `SFG-DATA-005`, `SFG-PAPER-002`

**Livrables**

- Déterminer date minimale affectée par les révisions.
- Émettre événement/invalidation features à partir de cette date.
- Ne jamais réécrire prédictions passées.

**DONE quand**

- Une correction historique invalide uniquement la plage dépendante.
- Aucune prédiction immuable n’est modifiée.

**Tests / preuves**

- revision invalidation test

#### `OE-020` — États de fraîcheur et politiques stale

**Dépendances :** `OE-016`, `OE-010`  
**Traçabilité SFG :** `SFG-DATA-006`, `SFG-DATA-007`

**Livrables**

- fresh/stale/degraded/failed/quarantined.
- allow-stale et require-fresh.
- asOf et snapshot ID exposés.
- SLA configurable.

**DONE quand**

- require-fresh retourne code non nul si fresh indisponible.
- allow-stale réutilise seulement snapshot validé et annonce stale/degraded.

**Tests / preuves**

- CLI/API stale policy tests

#### `OE-021` — Backfill multi-années reprenable

**Dépendances :** `OE-003`, `OE-020`, `OE-017`, `OE-018`  
**Traçabilité SFG :** `SFG-DATA-004`

**Livrables**

- Orchestrateur from_year/to_year.
- État par année/run.
- Reprise après interruption.
- Advisory lock par provider/année lorsque job system disponible; lock local/DB dès maintenant.

**DONE quand**

- Interruption puis reprise ne duplique rien.
- Deux exécutions convergent vers même état.

**Tests / preuves**

- resume test
- concurrent sync lock test

#### `OE-022` — CLI et Make Oracle’s Elixir

**Dépendances :** `OE-021`  
**Traçabilité SFG :** `SFG-DATA-004`, `SFG-DATA-006`, `SFG-DATA-007`

**Livrables**

- oe catalog refresh, backfill, sync --allow-stale/--require-fresh, verify, diff, rebuild-canonical.
- Make aliases conformes à la SFG.

**DONE quand**

- Codes retour documentés.
- Sortie machine-readable possible pour CI/ops.

**Tests / preuves**

- CLI integration tests

#### `OE-023` — API/admin et UI santé réelles

**Dépendances :** `OE-020`, `OE-022`, `UI-008`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-UX-001`

**Livrables**

- Brancher data-sources, ingestion-runs, quality-issues, sync.
- Afficher hash, rows, plage dates, schema changes, quarantine, last attempt/success.
- Mode real sans changer les composants UI.

**DONE quand**

- Même DTO qu’en mock.
- Erreur source externe ne casse pas lecture dernier snapshot.

**Tests / preuves**

- API contract diff mock/real
- Playwright real-fixture health

#### `OE-024` — Suite de fixtures OE critique

**Dépendances :** `OE-012`, `OE-014`, `OE-018`, `OE-020`  
**Traçabilité SFG :** `SFG-DATA-003`, `SFG-DATA-004`, `SFG-DATA-005`, `SFG-DATA-008`

**Livrables**

- Fixtures minimisées: valide, additive, cœur manquant, duplicate, incomplete, remake, retro change, truncated, HTML quota, encoding/delimiter surprise, corrupted archive.
- Origine/licence de test documentée.

**DONE quand**

- Tous les cas SFG §25.2 sont couverts.
- Hashes fixtures ne sont jamais considérés comme hash du fichier courant.

**Tests / preuves**

- pytest ingestion fixtures

#### `OE-025` — Gate P2 — reconstruction data fiable

**Dépendances :** `OE-023`, `OE-024`  
**Traçabilité SFG :** `SFG-DATA-001`, `SFG-DATA-002`, `SFG-DATA-003`, `SFG-DATA-004`, `SFG-DATA-005`, `SFG-DATA-006`, `SFG-DATA-007`, `SFG-DATA-008`

**Livrables**

- Script de démonstration DB vide -> migrations -> backfill/fixture -> canonical préliminaire.
- Rapport idempotence et stale/failure.
- Documentation opérateur.

**DONE quand**

- Les critères d’acceptation OE §9.18 passent.
- Aucune page quota ne peut être ingérée.

**Tests / preuves**

- make test-ingestion
- double run
- quota run

**Interdiction de passage P3 :** aucun feature engineering sur un fichier téléchargé “à la volée”; tout input doit provenir d’un snapshot validé et traçable.

### P3 — Canonique LoL et features as-of

Transformer le raw en données métier puis en features strictement antérieures au cutoff.

#### `CNL-001` — Dimensions canoniques LoL

**Dépendances :** `OE-018`, `FND-004`  
**Traçabilité SFG :** `SFG-DATA-001`

**Livrables**

- Tables game title, competitions, teams, players, patches avec identifiants canoniques/provenance.
- Pas d’autre source statistique LoL.

**DONE quand**

- Chaque entité issue d’OE remonte au raw.
- Aucune identité externe non traçable.

**Tests / preuves**

- canonical dimension tests

#### `CNL-002` — core.games et statistiques équipes/joueurs

**Dépendances :** `CNL-001`  
**Traçabilité SFG :** `SFG-DATA-008`

**Livrables**

- core.games, game_team_stats, game_player_stats selon champs réellement disponibles.
- Flags complete/remake/forfeit/usable_for_training.
- source_snapshot_id + row_revision.

**DONE quand**

- Deux participants équipes cohérents par game quand complet.
- Données absentes restent null+availability, jamais zéro silencieux.

**Tests / preuves**

- canonical fixture tests

#### `CNL-003` — Reconstruction core.series

**Dépendances :** `CNL-002`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Priorité identifiant série fourni par OE.
- Fallback équipes/compétition/date/ordre/format uniquement non ambigu.
- best_of/allows_draw/score/result/quality/provenance.

**DONE quand**

- Une série ambiguë reste unresolved.
- BO2 peut exprimer draw si le format le permet.

**Tests / preuves**

- series reconstruction fixtures

#### `CNL-004` — Observations de roster

**Dépendances :** `CNL-002`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- core.roster_observations datées dérivées des games.
- Rôles/joueurs/équipe/provenance.
- Aucune annonce externe.

**DONE quand**

- Roster attendu futur n’est jamais stocké comme vérité historique.
- Une substitution inconnue réduit confiance plus tard.

**Tests / preuves**

- roster temporal tests

#### `CNL-005` — Provenance et historique canonique

**Dépendances :** `CNL-001`, `CNL-002`, `CNL-003`, `CNL-004`  
**Traçabilité SFG :** `SFG-ML-003`, `SFG-OPS-001`

**Livrables**

- Lien snapshot, ligne(s) source, transformation version, processed_at, correction éventuelle, quality status.
- Historisation des révisions.

**DONE quand**

- À partir d’une ligne core, on retrouve raw snapshot/run.
- Une révision n’efface pas l’ancienne trace.

**Tests / preuves**

- provenance roundtrip tests

#### `CNL-006` — Capability registry

**Dépendances :** `OE-013`, `CNL-002`, `CNL-003`  
**Traçabilité SFG :** `SFG-MARKET-001`, `SFG-DATA-008`

**Livrables**

- Registre par snapshot/capacité: labels et features réellement calculables.
- Raisons enabled/disabled.
- Seuils de complétude versionnés.
- Matrice UI/API.

**DONE quand**

- Un marché ne peut pas devenir enabled sans label+données+rules+model+mapping+odds+sample gates.
- Avant modèle/odds, état reste disabled/pending.

**Tests / preuves**

- capability state tests

#### `CNL-007` — Repository real canonique et APIs événements historiques

**Dépendances :** `CNL-005`, `MCK-002`  
**Traçabilité SFG :** `SFG-MOCK-001`

**Livrables**

- Repositories real pour teams/series/games.
- DTO identiques au mock lorsque exposés.
- Pagination et filtres.

**DONE quand**

- Switch mock/real ne modifie pas composants UI.
- Fraîcheur source propagée.

**Tests / preuves**

- contract tests mock vs real

#### `FEAT-001` — Registre des définitions de features

**Dépendances :** `CNL-005`  
**Traçabilité SFG :** `SFG-ML-003`

**Livrables**

- FeatureDefinition versionnée: nom, domaine, paramètres, disponibilité, code version.
- Feature set version.
- Interdiction de colonnes ad hoc non versionnées.

**DONE quand**

- Toute prédiction référence une feature version.

**Tests / preuves**

- feature registry tests

#### `FEAT-002` — Primitives as-of et cutoff

**Dépendances :** `FEAT-001`, `CNL-002`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- API de lecture exigeant cutoff.
- max_input_time calculé/stocké.
- Assertion max(source_event_time_used) < cutoff.
- Helpers SQL/Polars empêchant agrégats sans cutoff.

**DONE quand**

- Impossible de construire une feature de production sans cutoff explicite.
- Toute violation lève une erreur bloquante.

**Tests / preuves**

- future-game injection test
- cutoff boundary tests

#### `FEAT-003` — Rating temporel pré-game

**Dépendances :** `FEAT-002`  
**Traçabilité SFG :** `SFG-TIME-001`, `SFG-ML-002`

**Livrables**

- Elo/Glicko-like ou équivalent rating baseline auditable.
- Valeur avant la game uniquement.
- Paramètres versionnés.
- Priori ligue/région si nécessaire.

**DONE quand**

- Le rating d’une game n’utilise pas son résultat.
- Recalcul déterministe.

**Tests / preuves**

- tiny sequence hand-check tests

#### `FEAT-004` — Forme récente

**Dépendances :** `FEAT-002`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Fenêtres 5/10/20 games, 30/60/90 jours, EWM, tendance/volatilité, force adversaires, data completeness.
- Pas d’imputation silencieuse.

**DONE quand**

- Toutes les fenêtres coupent strictement avant cutoff.
- Nouveau roster petit sample est régularisé plus tard.

**Tests / preuves**

- window cutoff tests

#### `FEAT-005` — Features side

**Dépendances :** `FEAT-002`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Win rate blue/red ajusté, différentiels, early stats si disponibles.
- Représentation explicite side inconnue pour marginalisation future.

**DONE quand**

- Side future inconnue n’est jamais supposée.

**Tests / preuves**

- unknown-side tests

#### `FEAT-006` — Économie, rythme et objectifs conditionnels

**Dépendances :** `FEAT-002`, `CNL-006`  
**Traçabilité SFG :** `SFG-DATA-008`, `SFG-TIME-001`

**Livrables**

- Gold/XP/CS diff timestamps présents, kills/min, durée, tours/objectifs/min, conversion/comeback sans fuite.
- Objectif first/total seulement si capability indique présence.

**DONE quand**

- Une colonne OE absente désactive la feature au lieu d’inventer.
- Availability indicators accompagnent groupes.

**Tests / preuves**

- missing-capability tests

#### `FEAT-007` — Roster et joueurs

**Dépendances :** `FEAT-002`, `CNL-004`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Continuité cinq, games communes, changements rôles, force individuelle régularisée, synergies, roster-confidence.
- OE antérieur uniquement.

**DONE quand**

- Une donnée externe roster n’entre jamais.
- Confiance faible est explicite.

**Tests / preuves**

- roster cutoff tests

#### `FEAT-008` — Champion pool et méta

**Dépendances :** `FEAT-002`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Diversité/profondeur champions, performances historiques champion/rôle/patch, adaptation patch, compositions observées.
- Pré-draft uniquement: aucun pick réel futur.

**DONE quand**

- Draft de la game cible absent du feature vector pré-draft.
- Patch inconnu devient incertitude/absence.

**Tests / preuves**

- post-draft leakage fixture

#### `FEAT-009` — Contexte compétition et calendrier

**Dépendances :** `FEAT-002`, `CNL-003`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Ligue/région/tournoi/stage, regular/playoffs/international si déductible OE, BO, jours repos, densité calendrier, patch connu, expérience format.
- Pas d’actualité externe.

**DONE quand**

- Chaque valeur contextuelle a provenance ou unknown.

**Tests / preuves**

- context provenance tests

#### `FEAT-010` — Priors, missingness et cold start

**Dépendances :** `FEAT-003`, `FEAT-004`, `FEAT-005`, `FEAT-006`, `FEAT-007`, `FEAT-008`, `FEAT-009`  
**Traçabilité SFG :** `SFG-TIME-001`, `SFG-ML-004`

**Livrables**

- Priors hiérarchiques ligue/patch, shrinkage petits échantillons, décote ancienneté, indicateurs disponibilité, règles cold start/OOD.
- Transformations fit train-only exposées pour ML.

**DONE quand**

- Jamais null->0 silencieux.
- Cold start peut prédire faible confiance mais ne garantit pas signal.

**Tests / preuves**

- missingness tests
- small-sample shrinkage tests

#### `FEAT-011` — Feature snapshots immuables

**Dépendances :** `FEAT-010`, `OE-011`  
**Traçabilité SFG :** `SFG-ML-003`, `SFG-TIME-001`

**Livrables**

- features.feature_snapshots: cutoff, event, teams, versions, valeurs, missingness, games fingerprint/list, OE snapshot, code commit, leakage checks.
- Hash du vector.

**DONE quand**

- Prediction future pourra référencer exactement un snapshot.
- Snapshot n’est jamais muté.

**Tests / preuves**

- snapshot hash/repro test

#### `FEAT-012` — Invalidation et rebuild ciblés

**Dépendances :** `OE-019`, `FEAT-011`  
**Traçabilité SFG :** `SFG-PAPER-002`, `SFG-ML-003`

**Livrables**

- Queue/marker d’invalidation à partir de min affected date.
- features-rebuild --from.
- Ne modifie jamais feature snapshots déjà référencés par prédictions; produit nouvelles versions si recalcul.

**DONE quand**

- Révision OE déclenche la bonne plage.
- Prédictions passées restent liées à ancien snapshot.

**Tests / preuves**

- retro revision rebuild test

#### `FEAT-013` — Suite anti-leakage

**Dépendances :** `FEAT-011`, `FEAT-012`  
**Traçabilité SFG :** `SFG-TIME-001`

**Livrables**

- Game future injectée, scaler/encoder train-only, agrégats cutoff, max_input_time, révision reçue après prédiction, draft futur.
- Property tests temps.

**DONE quand**

- Toute fuite volontaire fait échouer la suite.
- Cette suite est bloquante en CI.

**Tests / preuves**

- make test-leakage

#### `FEAT-014` — Gate P3 — dataset de features reproductible

**Dépendances :** `FEAT-013`, `CNL-007`  
**Traçabilité SFG :** `SFG-TIME-001`, `SFG-ML-003`

**Livrables**

- Commande features-rebuild.
- Rapport couverture/missingness/cutoff.
- Exemple feature snapshot retraçable.

**DONE quand**

- Depuis prediction candidate/event+cutoff, vector reproductible depuis snapshots versionnés.
- Aucune source autre qu’OE pour stats LoL.

**Tests / preuves**

- rebuild deterministic test

**Interdiction de passage P4 :** aucun entraînement de production tant que la suite anti-leakage n’est pas bloquante et verte.

### P4 — ML game winner et pricing indépendant

Produire des probabilités calibrées, incertaines et reproductibles, sans utiliser la cote comme feature.

#### `ML-001` — Dataset d’entraînement versionné

**Dépendances :** `FEAT-014`  
**Traçabilité SFG :** `SFG-ML-003`, `SFG-DATA-001`

**Livrables**

- ml.datasets avec market, cutoff/exemple, label, feature version, OE snapshots, quality filter, period, competitions, hash, code commit, exclusions.
- Builder game_winner uniquement pour MVP initial.

**DONE quand**

- Dataset hash stable à inputs identiques.
- Labels viennent uniquement d’OE validé.

**Tests / preuves**

- dataset reproducibility tests

#### `ML-002` — Validation walk-forward

**Dépendances :** `ML-001`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-TIME-001`

**Livrables**

- Splits chronologiques train->future val, transformations fit train-only, OOF predictions, final untouched test.
- Découpes/report internationaux et patchs.
- Aucun random split principal.

**DONE quand**

- Le moteur rejette une config de split principal aléatoire.
- Période finale n’est pas utilisée pour tuning seuils.

**Tests / preuves**

- split chronology tests

#### `ML-003` — Baselines prior et forme naïve

**Dépendances :** `ML-002`  
**Traçabilité SFG :** `SFG-ML-002`

**Livrables**

- Prior constant compétition.
- Forme récente naïve.
- Rapport log loss/Brier/calibration.

**DONE quand**

- Les baselines sont enregistrées comme runs comparables.

**Tests / preuves**

- baseline metric tests

#### `ML-004` — Baseline rating game winner

**Dépendances :** `FEAT-003`, `ML-002`  
**Traçabilité SFG :** `SFG-ML-002`

**Livrables**

- Transformer rating pré-game en probabilité auditable.
- Paramètres optimisés uniquement train/validation temporelle.
- Artefact versionné.

**DONE quand**

- Probabilités dans [0,1].
- Résultats reproductibles.

**Tests / preuves**

- probability bounds/property tests

#### `ML-005` — Benchmark gradient boosting

**Dépendances :** `ML-002`, `ML-003`, `ML-004`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-ML-002`

**Livrables**

- Benchmark CatBoost vs LightGBM ou candidat tabulaire prévu par SFG sur mêmes splits/features.
- Choix documenté par métriques/robustesse, pas par préférence.
- CPU MVP.

**DONE quand**

- Le modèle complexe n’est promouvable que s’il justifie son gain vs baselines.
- Hyperparamètres sauvegardés.

**Tests / preuves**

- training smoke deterministic seed

#### `ML-006` — Ensemble candidat

**Dépendances :** `ML-004`, `ML-005`  
**Traçabilité SFG :** `SFG-ML-002`

**Livrables**

- Combinaison rating + tabulaire seulement si validation OOS démontre intérêt.
- Poids entraînés/choisis sur validation, pas test final.

**DONE quand**

- L’ensemble peut être désactivé si aucun gain.
- Décision documentée dans model run.

**Tests / preuves**

- ensemble comparison test

#### `ML-007` — Calibration hors échantillon

**Dépendances :** `ML-004`, `ML-005`, `ML-006`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-ML-003`

**Livrables**

- Platt/isotonic comparés sur prédictions temporelles distinctes.
- Calibrator artifact versionné séparément.
- Reliability, ECE, Brier, log loss, slope/intercept.

**DONE quand**

- Pas de calibrateur fit sur le test final.
- Calibration par segments détecte dérives.

**Tests / preuves**

- calibration leakage tests

#### `ML-008` — Estimation d’incertitude

**Dépendances :** `ML-007`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-ML-004`

**Livrables**

- p50, p_low, p_high, confidence, reasons, data coverage, training-domain distance.
- Méthode choisie entre ensemble/bootstrap temporel/conformal adapté via benchmark documenté.
- Pas de fausse certitude.

**DONE quand**

- p_low <= p50 <= p_high.
- OOD/low coverage réduit confiance ou bloque.

**Tests / preuves**

- interval property tests
- OOD scenario tests

#### `ML-009` — Rapport d’évaluation et segments

**Dépendances :** `ML-007`, `ML-008`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-ML-002`

**Livrables**

- Log loss, Brier, ROC-AUC secondaire, ECE, slope/intercept, sharpness, interval coverage, abstention, ligue/patch/stage/format/bucket odds quand odds existent, outsider robustness, drift.
- Nombre d’observations partout.

**DONE quand**

- Aucune promotion sur accuracy seule.
- Faible sample signalé.

**Tests / preuves**

- metric calculation tests

#### `ML-010` — Model registry et artefacts

**Dépendances :** `ML-009`, `OE-002`  
**Traçabilité SFG :** `SFG-ML-003`

**Livrables**

- ml.model_versions avec algo/hyperparams/feature version/dataset hash/cutoffs/metrics/calibrator/artifact hash/code commit/status/auteur/date/motif.
- ObjectStore model artifacts.
- candidate/champion/retired/blocked.

**DONE quand**

- Un seul champion par jeu/marché/segment.
- Artefact hash vérifié avant chargement.

**Tests / preuves**

- registry DB constraints
- artifact checksum test

#### `ML-011` — Champion/challenger et rollback

**Dépendances :** `ML-010`  
**Traçabilité SFG :** `SFG-ML-002`, `SFG-OPS-001`

**Livrables**

- Promotion manuelle auditée.
- Comparaison baselines.
- Shadow predictions challenger facultatives.
- Rollback immédiat.
- Pas de promotion auto mono-métrique.

**DONE quand**

- Anciennes prédictions gardent ancien model_version.
- Deux champions concurrents interdits.

**Tests / preuves**

- promotion/rollback tests

#### `ML-012` — MarketPlugin GAME_WINNER

**Dépendances :** `ML-011`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`, `SFG-ML-001`

**Livrables**

- Plugin conforme au protocol required capabilities / labels / features / train / predict / price / settle.
- Capability gate lié au modèle champion.

**DONE quand**

- Le plugin reste disabled sans données/modèle valides.
- Probabilités team A+B = 1 tolérance.

**Tests / preuves**

- plugin contract/property tests

#### `ML-013` — Service de prédiction pré-match

**Dépendances :** `ML-012`, `FEAT-011`  
**Traçabilité SFG :** `SFG-ML-003`, `SFG-TIME-001`, `SFG-PAPER-002`

**Livrables**

- Construit feature snapshot au cutoff.
- Charge champion+calibrator.
- Produit prediction append-only avec p50/low/high/version/snapshot/code.
- Refuse cutoff >= event start pour pré-match.

**DONE quand**

- Prediction est immutable.
- Requête répétée peut créer un nouvel instant mais ne réécrit pas l’ancien.

**Tests / preuves**

- prediction reproducibility test

#### `ML-014` — Pricing de série BO1/BO3/BO5 et BO2 conditionnel

**Dépendances :** `ML-013`, `CNL-003`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-MARKET-001`

**Livrables**

- Dériver distribution série depuis proba game et format.
- BO2 trois issues si draw permis.
- Propager incertitude et marginaliser side inconnue.
- Score exact/nb games non activés ici, seulement distribution interne.

**DONE quand**

- Somme issues =1.
- Formats inconnus -> abstention/capability disabled.

**Tests / preuves**

- analytical/simulation property tests

#### `ML-015` — Explications structurées

**Dépendances :** `ML-013`  
**Traçabilité SFG :** `SFG-UX-001`

**Livrables**

- Contributions modèle, facteurs +/- et incertitude via templates structurés.
- SHAP si modèle supporté, étiqueté contribution non cause.
- Aucune narration libre d’absence/fatigue/rumeur.

**DONE quand**

- Chaque phrase se rattache à un champ structuré.
- Missing data affichable.

**Tests / preuves**

- explanation template tests

#### `ML-016` — API/UI modèles, train et promotion réels

**Dépendances :** `ML-011`, `ML-015`, `UI-007`, `MCK-006`  
**Traçabilité SFG :** `SFG-ML-002`, `SFG-ML-003`, `SFG-UX-001`

**Livrables**

- GET models/backtests réels.
- POST train/promote/retire -> jobs/audit.
- Courbes/metrics depuis données réelles.
- Version exacte visible dans prediction.

**DONE quand**

- Même DTO que mock.
- Promotion impossible si gate échoue.

**Tests / preuves**

- API integration
- Playwright model promotion fixture

#### `ML-017` — Gate P4 — cote juste bookmaker-free

**Dépendances :** `ML-016`  
**Traçabilité SFG :** `SFG-ML-001`, `SFG-ML-002`, `SFG-ML-003`, `SFG-ML-004`

**Livrables**

- Commande model-train MARKET=game_winner.
- Rapport walk-forward, calibration et baselines.
- Exemple prediction reproduite depuis model/dataset/feature snapshot.

**DONE quand**

- Game winner champion existe seulement si gates validés.
- Aucune cote bookmaker n’entre comme feature du modèle indépendant.

**Tests / preuves**

- make model-train MARKET=game_winner
- reproduce prediction test

**Interdiction de passage P5/P6 :** une fair odd n’est publiable que par un modèle/version/calibrateur traçable; le bookmaker reste hors features du modèle indépendant.

### P5 — Cotes et résolution d'entités

Recevoir des cotes autorisées, immuables et les mapper sans ambiguïté aux événements LoL.

#### `MAP-001` — Schéma et modèle d’aliases datés

**Dépendances :** `CNL-001`, `ODD-001`  
**Traçabilité SFG :** `SFG-MAP-001`

**Livrables**

- core.entity_aliases: entity_type, canonical_id, provider, raw_alias, normalized_alias, valid_from/to, source, confidence, approved_by/at, notes.
- Unique constraints temporelles cohérentes.

**DONE quand**

- Sponsor/rebranding peut être daté.
- Academy/main non fusionnés automatiquement.

**Tests / preuves**

- alias DB tests

#### `MAP-002` — Normalisation sûre des noms

**Dépendances :** `MAP-001`  
**Traçabilité SFG :** `SFG-MAP-001`

**Livrables**

- Normalisation typographique uniquement: casse/espaces/ponctuation règles explicites.
- Pas de fuzzy auto-merge à lui seul.
- Tests accents/sponsors/academy.

**DONE quand**

- Deux noms proches restent distincts sans alias approuvé.

**Tests / preuves**

- normalization property tests

#### `MAP-003` — Score de matching événement

**Dépendances :** `MAP-002`, `ODD-007`, `CNL-003`  
**Traçabilité SFG :** `SFG-MAP-001`

**Livrables**

- Score équipes 0.60, heure 0.20, compétition 0.15, format 0.05 comme valeurs initiales versionnées.
- Inversion A/B reconnue avec remapping selections.
- TBD/Winner of non résolus.
- Seuils >=.95 auto, .75-.95 review, <.75 reject; proches => review.

**DONE quand**

- Aucune prédiction si ambigu.
- Composantes du score persistées pour audit.

**Tests / preuves**

- mapping score fixtures

#### `MAP-004` — File de revue mapping et actions

**Dépendances :** `MAP-003`, `UI-009`  
**Traçabilité SFG :** `SFG-MAP-001`, `SFG-OPS-001`

**Livrables**

- Persistence pending reviews/candidates.
- Approve/reject/create alias daté.
- Audit complet.
- Impact preview.

**DONE quand**

- Action manuelle ne réécrit pas signaux historiques.
- Plusieurs candidats proches restent review.

**Tests / preuves**

- API/E2E review tests

#### `MAP-005` — Mapping canonique des marchés

**Dépendances :** `ODD-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Mapping par type, période, line, unité, nombre issues, settlement rules, draw, remake/forfeit/void.
- Market rules reference obligatoire pour activation.
- Unknown market stocké brut.

**DONE quand**

- Un libellé seul ne suffit jamais.
- Marché inconnu ne déclenche aucune prediction.

**Tests / preuves**

- market mapping fixtures

#### `MAP-006` — Gate P5 — événement coté résolu

**Dépendances :** `ODD-009`, `MAP-004`, `MAP-005`  
**Traçabilité SFG :** `SFG-ODDS-001`, `SFG-ODDS-002`, `SFG-MAP-001`, `SFG-PRICE-002`

**Livrables**

- Parcours mock/manual import -> event -> odds history -> mapping.
- UI mapping branchée réel.
- Contract test providers.

**DONE quand**

- Un événement ambigu n’atteint pas pricing.
- Les snapshots sont horodatés/immutables.

**Tests / preuves**

- integration odds->mapping

#### `ODD-001` — Schéma odds append-only

**Dépendances :** `FND-004`, `MCK-001`  
**Traçabilité SFG :** `SFG-PRICE-002`, `SFG-ODDS-001`

**Livrables**

- odds.providers, events, markets, selections, snapshots, raw payload reference minimal, provider health.
- captured_at obligatoire pour signal validé.
- Decimal odds positive constraints.

**DONE quand**

- Aucune UPDATE d’un snapshot de cote.
- Index event/market/selection/captured_at.
- Cote sans timestamp fiable marquée informational_only.

**Tests / preuves**

- immutability DB tests

#### `ODD-002` — Contrat OddsProvider

**Dépendances :** `ODD-001`  
**Traçabilité SFG :** `SFG-ODDS-001`

**Livrables**

- Protocol list_events/get_event_markets/capture_snapshot/health.
- ProviderEvent/Market/Selection normalisés.
- Aucun domaine ne dépend d’un provider concret.

**DONE quand**

- Contract test réutilisable par tous providers.

**Tests / preuves**

- provider contract suite

#### `ODD-003` — MockOddsProvider réel du contrat

**Dépendances :** `ODD-002`, `MCK-003`  
**Traçabilité SFG :** `SFG-ODDS-001`, `SFG-MOCK-001`

**Livrables**

- Adapter les scénarios existants au vrai protocol.
- Clock injectable pour odds changes/stale.
- Aucun réseau.

**DONE quand**

- Passe exactement la même contract suite que les autres providers.

**Tests / preuves**

- provider contract suite mock

#### `ODD-004` — ManualImportOddsProvider

**Dépendances :** `ODD-002`  
**Traçabilité SFG :** `SFG-ODDS-001`, `SFG-PRICE-002`

**Livrables**

- Import CSV/JSON strict: provider logique, event, start, market, selection, decimal odds, captured_at, provenance ref.
- Validation erreurs par ligne et transaction contrôlée.

**DONE quand**

- Cote sans captured_at fiable ne peut générer signal validé.
- Import idempotent selon clé documentée.

**Tests / preuves**

- valid/invalid/import duplicate tests

#### `ODD-005` — LicensedOddsFeedProvider boundary

**Dépendances :** `ODD-002`  
**Traçabilité SFG :** `SFG-ODDS-001`

**Livrables**

- Interface/adaptateur abstrait et config pour futur flux contractuel.
- Aucun faux endpoint, aucune clé inventée.
- Documentation d’implémentation future.

**DONE quand**

- Le produit compile/fonctionne sans provider licencié concret.

**Tests / preuves**

- contract test skeleton

#### `ODD-006` — StakeAuthorizedProvider désactivé

**Dépendances :** `ODD-002`  
**Traçabilité SFG :** `SFG-ODDS-002`, `SFG-COMP-002`

**Livrables**

- Squelette explicite DisabledProvider/feature flag.
- Message expliquant que l’autorisation écrite et validation juridique sont requises.
- Aucun scraper, endpoint privé, CAPTCHA, proxy, cookie bookmaker, geobypass ou automatisation de mise.

**DONE quand**

- Impossible de l’activer sans flag de conformité et implémentation autorisée future.
- Recherche statique CI interdit patterns de contournement documentés si pertinent.

**Tests / preuves**

- startup disabled test
- repository compliance scan

#### `ODD-007` — Capture et historisation des cotes

**Dépendances :** `ODD-003`, `ODD-004`  
**Traçabilité SFG :** `SFG-PRICE-002`

**Livrables**

- Append-only capture.
- Nouvelle observation sur changement cote/status/line/name ou confirmation.
- Déduplication physique optionnelle tout en préservant intervalle observé.
- Lien provider event/market/selection.

**DONE quand**

- Historique reconstructible.
- Aucune dernière cote n’écrase l’ancienne.

**Tests / preuves**

- odds history tests

#### `ODD-008` — Fraîcheur et admissibilité de marché

**Dépendances :** `ODD-007`  
**Traçabilité SFG :** `SFG-PRICE-003`

**Livrables**

- ODDS_MAX_AGE_SECONDS configurable provider/market/phase.
- Block stale, started pre-match, suspended/closed, selection missing, incomplete outcomes pour no-vig, temporal order invalid.
- Live betting hors MVP.

**DONE quand**

- Un snapshot devenu stale ne reste pas signalable.
- Status open requis.

**Tests / preuves**

- stale/start/suspended tests

#### `ODD-009` — Health provider et API odds history

**Dépendances :** `ODD-008`, `MCK-005`  
**Traçabilité SFG :** `SFG-UX-001`

**Livrables**

- Provider health, last capture, age, failures.
- GET event odds-history réel.
- Fraîcheur exposée.

**DONE quand**

- Erreur provider n’efface pas l’historique existant.

**Tests / preuves**

- API odds history tests

### P6 — Value engine et opportunités

Comparer prix modèle et prix marché, appliquer les garde-fous et accepter l'abstention.

#### `VAL-001` — Probabilité implicite et no-vig

**Dépendances :** `MAP-005`  
**Traçabilité SFG :** `SFG-PRICE-001`

**Livrables**

- q=1/O.
- Normalisation q_i/sum(q) pour issues mutuellement exclusives exhaustives.
- Stratégie no-vig versionnée.
- Refus si marché incomplet sauf stratégie explicitement compatible.

**DONE quand**

- Somme no-vig =1 tolérance.
- Cotes invalides refusées.

**Tests / preuves**

- hand-calculated unit tests
- property tests

#### `VAL-002` — Cote juste, edge, EV et EV prudente

**Dépendances :** `ML-013`, `VAL-001`  
**Traçabilité SFG :** `SFG-PRICE-001`

**Livrables**

- fair_odds=1/p_model, edge=p_model-p_book_no_vig, EV=p_model*O-1, conservative EV=p_low*O-1.
- Gestion limites p=0/1 selon politique numérique explicite.

**DONE quand**

- Exemple SFG cote 4.00 reproduit.
- Formules testées cas limites.

**Tests / preuves**

- golden numeric tests

#### `VAL-003` — Configuration versionnée des seuils

**Dépendances :** `FND-003`, `VAL-002`  
**Traçabilité SFG :** `SFG-OPS-001`, `SFG-PRICE-001`

**Livrables**

- min_edge/min_ev/min_conservative_ev/max_odds_age/min_mapping confidence, overrides market/competition/bucket.
- Version de policy persistée.
- Aucun tuning sur période test finale.

**DONE quand**

- Chaque signal référence policy version.
- Changement seuil audité.

**Tests / preuves**

- policy version tests

#### `VAL-004` — Garde-fous d’admission

**Dépendances :** `ODD-008`, `MAP-003`, `ML-011`, `CNL-006`, `VAL-003`  
**Traçabilité SFG :** `SFG-PRICE-003`, `SFG-MARKET-001`, `SFG-MAP-001`

**Livrables**

- Check edge, EV, conservative EV, mapping confidence, odds age, champion, source quality, market open, prediction cutoff<start, capability enabled.
- Ordre de checks déterministe.

**DONE quand**

- Un seul échec bloquant suffit à empêcher opportunity.
- Market stale/suspended/started ne passe jamais.

**Tests / preuves**

- guard matrix tests

#### `VAL-005` — Abstention de première classe

**Dépendances :** `VAL-004`, `ML-008`  
**Traçabilité SFG :** `SFG-ML-004`, `SFG-UX-001`

**Livrables**

- Enum complet SFG: ODDS_STALE, MARKET_SUSPENDED, EVENT_MAPPING_AMBIGUOUS, INSUFFICIENT_HISTORY, ROSTER_UNCERTAIN, SOURCE_STALE, MODEL_STALE, OUT_OF_DISTRIBUTION, CALIBRATION_FAILED, EDGE_TOO_SMALL, CONSERVATIVE_EV_NEGATIVE, MARKET_RULES_UNKNOWN, PATCH_CONTEXT_UNKNOWN, EVENT_ALREADY_STARTED, CAPABILITY_DISABLED.
- Plusieurs raisons possibles ordonnées.

**DONE quand**

- Aucune absence de value n’est représentée comme erreur système.
- UI montre les raisons.

**Tests / preuves**

- abstention scenario tests

#### `VAL-006` — Persistence append-only predictions/signals

**Dépendances :** `ML-013`, `VAL-005`, `ODD-007`  
**Traçabilité SFG :** `SFG-PRICE-002`, `SFG-PAPER-002`

**Livrables**

- ml.predictions immutable si pas déjà.
- signals.signals append-only avec odds_snapshot_id, prediction_id, policy_version, computed_at, grades VALUE/STRONG_VALUE/WATCH/NO_EDGE/BLOCKED.
- Jamais de réécriture après résultat.

**DONE quand**

- DB empêche update métier ou application n’expose aucune mutation; audit technique si correction administrative exceptionnelle.
- Chaque signal reproduit inputs exacts.

**Tests / preuves**

- immutability tests
- reproduction test

#### `VAL-007` — Projection Opportunités et APIs réelles

**Dépendances :** `VAL-006`, `MCK-005`, `UI-004`, `UI-006`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-UX-001`

**Livrables**

- GET opportunities/detail/explanation sur signaux réels admissibles.
- Filtres SFG.
- Tri EV prudente défaut.
- Freshness/model/data quality visibles.

**DONE quand**

- NO_EDGE/BLOCKED ne sont pas comptés comme opportunités mais restent consultables selon écran diagnostic.
- DTO identique mock.

**Tests / preuves**

- API/UI contract tests

#### `VAL-008` — Gestion changement de cote en UI

**Dépendances :** `ODD-007`, `VAL-006`, `UI-004`, `UI-005`  
**Traçabilité SFG :** `SFG-UX-002`, `SFG-PRICE-002`

**Livrables**

- Polling/refetch raisonné ou mécanisme simple; pas d’infra streaming lourde sans besoin.
- Nouvelle cote crée nouveau snapshot/signal si recalcul.
- La fiche ouverte ne réécrit pas silencieusement l’ancien signal.
- Indicateur “cote mise à jour”.

**DONE quand**

- Zéro flicker/layout rebuild de ligne.
- Ancien snapshot reste consultable.

**Tests / preuves**

- Playwright odds change

#### `VAL-009` — Gate P6 — signal value complet

**Dépendances :** `VAL-007`, `VAL-008`  
**Traçabilité SFG :** `SFG-PRICE-001`, `SFG-PRICE-002`, `SFG-PRICE-003`, `SFG-ML-004`, `SFG-MAP-001`

**Livrables**

- Parcours: event mappé + prediction + odds -> no-vig -> value -> grade/abstention -> UI.
- Rapport numérique de référence.
- Cas outsider cote élevée.

**DONE quand**

- Aucune promesse de gain.
- Exemple calculable manuellement.
- Ambigu/stale/suspended bloqués.

**Tests / preuves**

- integration odds->mapping->prediction->signal
- Playwright opportunities

### P7 — Paper trading et règlement

Mesurer honnêtement les performances à partir de cotes réellement observées.

#### `PAP-001` — Schéma Paper Ledger

**Dépendances :** `VAL-006`, `FND-004`  
**Traçabilité SFG :** `SFG-PAPER-001`, `SFG-PAPER-002`

**Livrables**

- signals.paper_bets, settlements, bankroll/exposure optional config.
- Référence signal+odds snapshot+policy/model au moment de décision.
- Append-only décisions/settlements.

**DONE quand**

- Impossible de créer paper bet sur une cote non horodatée.
- Signal historique ne change pas.

**Tests / preuves**

- DB constraints

#### `PAP-002` — Création contrôlée de paper bets

**Dépendances :** `PAP-001`, `VAL-005`  
**Traçabilité SFG :** `SFG-PAPER-002`

**Livrables**

- Création manuelle depuis signal.
- Auto-paper optionnel uniquement selon policy si voulu par SFG, jamais pari réel.
- Idempotency key.
- Bankroll fictive.

**DONE quand**

- WATCH/BLOCKED masquent suggestion de mise.
- Aucune API bookmaker d’exécution.

**Tests / preuves**

- paper create tests

#### `PAP-003` — Settlement GAME_WINNER

**Dépendances :** `ML-012`, `PAP-001`, `CNL-002`  
**Traçabilité SFG :** `SFG-PAPER-001`, `SFG-MARKET-001`

**Livrables**

- settle win/loss, remake/forfeit/void selon règles référencées.
- Résultat OE validé requis.
- Ambigu => pending_review.

**DONE quand**

- Aucun settlement inventé si règles inconnues.
- Idempotent.

**Tests / preuves**

- settlement fixtures

#### `PAP-004` — Settlement SERIES_WINNER

**Dépendances :** `ML-014`, `PAP-001`, `CNL-003`  
**Traçabilité SFG :** `SFG-PAPER-001`, `SFG-MARKET-001`

**Livrables**

- Win/loss/draw si marché le permet, cancelled/format change/pending review.
- Règles du marché provider référencées.

**DONE quand**

- Score/résultat core ambigu => pending_review.

**Tests / preuves**

- series settlement tests

#### `PAP-005` — Job de règlement depuis OE

**Dépendances :** `PAP-003`, `PAP-004`, `OE-020`  
**Traçabilité SFG :** `SFG-PAPER-001`, `SFG-OPS-001`

**Livrables**

- Recherche résultats OE validés après event.
- Délai configurable avant final settlement.
- Retries bornés.
- Audit.

**DONE quand**

- Source stale n’invente pas résultat.
- Settlement définitif seulement sur données suffisantes.

**Tests / preuves**

- result arrival tests

#### `PAP-006` — Closing line proxy et CLV

**Dépendances :** `ODD-007`, `PAP-001`  
**Traçabilité SFG :** `SFG-PAPER-001`

**Livrables**

- Dernier snapshot pré-start disponible comme approximation closing line.
- Marquer explicitement proxy.
- CLV avec méthode documentée.
- Pas de reconstruction d’odds manquantes.

**DONE quand**

- Aucune cote actuelle utilisée rétroactivement.
- Absence closing snapshot => CLV unavailable.

**Tests / preuves**

- CLV fixture tests

#### `PAP-007` — Métriques financières honnêtes

**Dépendances :** `PAP-005`, `PAP-006`  
**Traçabilité SFG :** `SFG-PAPER-001`

**Livrables**

- Signals/bets, turnover, P&L, ROI/yield, CLV, hit rate contextualisé, max drawdown, volatility, block-bootstrap CI, segments, exposure/correlation, void rate, EV announced vs realized.
- Sample size partout.

**DONE quand**

- Métriques utilisent uniquement paper bets issus de cotes réellement observées.
- Aucun backtest financier fabriqué depuis OE seul.

**Tests / preuves**

- small ledger hand-check tests

#### `PAP-008` — Anti-biais et immutabilité reporting

**Dépendances :** `PAP-007`  
**Traçabilité SFG :** `SFG-PAPER-002`

**Livrables**

- Inclure pertes, opportunités non prises selon policy, slippage, odds changes.
- Aucune suppression signal après résultat.
- Seuils non optimisés sur test final.

**DONE quand**

- Historique complet reconstructible.
- Audit des corrections manuelles.

**Tests / preuves**

- immutability/report completeness tests

#### `PAP-009` — UI/API paper trading réels

**Dépendances :** `PAP-008`, `UI-010`  
**Traçabilité SFG :** `SFG-MOCK-001`, `SFG-UX-001`

**Livrables**

- GET/POST paper-bets, detail, admin settle.
- Dashboard métriques/CLV.
- pending_review visible.
- Suggestion Kelly facultative désactivée par défaut et fondée p_low si activée.

**DONE quand**

- Aucun bouton mise bookmaker.
- Les pertes visibles.
- DTO mock/real identique.

**Tests / preuves**

- Playwright paper real-fixture

#### `PAP-010` — Gate P7 — validation financière live-from-go-live

**Dépendances :** `PAP-009`  
**Traçabilité SFG :** `SFG-PAPER-001`, `SFG-PAPER-002`

**Livrables**

- Documentation “ce qui est et n’est pas un backtest financier”.
- Commande paper-settle.
- Rapport exemple avec historique odds observé.

**DONE quand**

- Impossible d’afficher ROI historique sans odds snapshots réels correspondants.
- Décisions immuables.

**Tests / preuves**

- integration capture->signal->paper->result->settle

### P8 — Operations et sécurité

Fiabiliser jobs, audit, sauvegarde, restauration, sécurité réseau et observabilité.

#### `OPS-001` — Table jobs et worker PostgreSQL

**Dépendances :** `FND-008`, `FND-004`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- ops.jobs: type, payload, status, attempts, scheduled/started/finished, heartbeat, error code, cancellation, idempotency key.
- Worker claim transactionnel.

**DONE quand**

- Un job n’est exécuté que par un worker à la fois.
- Crash laisse job récupérable.

**Tests / preuves**

- concurrency tests

#### `OPS-002` — Advisory locks et unicité métier

**Dépendances :** `OPS-001`, `OE-021`  
**Traçabilité SFG :** `SFG-OPS-001`, `SFG-DATA-004`

**Livrables**

- Locks provider/year pour sync, market/model pour train/promotion si nécessaire, settlement scoped.
- Timeout et libération safe.

**DONE quand**

- Deux sync même année ne s’exécutent pas simultanément.
- Lock mort récupérable.

**Tests / preuves**

- concurrent worker tests

#### `OPS-003` — Retries, reprise et annulation

**Dépendances :** `OPS-001`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- Retry policy par type erreur.
- Heartbeat/lease.
- Cancel controlled.
- Dead/failed states et rerun explicite.

**DONE quand**

- Aucun retry infini.
- Erreur permanente finit failed.

**Tests / preuves**

- retry/cancel/recovery tests

#### `OPS-004` — Planification

**Dépendances :** `OPS-002`, `OPS-003`  
**Traçabilité SFG :** `SFG-INFRA-001`, `SFG-OPS-001`

**Livrables**

- Année courante OE toutes les 3h configurable.
- Retry 10m/30m/2h+jitter.
- Audit années closes mensuel, deep control quotidien après modif.
- Paper settlement schedule.
- Implémentation simple worker/DB/cron interne approprié; pas Airflow.

**DONE quand**

- Fréquences configurables.
- Un seul job par année.

**Tests / preuves**

- scheduler unit tests

#### `OPS-005` — Audit immuable

**Dépendances :** `FND-006`, `OPS-001`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- ops.audit_events append-only.
- Sync/quarantine/promotion alias/model threshold/paper/provider/mode/auth/admin.
- Actor, action, target, before/after refs non sensibles, trace_id.

**DONE quand**

- Chaque action admin critique crée un audit.
- Audit non modifiable via API.

**Tests / preuves**

- audit coverage tests

#### `OPS-006` — System status et observabilité

**Dépendances :** `OE-020`, `ODD-009`, `ML-011`, `OPS-001`  
**Traçabilité SFG :** `SFG-OPS-001`, `SFG-SEC-001`

**Livrables**

- Status source freshness, model freshness, mapping backlog, jobs, backups.
- Logs JSON trace_id/job_id/snapshot/model.
- Metrics durée jobs, failures, rows, anomalies, API latency, signals.
- Traces ingestion/pricing si instrumentation légère disponible.

**DONE quand**

- Aucun secret dans logs.
- External source degraded n’implique pas read unavailable si snapshot valide.

**Tests / preuves**

- log redaction tests
- status API tests

#### `OPS-007` — Alertes

**Dépendances :** `OPS-006`  
**Traçabilité SFG :** `SFG-OPS-001`

**Livrables**

- Alert rules source stale, model stale, mapping backlog, DQ blocking, backup failure.
- Canal local/log au MVP; intégration externe facultative future.
- Dedup/cooldown.

**DONE quand**

- Alerte non spammy et testable.
- Pas de dépendance SaaS obligatoire.

**Tests / preuves**

- alert rule tests

#### `OPS-008` — Sauvegardes

**Dépendances :** `FND-005`, `OE-002`, `ML-010`  
**Traçabilité SFG :** `SFG-OPS-002`

**Livrables**

- Dump PostgreSQL cohérent, copie objets immuables, rétention configurable, manifest backup, chiffrement si externe.
- Commande backup.

**DONE quand**

- Backup contient DB+raw+models nécessaires.
- Échec est visible/alertable.

**Tests / preuves**

- backup smoke test

#### `OPS-009` — Restauration et reconstruction

**Dépendances :** `OPS-008`, `OE-025`  
**Traçabilité SFG :** `SFG-OPS-002`

**Livrables**

- Commande restore sur environnement test.
- Procédure DB + objects.
- Procédure rebuild canonical depuis raw.
- Validation checksums.

**DONE quand**

- Un exercice de restauration automatisé/manuel documenté réussit.
- Raw permet reconstruction canonique.

**Tests / preuves**

- restore drill CI/nightly optional

#### `OPS-010` — Gate P8 — exploitation fiable

**Dépendances :** `OPS-009`, `SEC-005`, `OPS-007`  
**Traçabilité SFG :** `SFG-OPS-001`, `SFG-OPS-002`, `SFG-SEC-001`

**Livrables**

- Runbook startup/update/backup/restore/incidents.
- Migration dry-run sur copie avant prod.
- Graceful shutdown worker/API.
- Status page admin.

**DONE quand**

- Backup+restore testés.
- Jobs/audit visibles.
- Aucun secret loggé.

**Tests / preuves**

- ops smoke suite

#### `SEC-001` — Garde AUTH_MODE

**Dépendances :** `FND-003`, `FND-007`  
**Traçabilité SFG :** `SFG-SEC-001`

**Livrables**

- AUTH_MODE=disabled autorisé seulement localhost/réseau privé explicitement configuré.
- Refus de démarrage exposé publiquement sans auth.

**DONE quand**

- Configuration publique+auth disabled échoue.

**Tests / preuves**

- startup security tests

#### `SEC-002` — Compte Owner et sessions

**Dépendances :** `SEC-001`, `FND-004`  
**Traçabilité SFG :** `SFG-SEC-001`

**Livrables**

- Bootstrap owner CLI.
- Session cookie HTTP-only/Secure/SameSite en réseau.
- Rotation session.
- Password hashing moderne choisi via bibliothèque maintenue.

**DONE quand**

- Mot de passe jamais stocké/loggé clair.
- Session invalidée/rotée selon policy.

**Tests / preuves**

- auth integration tests

#### `SEC-003` — Protection HTTP

**Dépendances :** `SEC-002`  
**Traçabilité SFG :** `SFG-SEC-001`

**Livrables**

- Validation inputs, CSRF mutations, CSP, headers sécurité, rate limit endpoints sensibles, CORS fermé.
- Erreurs sans fuite stack/secrets en production.

**DONE quand**

- Tests CSRF/CORS/rate-limit.
- CSP n’empêche pas UI attendue.

**Tests / preuves**

- security integration tests

#### `SEC-004` — Secrets et conteneurs

**Dépendances :** `FND-005`, `OE-006`, `ODD-005`  
**Traçabilité SFG :** `SFG-SEC-001`

**Livrables**

- .env non commité, secrets serveur uniquement, aucun token frontend, redaction logs, Docker secrets/manager en prod, non-root, volumes readonly sauf besoin.
- Payloads bruts sensibles minimisés/chiffrés si requis.

**DONE quand**

- Scan repo ne trouve pas credentials.
- Frontend bundle ne contient pas secrets serveur.

**Tests / preuves**

- secret scan
- container user/permissions tests

#### `SEC-005` — Scans CI sécurité

**Dépendances :** `FND-010`, `SEC-004`  
**Traçabilité SFG :** `SFG-SEC-001`

**Livrables**

- Dependency scan frontend/Python, image scan, secret scan.
- Policy de mise à jour contrôlée.

**DONE quand**

- Vulnérabilité critique non acceptée bloque release selon policy.
- Exceptions documentées.

**Tests / preuves**

- CI scan jobs

### P9 — Durcissement et recette MVP

Prouver que la Definition of Done de la SFG est satisfaite de bout en bout.

#### `QA-001` — Performance API et N+1

**Dépendances :** `VAL-007`, `PAP-009`, `OPS-006`  
**Traçabilité SFG :** `SFG-UX-002`

**Livrables**

- Bench pages/endpoints courants.
- p95 cible <300ms hors réseau externe sur machine de référence documentée.
- Pagination histories.
- Indexes/query plans.
- Pas de calcul lourd web.

**DONE quand**

- Aucune N+1 connue.
- Machine/scénario benchmark documentés.

**Tests / preuves**

- load smoke benchmark
- query count tests

#### `QA-002` — Stabilité visuelle et régression

**Dépendances :** `UI-011`, `VAL-008`  
**Traçabilité SFG :** `SFG-UX-002`

**Livrables**

- Visual regression desktop/mobile.
- Mesure CLS <0.05 pages clés scénario.
- Console error/hydration warning fail.
- Theme flash check.
- Graphs/skeleton dimensions.

**DONE quand**

- Zéro erreur console/hydratation sur parcours clés.
- Animations annulables et reduced motion.

**Tests / preuves**

- Playwright visual suite

#### `QA-003` — Accessibilité complète

**Dépendances :** `UI-011`  
**Traçabilité SFG :** `SFG-UX-003`

**Livrables**

- Navigation clavier tous parcours critiques.
- WCAG AA contrast.
- Semantic tables/labels.
- aria-live odds.
- Text summaries charts.

**DONE quand**

- Aucune fonctionnalité critique souris-only.
- Information jamais couleur-only.

**Tests / preuves**

- automated a11y + manual keyboard checklist

#### `QA-004` — Résilience réseau et erreurs

**Dépendances :** `MCK-007`, `OE-023`, `ODD-009`, `OPS-006`  
**Traçabilité SFG :** `SFG-UX-002`, `SFG-OPS-001`

**Livrables**

- Tests offline/reconnect, timeout provider, DB transient, source stale, last snapshot read.
- UI recoverable/blocking distinction.

**DONE quand**

- Aucun écran blanc/spinner infini.
- Dernier état sûr reste visible si autorisé.

**Tests / preuves**

- Playwright network fault suite

#### `QA-005` — CI complète normative

**Dépendances :** `OE-024`, `FEAT-013`, `ML-017`, `VAL-009`, `PAP-010`, `OPS-010`, `QA-002`, `QA-003`  
**Traçabilité SFG :** `SFG-TIME-001`, `SFG-SEC-001`, `SFG-UX-002`

**Livrables**

- format/lint frontend, TS strict, Python lint/typecheck, unit/property, migrations, ingestion, model determinism, OpenAPI compatibility, Playwright mock, visual, Docker build, security scans.
- Temporalité, settlement, migration, ingestion = hard blockers.

**DONE quand**

- Pipeline verte sur commit de release.
- Un test critique forcé en échec bloque le pipeline.

**Tests / preuves**

- full CI

#### `QA-006` — Checklist conformité et release gates

**Dépendances :** `ODD-006`, `OPS-005`  
**Traçabilité SFG :** `SFG-COMP-001`, `SFG-COMP-002`, `SFG-ODDS-002`

**Livrables**

- Flags OE-COMMERCIAL=NO-GO, RIOT-PRODUCT=NO-GO, Stake provider disabled par défaut.
- Checklist sources externes à revalider avant lancement.
- Aucun marketing/“garanti/lock”.

**DONE quand**

- Build personnel fonctionne avec gates NO-GO.
- Release publique/commerciale bloquée tant que gates non levés manuellement avec preuve.

**Tests / preuves**

- release gate tests/config assertions

#### `QA-007` — Recette Definition of Done MVP

**Dépendances :** `QA-001`, `QA-004`, `QA-005`, `QA-006`  
**Traçabilité SFG :** `SFG-DATA-001`, `SFG-DATA-002`, `SFG-DATA-003`, `SFG-DATA-004`, `SFG-DATA-005`, `SFG-DATA-006`, `SFG-DATA-007`, `SFG-DATA-008`, `SFG-TIME-001`, `SFG-ML-001`, `SFG-ML-002`, `SFG-ML-003`, `SFG-ML-004`, `SFG-PRICE-001`, `SFG-PRICE-002`, `SFG-PRICE-003`, `SFG-ODDS-001`, `SFG-ODDS-002`, `SFG-MAP-001`, `SFG-MARKET-001`, `SFG-PAPER-001`, `SFG-PAPER-002`, `SFG-MOCK-001`, `SFG-MOCK-002`, `SFG-UX-001`, `SFG-UX-002`, `SFG-UX-003`, `SFG-OPS-001`, `SFG-OPS-002`, `SFG-SEC-001`, `SFG-COMP-001`, `SFG-COMP-002`, `SFG-INFRA-001`

**Livrables**

- Checklist automatisée + manuelle des 22 points SFG §31.
- Rapport avec PASS/FAIL, commandes, preuves et versions.
- Aucun TODO/PASS simulé.

**DONE quand**

- Les 22 critères passent ou le MVP reste non terminé.
- Rapport archivé par release.

**Tests / preuves**

- make acceptance

### P10 — Marchés LoL supplémentaires

Ajouter les marchés uniquement derrière le capability registry et après validation statistique.

#### `MRK-001` — Plugin total kills

**Dépendances :** `QA-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Label OE capability-gated.
- Distribution de total.
- P(over/under line), settlement et calibration par lines.

**DONE quand**

- Activation seulement après checklist Annexe B.

**Tests / preuves**

- market plugin + walk-forward + settlement

#### `MRK-002` — Plugin kill handicap

**Dépendances :** `QA-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Distribution différence kills.
- P(diff > handicap) et settlement.

**DONE quand**

- Pas de modèle binaire séparé par ligne si distribution cohérente validée.

**Tests / preuves**

- distribution/settlement tests

#### `MRK-003` — Plugin durée de game

**Dépendances :** `QA-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Distribution durée.
- Over/under et settlement selon rules.

**DONE quand**

- Capability et sample gates passés.

**Tests / preuves**

- market validation

#### `MRK-004` — Premiers objectifs conditionnels

**Dépendances :** `QA-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- First blood/tower/dragon/herald/baron séparés.
- Bernoulli calibré seulement si labels OE complets et définitions provider équivalentes.

**DONE quand**

- Une définition différente provider vs OE bloque.
- Remakes/incomplete filtrés.

**Tests / preuves**

- label equivalence + calibration + settlement

#### `MRK-005` — Totaux objectifs

**Dépendances :** `QA-007`, `CNL-006`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Total towers/dragons si capability.
- Distribution et settlement.

**DONE quand**

- Activation checklist complète.

**Tests / preuves**

- market validation

#### `MRK-006` — Score exact et nombre de games

**Dépendances :** `ML-014`, `QA-007`  
**Traçabilité SFG :** `SFG-MARKET-001`

**Livrables**

- Prix dérivé de distribution série.
- Somme issues =1.
- Règles BO/void explicites.

**DONE quand**

- Pas de modèle incohérent indépendant si distribution série suffit.

**Tests / preuves**

- probability sum + settlement tests

#### `MRK-007` — Gate d’activation par marché

**Dépendances :** `MRK-001`, `MRK-002`, `MRK-003`, `MRK-004`, `MRK-005`, `MRK-006`  
**Traçabilité SFG :** `SFG-MARKET-001`, `SFG-OPS-001`

**Livrables**

- Implémenter Annexe B comme checklist/versioned approval record.
- UI matrix capacités.
- Aucun market enabled par simple présence provider.

**DONE quand**

- Tous les items requis doivent être true/approved.
- Décision auditée.

**Tests / preuves**

- capability activation tests

### P11 — SaaS et multi-jeux — bloqués

Préparer les extensions sans les activer avant levée des portes conformité/licence.

#### `EXT-001` — Extraire GameAdapter seulement quand LoL MVP stable

**Dépendances :** `QA-007`  
**Traçabilité SFG :** `SFG-EXT-001`

**Livrables**

- Protocol GameAdapter conforme SFG.
- Réutiliser odds/value/UI/auth/jobs/audit/paper; logique LoL reste dans adapter/modules LoL.
- Pas de modèle universel rempli de nulls.

**DONE quand**

- Tests architecture adapter sans changer comportement LoL.

**Tests / preuves**

- architecture tests

#### `EXT-002` — CS2 et Dota 2 — sources distinctes et droits distincts

**Dépendances :** `EXT-001`, `GATE-001`  
**Traçabilité SFG :** `SFG-EXT-001`

**Livrables**

- Backlog de source statistique/licence par jeu, canonical adapter, features, market plugins, settlement, calibration.
- Ne jamais réutiliser Oracle’s Elixir comme source CS2/Dota.

**DONE quand**

- Aucun nouveau jeu activé sans source/droits/validation propres.

**Tests / preuves**

- N/A avant décision

#### `GATE-001` — Conserver les portes SaaS bloquantes

**Dépendances :** `QA-006`  
**Traçabilité SFG :** `SFG-COMP-001`, `SFG-COMP-002`

**Livrables**

- Registre compliance decisions avec source/date/owner/status.
- OE commercial, Riot product, provider odds.
- Pas d’automatisation de décision juridique.

**DONE quand**

- NO-GO empêche profile/public commercial release.

**Tests / preuves**

- release gate tests

#### `SAAS-001` — Multi-user/RBAC/abonnements — non implémenté avant GO

**Dépendances :** `GATE-001`  
**Traçabilité SFG :** `SFG-COMP-001`, `SFG-COMP-002`

**Livrables**

- Backlog documenté seulement: users, Admin/Analyst/Subscriber/ReadOnly, tenancy, billing, quotas, privacy, support.
- Aucun code complexe prématuré dans MVP personnel.

**DONE quand**

- Ticket reste blocked tant que gates NO-GO.

**Tests / preuves**

- N/A avant GO

**Phase bloquée :** ces tickets ne constituent pas une autorisation juridique ou contractuelle. `SAAS-001` et `EXT-002` restent bloqués tant que les portes ne sont pas levées.

## 7. Gates de promotion d’un modèle game winner

Codex doit implémenter un rapport de promotion qui répond au minimum à :

- dataset et feature set versionnés et hashés ;
- validation principale walk-forward ;
- période finale de test intacte ;
- comparaison prior constant, forme naïve, rating baseline ;
- log loss et Brier ;
- calibration ECE + slope/intercept + reliability ;
- résultats par ligue/patch/stage/format et faible-échantillon explicite ;
- tests anti-leakage verts ;
- artifact/calibrator hashes valides ;
- motif de promotion humain/audité ;
- rollback possible.

Le benchmark peut conclure que le modèle simple est meilleur. Dans ce cas, il faut conserver le modèle simple; il est interdit de promouvoir un modèle plus complexe pour “faire plus IA”.

## 8. Gates d’activation d’un marché

Reprendre l’Annexe B de la SFG comme checklist réellement versionnée : label reconstructible OE, équivalence exacte provider, settlement rules, complétude, sample, walk-forward, calibration, baseline, leakage, mapping, odds fresh, seuils hors final-test, settlement tests, UI incertitude, droits provider.

## 9. Commandes finales attendues

Les noms exacts de scripts internes peuvent évoluer, mais ces interfaces opératoires doivent exister :

```bash
make up
make down
make db-migrate
make lint
make typecheck
make test
make test-e2e
make oe-catalog
make oe-backfill FROM=2014 TO=2026
make oe-sync YEAR=2026
make oe-sync-current REQUIRE_FRESH=1
make oe-validate SNAPSHOT=<snapshot_id>
make oe-diff LEFT=<snapshot_id> RIGHT=<snapshot_id>
make oe-rebuild-canonical FROM=<YYYY-MM-DD>
make features-rebuild FROM=<YYYY-MM-DD>
make model-train MARKET=game_winner
make paper-settle
make backup
make restore-check
make acceptance
```

## 10. Ce que Codex ne doit pas “compléter” de sa propre initiative

- pas de news, blessures, rumeurs, social media ou données roster externes ;
- pas de Riot API comme seconde source de statistiques LoL ;
- pas d’historique de cotes reconstitué ;
- pas de betting live au MVP ;
- pas de mise réelle ou de connexion compte bookmaker ;
- pas de Stake scraping ;
- pas de features post-draft dans le modèle pré-draft ;
- pas d’accuracy comme métrique de promotion principale ;
- pas de split aléatoire principal ;
- pas de réécriture des prédictions/signaux historiques après correction OE ;
- pas de marché activé uniquement parce qu’un bookmaker l’affiche ;
- pas de billing/multitenancy/RBAC complet avant les gates SaaS ;
- pas de CS2/Dota sans source propre et droits propres.

## 11. Procédure de travail recommandée dans Codex

Pour chaque ticket :

1. Lire le ticket et ses dépendances.
2. Inspecter le code existant et les migrations.
3. Écrire/mettre à jour d’abord les tests qui matérialisent les critères d’acceptation.
4. Implémenter la plus petite solution complète respectant la SFG.
5. Lancer tests ciblés puis lint/typecheck.
6. À la fin d’un milestone, lancer la suite complète pertinente.
7. Mettre à jour `docs/progress.md` avec preuves.
8. Continuer automatiquement vers le prochain ticket débloqué, sauf secret externe manquant ou gate explicitement humaine/juridique.
9. En cas de blocage externe, ne pas fabriquer de données réelles : utiliser seulement les fixtures prévues et garder le statut non validé pour le réel.

## 12. Critère final

Le projet n’est pas “terminé” parce que l’interface fonctionne ou parce qu’un modèle produit un pourcentage. Il est terminé au MVP personnel uniquement lorsque `QA-007` prouve les 22 points de la Definition of Done de la SFG, notamment backfill idempotent, quota sûr, features as-of, modèle calibré/versionné, mapping bloquant, value engine, immutabilité, paper trading, UX sans erreurs, sauvegarde/restauration et absence de scraper Stake.
