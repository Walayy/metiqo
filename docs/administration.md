# Administration — 16 septembre 2026

L’espace `?view=admin` est visible dans la sidebar uniquement pour un compte administrateur vérifié. Il utilise la vraie API, y compris avec `VITE_DATA_MODE=mock`. Les données esport et leurs fixtures restent inchangées.

## Comptes

`GET /api/v1/admin/users?q=&page=1` recherche les emails et renvoie 20 comptes par page. La fiche permet de modifier le rôle (`user` / `admin`), suspendre/réactiver un compte et révoquer ses sessions. Les opérations sont sérialisées en base ; le rôle de l’acteur est relu à chaque demande. L’acteur ne peut pas retirer son propre accès admin, et il reste au moins un admin actif. Les emails/identités ne sont pas éditables, et aucune suppression définitive n’est proposée.

Toute modification du rôle ou du statut invalide les sessions. Une suspension empêche également une nouvelle connexion avec un code valide. La route de révocation peut déconnecter l’administrateur lui-même. Le frontend masque immédiatement l’espace lors de la perte du rôle/session détectée et purge les requêtes Admin en mémoire.

## Scripts et crons

Les six identifiants stables sont `lol-catalog`, `oracle-latest`, `oracle-full`, `loltv-matches`, `stake-markets` et `settle-selections`. Ils correspondent à des traitements prédéfinis ; aucune commande shell n’est exécutée depuis du texte fourni par l’utilisateur. Les cron ont cinq champs numériques (listes, plages, pas, astérisques) et utilisent `Europe/Paris` ou `UTC`. Les heures de Paris tiennent compte du changement d’heure ; préférer un horaire éloigné de 02:00–03:00 pour une heure quotidienne sans ambiguïté.

`POST /scripts/preview` calcule les trois prochaines dates. `PATCH /scripts/{id}` exige une révision pour éviter qu’un formulaire ancien n’écrase un autre changement. Le changement prend effet immédiatement pour les prochaines échéances. `POST /scripts/{id}/run` répond 202 uniquement après insertion en base et refuse un doublon actif ou un worker indisponible. Ces chemins ont le préfixe `/api/v1/admin`.

Un verrou de planificateur et un index unique partiel empêchent les doubles consommations et les demandes actives multiples pour un même script. Les collecteurs gardent leurs verrous par source, y compris face aux commandes CLI. La file est persistante et consommée en série : `queued`, `running`, puis `succeeded`, `failed` ou `interrupted`. Un worker redémarré marque les anciennes exécutions `running` comme interrompues ; elles sont relançables manuellement. Une source occupée reste en file avec une tentative une minute plus tard. Les échecs de collecte ne déclenchent pas de boucle automatique : attendre le prochain cron ou relancer.

Une pause empêche de nouvelles échéances, mais conserve les jobs déjà demandés ; une reprise calcule la prochaine échéance future. Les périodes manquées pendant une indisponibilité sont regroupées en un seul job par script. Une collecte ne modifie jamais les probabilités/cotes du frontend. L’historique de l’interface couvre les huit dernières demandes Admin ; les exécutions CLI et leurs bilans restent dans les endpoints source.

Chaque worker publie un heartbeat toutes les 20 secondes et vérifie sa file toutes les cinq secondes. Le worker Docker principal, le worker Stake local et `settlement-worker` ont des identifiants de heartbeat distincts ; après 90 secondes sans heartbeat, l’interface indique l’indisponibilité du script concerné. Les interrupteurs de source et l’option `--only` sont prioritaires. Le résultat des sélections est un traitement local de la base, sans navigateur ni réseau source.

## Journal d’exploitation

Scripts distingue les trois services : **Collectes sportives** (catalogue, Oracle et LoLTV), **Cotes Stake** et **Résultats des sélections**. Chaque ligne affiche sa disponibilité, son activité courante et son dernier contact. « Journaux » ouvre le lecteur du service ; « Voir le journal » dans une exécution l’ouvre directement sur son identifiant. Le retour à l’historique conserve l’exécution dépliée. Les événements de service (démarrage, arrêt et incidents de planification) restent visibles même sans exécution associée.

Le journal stocke des événements structurés horodatés, avec identifiant de worker, script et exécution lorsque ceux-ci existent, gravité, étape, message fixe et contexte numérique ou technique autorisé. Il consigne notamment les publications et rejets Stake, les erreurs de collecteur, les résumés de passage et les incidents auxiliaires. Il ne copie pas la sortie brute des processus ni les corps de réponse des sources. Les identifiants d’événement et traces techniques sont validés avant écriture ; les secrets, cookies, jetons, chaînes de connexion et URLs ne sont jamais acceptés dans les messages et contextes persistés. Les comptes d’erreurs seuls ne suffisent pas à définir l’état global : le résumé d’exécution conserve séparément la couverture réelle.

`GET /api/v1/admin/worker-logs` est réservé à une session admin vérifiée. `workerId` est obligatoire ; `runId`, `level`, `q`, `before`, `after` et `limit` sont optionnels. Les lignes sont paginées par identifiant stable, et les incidents du résumé restent indépendants des filtres de la liste. Le lecteur interroge périodiquement cette API avec le dernier identifiant reçu ; il ne double pas les lignes lors d’une reconnexion et suspend le défilement automatique quand l’administrateur remonte. Les lignes anciennes sont chargées explicitement. La base conserve les événements jusqu’à 14 jours : l’API exclut immédiatement les plus anciens et les workers les purgent au démarrage puis chaque heure. Les bilans de `script_runs` et `ingestion_runs` sont conservés suivant leur propre politique. Le journal détaillé commence à la mise en service de la migration `0020` ; aucune ligne ancienne n’est inventée ou reconstituée.

L’API n’a qu’un droit SQL de lecture sur `worker_log_entries` ; les workers ont insertion et purge, sans accès à l’authentification. Aucun socket Docker ni commande `docker logs` n’est exposé à l’API.

## Persistance et permissions

La migration Alembic `0004` ajoute `app_users.disabled`, `script_schedules`, `script_runs`, `worker_status` et `admin_audit`. Elle ajuste aussi les privilèges sur les volumes déjà initialisés. L’API peut écrire les colonnes nécessaires aux comptes et planifications, insérer uniquement les champs de demande dans la file et ajouter des événements d’audit. Elle ne peut pas écrire les résultats ou le heartbeat. Le worker ne peut lire ni les comptes, ni les sessions, ni les événements d’audit. Aucune donnée privée n’est transmise au worker.

L’audit conserve l’acteur, l’action, la cible, l’heure et les paramètres avant/après, sans code de connexion, cookie ou token. Les réponses Admin sont `no-store`. Les écritures exigent une origine autorisée et le même en-tête anti-CSRF que l’authentification. `npm run docker:up` applique les migrations et reconstruit les services locaux. Aucune publication externe n’est nécessaire.

Les crons reposent sur [croniter](https://github.com/pallets-eco/croniter), consulté le 16 septembre 2026, verrouillé avec `tzdata` dans `uv.lock`. Les tests couvrent les fuseaux, transitions été/hiver, dates impossibles, droits HTTP/SQL, concurrence, persistance et interruption du worker.

### Comptes demandés le 16 septembre 2026

La migration `0005` provisionne `metiquo@admin.fr` en administrateur et `metiquo@user.fr` en utilisateur ordinaire. Les sessions sont révoquées uniquement lors d’un changement de rôle ; la vérification email et les suspensions existantes sont conservées. La migration n’accorde pas de session ni de vérification email et ne change pas le compte pgAdmin. Voir [authentication.md](authentication.md).
