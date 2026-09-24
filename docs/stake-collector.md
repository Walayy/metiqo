# Collecteur Stake pré-match et direct

Implémentation du 22 septembre 2026, rétablie le 23 septembre depuis la révision Git `7e10858`. Le collecteur lit les pages publiques, sans compte ni action de pari. Le frontend modifié se limite à l’administration ; les cotes collectées ne sont pas injectées dans les fixtures ni dans les values.

## Parcours et périmètre

`sync-stake-markets` ouvre le hub esport, découvre le lien du jeu, parcourt sa liste paginée, puis visite les rencontres admissibles et tous leurs onglets de marchés activés. Il déplie les accordéons et les contrôles « Tout » observés. Les sélections de pari ne sont jamais cliquées. Les catégories et compétitions proviennent des chemins et libellés source ; aucune liste fermée de ligues n’est codée.

La configuration active seulement `league-of-legends`. Le schéma, les identifiants, le planificateur et les contrats de capture acceptent plusieurs jeux. Ajouter un slug demande néanmoins de vérifier le DOM et les preuves de statut de ce jeu : une structure inconnue ne devient pas automatiquement collectable.

Patchright **1.63.0** est verrouillé dans `uv.lock`. Stake utilise Chrome Stable installé localement, **avec interface**, un contexte persistant dédié et les dimensions natives de la fenêtre. Les cookies restent sous `.cache/stake-audit/chrome-profile`, hors Git. Aucun profil personnel, export de cookies, proxy ou changement d’identité n’est utilisé. Ne pas lancer l’audit manuel simultanément sur ce profil.

## État de la rencontre et disponibilité des cotes

Avant toute lecture des nœuds de marchés, le script DOM exige une fiche identifiée, deux participants distincts et un état public vérifié. Le pré-match demande `SportsEvent / EventScheduled`, une date `startDate` avec fuseau explicite, encore future au-delà de la marge de 60 secondes, et deux scores d’attente `-`. Le JSON-LD doit correspondre au chemin de la fiche visitée. La date UTC est conservée sans déduire le fuseau du texte affiché.

Un badge live ou les scores numériques de la fiche permettent la lecture des marchés **en direct**, même si l'heure prévue est passée ou manque dans la source. Le début d'une rencontre n'arrête plus sa collecte. Un statut clos ou inconnu ne publie aucun nouveau relevé. Les contrôles sont répétés après les pauses, avant les clics de navigation, à chaque capture et avant publication. Si le statut passe de pré-match à direct au milieu d'un parcours, ce relevé mixte est rejeté puis le collecteur réessaie une fois en direct. Les captures précédentes restent historiques.

`stopped_at` et `stop_reason` restent persistants pour les rencontres **closes** ; le worker ne les efface pas. La migration `0016` archive dans `bookmaker_collection_resumptions` les anciens arrêts dus uniquement à la règle pré-match, puis rouvre ces événements afin que leur éventuel direct puisse être observé. Une heure passée sans marqueur live n'autorise pas la lecture de marchés. Le navigateur reçoit naturellement les ressources de la page ; cette règle porte sur la publication, pas sur le contenu réseau que le site peut pousser de lui-même.

Les sélections visibles mais suspendues restent dans le snapshot avec `disabled=true` et `odds=NULL`, même lorsque leur ligne ou leur marché est affiché. Une cote antérieure n'est jamais reportée sur un bouton fermé. `odds_raw` peut conserver le texte brut de la source ; `quote_open` dans la vue décrit seulement l'état **au moment du relevé**, pas une disponibilité garantie lors de la consultation.

## Organisation PostgreSQL

La migration **0013** ajoute les tables suivantes, indépendantes des marchés de démonstration et des rencontres canoniques :

