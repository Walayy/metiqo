# Worker PostgreSQL

La migration `20260908_0039` crée `ops.jobs`. Chaque requête conserve un type, un payload JSON, une portée métier, un acteur, un identifiant de trace, sa clé d'idempotence et son empreinte. Modifier une requête existante ou supprimer son historique est refusé par PostgreSQL. L'état d'exécution, les tentatives, les horaires, le heartbeat, le bail, la demande d'annulation et le code d'erreur restent des champs de suivi.

`PostgresJobQueue.enqueue` retourne le job existant pour une clé et une requête identiques. Un payload différent avec cette clé produit un conflit. `claim` sélectionne un job planifié arrivé à échéance ou un bail expiré, dans une transaction avec `FOR UPDATE SKIP LOCKED`. La reprise reçoit un nouveau jeton de propriété ; l'ancien jeton ne peut ni renouveler le bail ni publier la fin du job. Les tentatives épuisées deviennent `dead`.

Un verrou PostgreSQL par identifiant de job protège toute l'exécution du handler. Tant qu'un handler détient ce verrou, un bail expiré ne suffit pas à lancer ce même job en parallèle. La perte de la session libère le verrou et permet la reprise. Le runner renouvelle le bail par heartbeat et vérifie la propriété avant l'exécution et la publication du résultat. Les handlers doivent rester idempotents : une reprise peut répéter un appel métier dont la réponse a été perdue après publication.

En mode réel, `uv run --frozen python -m metiquo.worker` consomme la file. Les handlers `paper.report` et `paper.settle` appellent les services P7 et conservent leurs références de résultat. Un type inconnu finit `failed` avec `UNKNOWN_JOB_TYPE` ; il n'est jamais traité comme un succès. En mode mock, le processus conserve son cycle isolé sans consommer la file réelle.

La mise en file est disponible via `PostgresJobQueue` pour les services opérateur. Par exemple, `enqueue("paper.report", {"currency": "EUR"}, key="report-001", scope="paper:EUR")` demande un rapport de cette devise.

La portée métier protège également les jobs distincts. Un job dont la portée est occupée reste en attente sans consommer de tentative ; les autres portées peuvent avancer. `oe:oracles_elixir:2026` coordonne worker, backfill et synchronisation directe de l'année 2026. `model:lol:game_winner` coordonne entraînement, promotion, rollback, blocage et retrait. Les appels imbriqués reconnaissent leur propre verrou. Le règlement protège déjà sa bankroll et sa ligne paper dans la transaction. Les verrous de session sont libérés après exception ou perte de connexion ; l'attente explicite est bornée à 120 secondes au maximum, avec refus immédiat par défaut.

Les tests PostgreSQL vérifient deux prises concurrentes, la reprise après expiration, le refus d'un ancien propriétaire, le verrou d'un handler toujours actif, un job futur, une erreur terminale, les contraintes d'immutabilité et l'exécution du vrai service de rapport. Le worker journalise les identifiants du job et de trace ; il ne journalise pas le payload ni le texte brut d'une erreur de handler.

Les erreurs transitoires explicites, connexions perdues, timeouts et conflits transactionnels autorisent une nouvelle tentative planifiée. Les délais initiaux sont 10 minutes, 30 minutes et 2 heures, avec un jitter positif jusqu'à 10 %, reproductible par job et tentative. L'horaire est persisté ; le worker ne dort pas pendant le backoff. Le nombre maximal d'essais reste borné dans la requête. Son épuisement mène à `dead` ; une erreur permanente ou inconnue mène à `failed`.

En mode réel, `uv run --frozen python -m metiquo.cli jobs show JOB_ID --json` consulte l'état sans afficher le payload. `jobs cancel JOB_ID --json` annule immédiatement un job en attente, ou demande un arrêt coopératif au handler actif. Le heartbeat transmet cette demande au token ; le lot paper le vérifie entre ses transactions. SIGINT et SIGTERM demandent aussi l'arrêt coopératif. Une transaction métier déjà commise reste conservée. Un handler doit vérifier le token entre ses unités ; le runner ne tue pas une transaction en cours arbitrairement.

`jobs rerun JOB_ID --key NOUVELLE_CLE --actor OPERATEUR --reason MOTIF --json` relance un job `failed`, `dead` ou `cancelled`. La migration `20260908_0040` conserve le parent et le motif immuables ; le job original reste terminé avec ses tentatives et son erreur. Réutiliser une clé avec une requête différente est refusé. Les tests couvrent aussi la course annulation/fin et le nettoyage d'une annulation dont le propriétaire a disparu.

En mode réel, le scheduler s'exécute dans une boucle indépendante des handlers longs. `WORKER_SCHEDULER_ENABLED=false` le désactive ; le mode mock ne démarre jamais cette planification réelle. Chaque worker peut avoir son scheduler : un verrou partagé, des clés de créneaux UTC et la vérification des jobs actifs empêchent les doublons. Un redémarrage traite le créneau courant sans accumuler les créneaux manqués.

| Traitement                                         | Configuration                       | Valeur initiale   |
| -------------------------------------------------- | ----------------------------------- | ----------------- |
| Année OE courante                                  | `OE_SYNC_INTERVAL_SECONDS`          | 10 800 secondes   |
| Catalogue et années closes                         | `OE_CLOSED_AUDIT_MONTHS`            | 1 mois calendaire |
| Contrôle approfondi après plusieurs hashes validés | `OE_DEEP_CHECK_INTERVAL_SECONDS`    | 86 400 secondes   |
| Règlement paper                                    | `PAPER_SETTLEMENT_INTERVAL_SECONDS` | 300 secondes      |
| Rapport paper                                      | `PAPER_REPORT_INTERVAL_SECONDS`     | 300 secondes      |
| Réveil du scheduler                                | `WORKER_SCHEDULER_TICK_SECONDS`     | 15 secondes       |
| Délais de reprise                                  | `WORKER_RETRY_DELAYS_SECONDS`       | `[600,1800,7200]` |
| Jitter positif maximal                             | `WORKER_RETRY_JITTER_FRACTION`      | 0,1               |

`oe.catalog` utilise la découverte et la réconciliation existantes. Un fallback conserve le catalogue utilisable et signale l'indisponibilité distante. `oe.sync` et `oe.audit` utilisent la synchronisation réelle : seul un checksum SHA-256 fiable identique, un chargement précédent réussi et une vérification du fichier/manifeste/schéma autorisent à éviter un nouveau transfert. Sans cette preuve, la validation complète reste nécessaire. `oe.deep` relit le snapshot actif et ses preuves locales. Une source ayant déjà publié plusieurs hashes validés reçoit ce contrôle quotidien, y compris après sa clôture.

Une confirmation récente est attachée au run (`contentVerified`, `metadataVerified`, `sourceProbe`) et au snapshot ; elle ne change ni la date de validation initiale ni le manifeste immuable. La fraîcheur utilise la dernière confirmation réussie de ce contenu. Le miroir privé est exclu de cette confirmation distante. Une synchronisation distante en échec garde le snapshot lisible selon sa politique, tout en laissant le job en échec ou en attente d'une reprise bornée ; conserver des données ne devient pas artificiellement un succès de synchronisation.
