# Administration — 16 septembre 2026

L’espace `?view=admin` est visible dans la sidebar uniquement pour un compte administrateur vérifié. Il utilise la vraie API, y compris avec `VITE_DATA_MODE=mock`. Les données esport et leurs fixtures restent inchangées.

## Comptes

`GET /api/v1/admin/users?q=&page=1` recherche les emails et renvoie 20 comptes par page. La fiche permet de modifier le rôle (`user` / `admin`), suspendre/réactiver un compte et révoquer ses sessions. Les opérations sont sérialisées en base ; le rôle de l’acteur est relu à chaque demande. L’acteur ne peut pas retirer son propre accès admin, et il reste au moins un admin actif. Les emails/identités ne sont pas éditables, et aucune suppression définitive n’est proposée.

Toute modification du rôle ou du statut invalide les sessions. Une suspension empêche également une nouvelle connexion avec un code valide. La route de révocation peut déconnecter l’administrateur lui-même. Le frontend masque immédiatement l’espace lors de la perte du rôle/session détectée et purge les requêtes Admin en mémoire.

## Scripts et crons

Les trois identifiants stables sont `lol-catalog`, `oracle-latest`, `oracle-full`. Ils correspondent aux collecteurs existants et à des arguments prédéfinis ; aucune commande shell n’est exécutée depuis du texte fourni par l’utilisateur. Les cron ont cinq champs numériques (listes, plages, pas, astérisques) et utilisent `Europe/Paris` ou `UTC`. Les heures de Paris tiennent compte du changement d’heure ; préférer un horaire éloigné de 02:00–03:00 pour une heure quotidienne sans ambiguïté.

`POST /scripts/preview` calcule les trois prochaines dates. `PATCH /scripts/{id}` exige une révision pour éviter qu’un formulaire ancien n’écrase un autre changement. Le changement prend effet immédiatement pour les prochaines échéances. `POST /scripts/{id}/run` répond 202 uniquement après insertion en base et refuse un doublon actif ou un worker indisponible. Ces chemins ont le préfixe `/api/v1/admin`.

Un verrou de planificateur et un index unique partiel empêchent les doubles consommations et les demandes actives multiples pour un même script. Les collecteurs gardent leurs verrous par source, y compris face aux commandes CLI. La file est persistante et consommée en série : `queued`, `running`, puis `succeeded`, `failed` ou `interrupted`. Un worker redémarré marque les anciennes exécutions `running` comme interrompues ; elles sont relançables manuellement. Une source occupée reste en file avec une tentative une minute plus tard. Les échecs de collecte ne déclenchent pas de boucle automatique : attendre le prochain cron ou relancer.

Une pause empêche de nouvelles échéances, mais conserve les jobs déjà demandés ; une reprise calcule la prochaine échéance future. Les périodes manquées pendant une indisponibilité sont regroupées en un seul job par script. Une collecte ne modifie jamais les probabilités/cotes du frontend. L’historique de l’interface couvre les huit dernières demandes Admin ; les exécutions CLI et leurs bilans restent dans les endpoints source.

Le worker unique publie un heartbeat toutes les 20 secondes et vérifie la file toutes les cinq secondes entre les collectes. Après 90 secondes sans heartbeat, l’interface indique son indisponibilité. Les interrupteurs `METIQUO_CATALOG_ENABLED` / `METIQUO_ORACLE_ENABLED` et l’option `--only` sont prioritaires. La mise à l’échelle vers plusieurs workers de périmètres différents nécessitera un heartbeat par instance ; cette version supervise un worker unique.

## Persistance et permissions

La migration Alembic `0004` ajoute `app_users.disabled`, `script_schedules`, `script_runs`, `worker_status` et `admin_audit`. Elle ajuste aussi les privilèges sur les volumes déjà initialisés. L’API peut écrire les colonnes nécessaires aux comptes et planifications, insérer uniquement les champs de demande dans la file et ajouter des événements d’audit. Elle ne peut pas écrire les résultats ou le heartbeat. Le worker ne peut lire ni les comptes, ni les sessions, ni les événements d’audit. Aucune donnée privée n’est transmise au worker.

L’audit conserve l’acteur, l’action, la cible, l’heure et les paramètres avant/après, sans code de connexion, cookie ou token. Les réponses Admin sont `no-store`. Les écritures exigent une origine autorisée et le même en-tête anti-CSRF que l’authentification. `npm run docker:up` applique les migrations et reconstruit les services locaux. Aucune publication externe n’est nécessaire.

Les crons reposent sur [croniter](https://github.com/pallets-eco/croniter), consulté le 16 septembre 2026, verrouillé avec `tzdata` dans `uv.lock`. Les tests couvrent les fuseaux, transitions été/hiver, dates impossibles, droits HTTP/SQL, concurrence, persistance et interruption du worker.

### Comptes demandés le 16 septembre 2026

La migration `0005` provisionne `metiquo@admin.fr` en administrateur et `metiquo@user.fr` en utilisateur ordinaire. Les sessions sont révoquées uniquement lors d’un changement de rôle ; la vérification email et les suspensions existantes sont conservées. La migration n’accorde pas de session ni de vérification email et ne change pas le compte pgAdmin. Voir [authentication.md](authentication.md).