| Table                   | Rôle                                                                                                                                                                       |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bookmaker_events`      | Identifiant Stake et URL, jeu, compétition/catégorie, participants ordonnés, noms normalisés indexés, début UTC éventuel, statut, première/dernière observation et arrêt terminal |
| `bookmaker_markets`     | Identité du marché par événement, libellé intégral, famille, portée rencontre/carte et numéro de carte publié                                                              |
| `bookmaker_selections`  | Identité de sélection, libellés visible/accessible/colonne/en-tête de ligne, cut décimal et brut, rang ordinal éventuel                                                    |
| `bookmaker_snapshots`   | Un parcours complet d’une rencontre dans une exécution, phase pré-match ou direct, début/fin de capture, heure prévue éventuelle, dates par onglet et référence de preuve   |
| `bookmaker_quotes`      | Prix décimal ou nul, texte source, état désactivé, onglet et horodatage de chaque lecture validée                                                                          |
| `bookmaker_payloads`    | Document source normalisé JSONB dédupliqué par SHA-256, version du parseur                                                                                                 |
| `bookmaker_collection_resumptions` | Ancienne date et raison d'arrêt pré-match levées par `0016`, conservées sans réécrire les relevés historiques                                                   |
| `bookmaker_match_links` | Association future vers `matches`, méthode, preuves JSONB et date ; aucune association automatique actuelle                                                                |

Chaque rencontre complète est publiée dans une transaction. Un onglet manquant, un état inconnu ou clos, une transition de phase, une identité ambiguë ou une cote active illisible conserve la dernière version valide. Les autres rencontres déjà validées du cycle ne sont pas annulées. Les timestamps sont en `timestamptz` ; la cote n’est jamais confondue avec son cut. Un score exact `0:3` n’est pas un cut ; le dixième kill est un ordinal, distinct d’une ligne de total. Les unités non publiées restent inconnues. Les labels des familles nouvelles sont conservés sans inventer leur sémantique.

Les identifiants source sont conservés lorsqu’ils existent. Sinon, une identité DOM déterministe est construite à partir du contexte du libellé, de la colonne et de la ligne, avec `identity_basis=stake-dom-v1`. Pour les grilles à en-tête d'équipe par ligne, `stake-dom-v2-row` utilise cet en-tête réellement affiché : les choix « Oui/Non » restent distincts même quand un bouton suspendu perd son nom accessible. Ces identités calculées ne sont pas présentées comme des identifiants fournis par Stake ; les anciennes sélections `v1` restent historiques et ne sont pas réécrites. Un changement de cut crée une sélection distincte ; un changement de prix conserve la même sélection. Les payloads permettent de réexaminer le parsing et les libellés historiques. La langue de navigation est fixée à la route publique française.

Un relevé inchangé est une nouvelle observation datée : **A → B → A → A** reste quatre points, avec déduplication des documents identiques seulement. Une relance technique du même couple exécution/rencontre est idempotente. Un marché présent dans plusieurs onglets peut produire plusieurs lectures datées dans un même parcours. Les prix ne représentent pas un instant simultané garanti ni la date de mise à jour interne de Stake.

Le rôle worker ne peut ni modifier ni supprimer les snapshots, payloads et prix. Des triggers SQL vérifient la cohérence événement/sélection, l’intervalle de capture et la phase annoncée ; l'antériorité au début programmé ne concerne que le pré-match. La vue `bookmaker_current_quotes` expose les dernières sélections du dernier parcours complet de chaque rencontre ; une sélection absente de ce nouveau parcours n’est plus courante. Elle indique `captured_phase`, `event_status` et `quote_open`. Toujours consulter l'horodatage et l'état suspendu : le dernier relevé peut être ancien, surtout après la disparition de la rencontre de la liste publique.

```sql
-- Dernier relevé par rencontre / marché / sélection.
SELECT event_source_id, competition_name, participants, starts_at,
       market_label, selection_label, column_label, row_label, line, ordinal,
       odds, disabled, observed_at, captured_phase, event_status, quote_open
FROM bookmaker_current_quotes
WHERE game = 'league-of-legends'
ORDER BY starts_at, event_source_id, market_label, selection_label, line;

