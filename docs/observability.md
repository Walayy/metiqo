# Supervision opérationnelle

En mode réel, `GET /api/v1/system/status` lit un état cohérent PostgreSQL sans contacter les fournisseurs. Il expose la source OE de l'année configurée, le champion global LoL game winner, le nombre de mappings en attente, la file de jobs, les sauvegardes et les mesures. En mock, `operations` vaut `null` : les exemples métier ne deviennent pas des mesures de production.

`/health` vérifie uniquement la présence du serveur. `/ready` dépend de PostgreSQL et des migrations. Une source dégradée ne fait donc pas tomber ces routes si la base répond. `operations.readsAvailable` indique qu'un snapshot courant validé reste utilisable, y compris après un incident distant ou un dépassement du SLA. Cette disponibilité ne donne aucune autorisation de publier un signal : le gate value conserve ses conditions de fraîcheur. Une date de confirmation future est signalée comme invalide sans inventer un âge nul.

La fraîcheur source utilise la dernière validation ou confirmation fiable du contenu du snapshot courant. Une vérification de hash inchangé peut prolonger cette preuve sans modifier le fichier, son manifeste ou sa date de validation initiale. `OE_FRESHNESS_SLA_SECONDS` fixe le SLA, initialement trois heures. `MODEL_FRESHNESS_SLA_SECONDS` fixe l'âge maximal du champion et de sa borne d'entraînement, initialement trente jours. Le statut global est dégradé lorsqu'une source, un modèle ou une sauvegarde n'est pas à jour. Jusqu'au raccordement des sauvegardes OPS-008, leur état est explicitement `not_configured`.

## Portée des mesures

- Les compteurs PostgreSQL portent sur l'historique conservé, pas sur une fenêtre temporelle implicite. Les échecs de jobs sont les états terminaux `failed` et `dead` ; les retries en attente restent dans la file.
- La durée moyenne mesure la dernière tentative des jobs terminés disposant d'un début et d'une fin cohérents. Le nombre de jobs mesurés accompagne cette moyenne. Les durées de chaque tentative sont aussi journalisées.
- Les lignes sont celles des chargements raw réussis, y compris les rechargements ; ce compteur n'est pas un nombre de lignes métier uniques. Les anomalies comptent l'historique de qualité, avec un sous-total bloquant. Les signaux sont regroupés par grade réellement conservé.
- Les requêtes, erreurs HTTP 5xx et latences moyennes portent uniquement sur le processus API courant et repartent à zéro au redémarrage. La requête de statut en cours n'entre dans le compteur qu'après sa réponse. Une absence de mesure est `null`, jamais une latence simulée.

L'administration présente ces états avec une actualisation explicite. Les lectures de jobs et d'audit sont paginées en SQL, avec un maximum de cent éléments par page et un total cohérent. La file expose portée, tentative, horaire, demande d'annulation, erreur et trace, sans payload. Le journal central conserve les événements et références des anciens audits de modèles et de mapping sans les dupliquer. L'empreinte affichée identifie une opération ; elle ne constitue pas une preuve de contenu métier.

## Journaux et corrélation

API et worker émettent du JSON avec `trace_id`, `job_id`, `correlation_id`, `snapshot_id` et `model_version` lorsque ces références existent. `X-Trace-Id` relie une réponse HTTP à son audit transactionnel. Les logs d'ingestion et de pricing ajoutent leurs références et durées sans dépendance de télémétrie externe. Le message `pricing.evaluated_in_transaction` décrit un calcul avant la clôture de la transaction ; le journal SQL reste la preuve de publication.

Les champs additionnels acceptés sont limités à durée, statut HTTP, tentative, méthode, patron de route et type de job. L'API journalise le patron de route sans query ni paramètres de chemin. Le journal d'accès brut du serveur est désactivé pour éviter de recopier les URLs. Les secrets configurés, chaînes de connexion, credentials d'URL, autorisations et affectations de tokens sont masqués. Une exception expose son type, pas son payload brut ou sa pile. Les retours CLI inattendus utilisent un code stable et un message générique.

Les tests couvrent masquage, compteurs, panne distante avec lecture conservée, dates invalides, confirmation inchangée et dépassement du SLA, pagination, compatibilité des audits, traces ingestion/pricing et affichage navigateur. Les fixtures navigateur sont identifiées comme telles ; les mêmes états et mesures sont vérifiés séparément sur PostgreSQL réel.
