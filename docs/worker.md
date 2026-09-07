# Worker PostgreSQL

La migration `20260908_0039` crée `ops.jobs`. Chaque requête conserve un type, un payload JSON, une portée métier, un acteur, un identifiant de trace, sa clé d'idempotence et son empreinte. Modifier une requête existante ou supprimer son historique est refusé par PostgreSQL. L'état d'exécution, les tentatives, les horaires, le heartbeat, le bail, la demande d'annulation et le code d'erreur restent des champs de suivi.

`PostgresJobQueue.enqueue` retourne le job existant pour une clé et une requête identiques. Un payload différent avec cette clé produit un conflit. `claim` sélectionne un job planifié arrivé à échéance ou un bail expiré, dans une transaction avec `FOR UPDATE SKIP LOCKED`. La reprise reçoit un nouveau jeton de propriété ; l'ancien jeton ne peut ni renouveler le bail ni publier la fin du job. Les tentatives épuisées deviennent `dead`.

Un verrou PostgreSQL par identifiant de job protège toute l'exécution du handler. Tant qu'un handler détient ce verrou, un bail expiré ne suffit pas à lancer ce même job en parallèle. La perte de la session libère le verrou et permet la reprise. Le runner renouvelle le bail par heartbeat et vérifie la propriété avant l'exécution et la publication du résultat. Les handlers doivent rester idempotents : une reprise peut répéter un appel métier dont la réponse a été perdue après publication.

En mode réel, `uv run --frozen python -m metiquo.worker` consomme la file. Les handlers `paper.report` et `paper.settle` appellent les services P7 et conservent leurs références de résultat. Un type inconnu finit `failed` avec `UNKNOWN_JOB_TYPE` ; il n'est jamais traité comme un succès. En mode mock, le processus conserve son cycle isolé sans consommer la file réelle.

La mise en file est disponible via `PostgresJobQueue` pour les services opérateur. La planification automatique est raccordée dans OPS-004. Par exemple, `enqueue("paper.report", {"currency": "EUR"}, key="report-001", scope="paper:EUR")` demande un rapport de cette devise. Les verrous de portée entre jobs différents, les politiques de retry et l'annulation contrôlée sont les étapes OPS-002 et OPS-003.

Les tests PostgreSQL vérifient deux prises concurrentes, la reprise après expiration, le refus d'un ancien propriétaire, le verrou d'un handler toujours actif, un job futur, une erreur terminale, les contraintes d'immutabilité et l'exécution du vrai service de rapport. Le worker journalise les identifiants du job et de trace ; il ne journalise pas le payload ni le texte brut d'une erreur de handler.