-- Historique d'une sélection stable : UUID obtenu dans la vue courante.
SELECT q.observed_at, q.odds, q.odds_raw, q.disabled, s.line, q.tab
FROM bookmaker_quotes q
JOIN bookmaker_selections s ON s.id = q.selection_id
WHERE q.selection_id = :selection_id
ORDER BY q.observed_at;
```

## Matching LoLTV / Oracle

L’événement conserve le triplet bookmaker/jeu/identifiant source, la compétition, les participants ordonnés et l’horaire UTC. Le [résolveur automatique](match-reconciliation.md), migration `0015`, publie les liens démontrés dans `bookmaker_match_links`, avec l’orientation des participants, les identités LoLTV/Oracle et leur preuve. Les événements absents restent en attente ; les ambiguïtés retirent le lien actif. Les découvertes sont conservées avant la collecte des marchés et les lectures partielles n’effacent plus les identités complètes. Les cotes et cuts ne sont pas encore interprétés en catégories de paris.

## Lancement local Windows

Prérequis : stack Docker configurée, `uv`, Chrome Stable installé et session Windows graphique ouverte. Le navigateur Stake s’exécute sur l’hôte ; API, PostgreSQL et les autres collecteurs restent dans Docker. Le port SQL optionnel est lié uniquement à `127.0.0.1`.

```powershell
uv sync --frozen
npm run docker:api
npm run stake:status
```

Dans **Gestion → Scripts**, « Stake · cotes pré-match et direct » permet **Lancer**, **Planifier**, mettre en pause et consulter le bilan des exécutions. La migration `0014` règle **`*/20 * * * *`**, heure de Paris. Le formulaire propose directement « Toutes les 20 minutes ». Le moteur de values supprimé n’est pas relancé par le collecteur.

```powershell
# Arrêt propre du worker dédié, avec conservation des rencontres déjà validées.
npm run stake:stop

# Un passage isolé, worker dédié arrêté. Le cron n'est pas changé.
npm run stake:run
```

Le lanceur lit le rôle SQL `metiquo_worker` dans `.env.docker`, sans afficher les secrets. PID, demande d’arrêt et journaux résident dans `.cache/stake-worker`. Le worker natif annonce son heartbeat sous l’ID 2 ; le worker Docker conserve l’ID 1. L’administration agrège seulement les heartbeats récents et contrôle la disponibilité de chaque script. `stake:status` distingue le processus de son état prêt ; `stake:start` attend le premier heartbeat et évite un second processus. Un verrou PostgreSQL empêche aussi deux collectes Stake simultanées.

Le worker doit être démarré à nouveau après fermeture de la session ou redémarrage de Windows. Aucune tâche Windows au démarrage n’est installée. Si Docker ou la session graphique ne sont pas disponibles, le cron ne peut pas collecter ; l’administration conserve sa file. Une indisponibilité regroupe les échéances manquées, sans lancer toutes les anciennes occurrences à la suite.

## Réglages et erreurs

Les variables ci-dessous portent le préfixe `METIQUO_`. Le lanceur lit les `METIQUO_STAKE_*` présentes dans `.env.docker`. En CLI Python directe, elles viennent de l’environnement. La cadence cron se règle en base depuis l’Admin.

| Variable                       | Défaut                              | Usage                                                                                               |
| ------------------------------ | ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| `STAKE_ENABLED`                | `false`                             | Activation du worker ; le lanceur natif et la commande explicite l’activent, Docker reste désactivé |
| `STAKE_GAMES`                  | `["league-of-legends"]`             | Slugs des jeux validés                                                                              |
| `STAKE_PROFILE_DIR`            | `.cache/stake-audit/chrome-profile` | Profil Chrome dédié, jamais partagé entre processus actifs                                          |
| `STAKE_MIN_DELAY_SECONDS`      | 5                                   | Espacement minimum des navigations/clics explicites                                                 |
| `STAKE_TIMEOUT_SECONDS`        | 45                                  | Attente d’une page ou d’un contenu stable                                                           |
| `STAKE_CYCLE_SECONDS`          | 900                                 | Durée maximale d’un cycle ; priorité aux rencontres les moins récemment relevées                    |
| `STAKE_MAX_ACTIONS`            | 300                                 | Plafond des navigations et clics d’un cycle                                                         |
| `STAKE_REQUEST_BUDGET`         | 30000                               | Plafond persistant d’événements de requêtes naturelles du navigateur                                |
| `STAKE_BUDGET_WINDOW_SECONDS`  | 1200                                | Fenêtre du budget partagé                                                                           |
| `STAKE_BLOCK_COOLDOWN_SECONDS` | 3600                                | Pause après refus principal ; prolongée par `Retry-After`                                           |
| `STAKE_START_GUARD_SECONDS`    | 60                                  | Marge avant l'heure prévue pour les seuls relevés pré-match ; sans effet sur le direct               |

Ces limites locales ne sont pas des quotas publiés par Stake. Un budget compte aussi les ressources naturellement chargées ; il ne garantit pas l’absence de 403/429. Les requêtes déjà parties ne sont pas annulées rétroactivement.

Un **403/429 auxiliaire** est journalisé, avec URL expurgée, et le parcours continue tant que les données requises sont disponibles. Aucune requête directe ne rejoue ces ressources. Un 403/429 du document principal reste provisoire jusqu'à la vérification du contenu rendu : si la liste ou les marchés attendus sont lisibles, le refus est classé `nonblocking` et le cycle continue. Si la page affiche une protection explicite ou si les données attendues restent indisponibles après le délai de lecture, la source est mise en pause en respectant `Retry-After`. Le planificateur replace la demande en attente avec sa date de reprise. Les données précédentes restent disponibles ; LoLTV et Oracle continuent indépendamment.

Une couverture interrompue par le budget apparaît avec `complete=false` dans `ingestion_runs.details`. Les rencontres les plus anciennes sont prioritaires au cycle suivant. Les erreurs de parsing par événement sont comptées ; elles ne doivent pas être interprétées comme une absence de marchés. L’historique Admin affiche les nombres de matchs collectés/écartés/échoués, marchés, sélections et relevés ; son contrat fournit aussi le nombre de snapshots. Les journaux ne contiennent ni cookies ni jetons.

## Vérification

Le premier cycle applicatif réel, lancé depuis l’Admin le **22 septembre 2026 de 21:17:36 à 21:22:36 UTC** (23:17–23:22 Paris), a traité les **13 rencontres découvertes** : **12 pré-match publiées**, **227 marchés**, **622 sélections**, **702 lectures horodatées**, **160 cuts numériques**, **120 rangs ordinaux**. La rencontre `848212`, passée en direct avec un début publié à 21:18 UTC, a été arrêtée avec **zéro cote enregistrée**. Aucun refus 403/429 ni échec de parsing pendant ce cycle. Les requêtes naturelles comptées sont 11 840 ; aucun relevé n’atteint l’heure prévue de sa rencontre. [Bilan et preuves PostgreSQL](audits/stake/2026-09-22-pipeline/validation.json), [empreinte](audits/stake/2026-09-22-pipeline/manifest.json). Le dump restauré le 23 septembre contient désormais 20 événements et 14 160 lectures ; ces nombres décrivent des données historiques, pas un relevé courant.

Les fichiers restaurés `tests/backend/test_stake_pipeline.py` et `test_stake_audit.py` contiennent les tests de parsing et de refus hors réseau, ainsi que des tests PostgreSQL de stockage, cuts, suspensions, idempotence, droits SQL et provenance. Leur ancien test de rejet du direct a été remplacé par des cas de publication live, d'heure prévue absente ou passée et de suspension sans cote. L’exécution réelle du 23 septembre 2026, antérieure à cette extension, a terminé avec 13 événements examinés, 10 collectés, 3 arrêtés avant le live, 0 échec et 528 nouvelles cotes. L’interface Admin avait été vérifiée en clair et sombre, sur ordinateur, tablette et mobile, ainsi qu’au clavier.

Les tests automatiques ordinaires ne contactent pas Stake. Les preuves d’accès réel et leurs limites sont consignées séparément dans [les sources](data-sources.md). L’offre peut changer entre deux cycles ; ni l’exhaustivité permanente ni l’accès sans refus ne sont promis.

Après l'extension au direct, l'exécution locale `2fbc9710-39c4-4c5d-83f3-7febd9edcfa3` du **23 septembre 2026, 19:08:18–19:13:49 UTC** a réussi : **13 rencontres découvertes et collectées, dont 3 en direct**, 231 marchés, 630 sélections et 712 lectures (708 cotées, 4 suspendues), sans échec ni refus déclaré. Les trois snapshots live contiennent **182 lectures cotées et 2 suspendues** ; chacun comporte au moins un marché « Gagnant » coté. Le SQL ne trouve aucune lecture avec une cote numérique et `disabled=true`, ni sans cote et `disabled=false`. Les chiffres décrivent ce seul passage, pas la disponibilité d'un pari quelques secondes plus tard. La collection reste planifiée toutes les vingt minutes et le worker Chrome local est actif après la vérification.
