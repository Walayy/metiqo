# Exploitation du MVP personnel

Ce runbook utilise Docker Compose et le stockage filesystem. Les commandes
PowerShell se lancent à la racine du dépôt. Employer un projet Compose dédié à
chaque environnement ; une base mock ne devient jamais une base réelle.

## Démarrage

1. Vérifier le commit, les verrous et les preuves de release. Exécuter
   `make check`, `make docker-build`, `make scan-security` et les tests du gate
   sur une base jetable. Ne pas utiliser la base personnelle comme base de tests.
2. Préparer les deux fichiers privés de mots de passe/connexion décrits dans
   [la sécurité](security.md), puis leurs chemins `POSTGRES_PASSWORD_SECRET_FILE`
   et `DATABASE_URL_SECRET_FILE`. La base de production neuve utilise le mot de
   passe PostgreSQL monté et SCRAM ; changer ces fichiers ne modifie pas les
   credentials ou les règles d'une base déjà initialisée.
3. Déclarer `APP_DATA_MODE=real`, `ODDS_PROVIDER=disabled`,
   `APP_PUBLIC_ORIGIN=https://localhost:8443` et `APP_PUBLISH_HOST=127.0.0.1` pour
   l'installation locale. Un provider de cotes ne s'active qu'avec ses preuves
   d'admissibilité. Les exigences d'authentification restent applicables sur le LAN.

```powershell
$composeArgs = @('-f', 'docker-compose.yml', '-f', 'docker-compose.production.yml')
docker compose @composeArgs config --quiet
docker compose @composeArgs up -d --wait postgres volume-init
docker compose @composeArgs run --rm --no-deps api alembic upgrade head
docker compose @composeArgs run --rm --no-deps worker oe auth bootstrap-owner --username owner
docker compose @composeArgs up -d --wait api web gateway worker
```

Le bootstrap demande le mot de passe sans écho et refuse un deuxième compte.
Seul le port HTTPS du gateway est publié. Caddy utilise le hostname de
`APP_PUBLIC_ORIGIN` et écoute toujours sur le port interne 8443. Pour publier un
autre port, exporter aussi `GATEWAY_HTTPS_PORT` dans le shell Compose : par exemple
9443 avec `APP_PUBLIC_ORIGIN=https://localhost:9443`, ou 443 pour l'origine HTTPS
sans port explicite. Cette variable Compose ne se place pas dans le fichier de
configuration `.env` du backend. IPv6 conserve les crochets de l'adresse.
Avec le TLS interne, l'appareil navigateur doit approuver son autorité locale.
Le certificat public peut être lu avec
`docker compose @composeArgs exec -T gateway cat /data/caddy/pki/authorities/local/root.crt`.
La clé privée reste dans le volume `gateway_data`, accessible au seul service
et à l'initialisation des permissions. Ce volume conserve l'autorité entre les
redémarrages. Il n'est pas inclus dans le backup métier ; sa perte demande de
réinstaller la confiance dans une nouvelle autorité locale.

Ouvrir l'origine déclarée, se connecter, puis contrôler `/admin` et `/data`.
`/health` vérifie la vie du processus ; `/ready` vérifie PostgreSQL et la tête
Alembic. L'état opérationnel distingue une source dégradée d'une API indisponible.
L'absence de données historiques, de modèle validé ou de cotes ne constitue jamais
un signal de value et ne doit pas être masquée par une fixture en mode réel.

## Synchronisation et jobs

Le bouton admin retourne immédiatement un reçu 202 pour un nouveau job réel.
L'interface suit son état et affiche son run après exécution. Une réponse réseau
perdue se relance avec la même clé d'idempotence ; le clic sur une nouvelle action
crée une nouvelle clé. Les réponses 200 des anciens runs et du mock restent valides.

L'entraînement réel suit le même principe : le bouton de `/models` crée un job
`model.train`, consultable par `GET /api/v1/admin/jobs/{jobId}`. Le worker choisit
le dernier dataset game winner versionné, produit les preuves walk-forward et
enregistre un candidat ou un modèle bloqué. La promotion reste une décision
distincte soumise au gate du registre. Une base sans dataset produit un échec
observable ; elle ne reçoit aucun modèle de démonstration. Une annulation reçue
avant la publication empêche l'enregistrement de la version.

`make docker-build` associe les images Python à la révision Git complète uniquement
si le checkout est propre, fichiers nouveaux compris. La release utilise
`uv run --frozen python infra/scripts/build_images.py --require-clean` et refuse
un checkout modifié. Sans cette provenance, le développement reste disponible
mais l'entraînement réel retourne une indisponibilité explicite. L'API inscrit
la révision dans la demande et le worker refuse un job destiné à une autre
révision. Pour lancer ces processus directement hors Docker, `APP_CODE_COMMIT`
doit désigner leur commit exact et propre. Un build Compose direct sans métadonnée
de révision ne permet pas l'entraînement réel.

Le worker écrit `raw`, `quarantine`, `models`, `backups` et son espace `work`.
L'API ne monte les objets qu'en lecture. Le réseau `ingestion_egress` donne une
sortie au worker ; PostgreSQL reste uniquement sur le réseau interne. Les
transports OE continuent d'imposer leurs sources et leurs limites, même sur ce réseau.
La suppression d'un fichier de `work` n'est pas une procédure de reprise : attendre
l'arrêt du job, préserver ses diagnostics et lancer une relance identifiée.

```powershell
docker compose @composeArgs exec -T worker oe jobs show <uuid> --json
docker compose @composeArgs exec -T worker oe jobs cancel <uuid> --json
docker compose @composeArgs exec -T worker oe jobs rerun <uuid> --key <nouvelle-cle> --actor owner --reason "Source rétablie" --json
```

Vérifier la syntaxe exacte avec `oe jobs --help` pour la version installée.
Les tentatives sont bornées ; un job `dead` exige une décision de relance.
Les runs échoués restent présents. Chaque nouvelle tentative dispose d'une clé raw
distincte et reste liée au même job. L'audit conserve les identités et les références
utiles sans exposer les payloads ou les credentials.

## Mise à jour et migration sur copie

1. Arrêter le worker pour geler la planification et les nouvelles écritures de jobs.
   Garder la version précédente et ses paramètres disponibles.
2. Faire un backup avec la version courante via
   `docker compose @composeArgs run --rm --no-deps worker oe backup --json` ; conserver le SHA-256 de son index
   séparément du stockage des backups. Voir [sauvegardes](backups.md).
3. Construire et scanner la version candidate. Rejouer le backup dans une base et
   un dossier de test neufs avec `oe restore --migration-dry-run`. Le mode test
   est obligatoire et la base cible doit commencer par `metiquo_restore_`.
4. Examiner la sortie : révision initiale, révision cible, références snapshots et
   modèles conservées. L'exercice n'applique rien à la source et conserve la copie
   pour inspection. En cas d'échec, conserver le rapport et corriger la migration.

```powershell
New-Item -ItemType Directory -Force data/migration-drills
$drillRoot = (Resolve-Path data/migration-drills).Path
$drillId = [guid]::NewGuid().ToString('N')
docker compose @composeArgs run --rm --no-deps -e APP_ENV=test --volume "${drillRoot}:/restore" worker oe restore --backup-id <uuid> --index-sha256 <sha256-verifie> --target-database "metiquo_restore_$drillId" --target-objects "/restore/$drillId" --migration-dry-run --json
```

Sur Linux, le dossier monté doit être inscriptible par UID 10001. Un backup chiffré
exige aussi le montage readonly de son identité age et `--identity <chemin>`.
L'outil refuse une cible existante, une racine partagée avec les objets source,
un index corrompu ou des fichiers dont les empreintes diffèrent.

Après validation de la copie et des tests, arrêter l'API, appliquer les migrations
de la version candidate sur la base personnelle puis redémarrer API/web/gateway et
worker dans cet ordre. Contrôler readiness, session Owner, état opérationnel,
jobs, audit et dernière sauvegarde. Ne pas utiliser un downgrade automatique pour
annuler une migration de données : restaurer la sauvegarde vérifiée dans une
nouvelle cible et valider le basculement. Ne jamais supprimer les volumes par
`docker compose down -v` pendant une mise à jour.

## Arrêt et incidents

`docker compose @composeArgs stop worker` envoie SIGTERM. Le worker cesse de
prendre des jobs et demande leur arrêt à la prochaine frontière coopérative.
Le streaming, le hash, la validation CSV, le staging et les outils de backup
observent l'annulation ; les transactions inachevées sont annulées et les fichiers
temporaires nettoyés. La lecture HTTP courante reste bornée par son timeout.
La grâce Compose est de 90 secondes pour le worker, 30 pour l'API ; Uvicorn
dispose de 25 secondes pour les requêtes en cours et ferme les pools SQL.
Si un processus est malgré tout tué, les baux expirés et les verrous PostgreSQL
permettent la reprise ; un résultat tardif ne peut pas remplacer celui d'un autre worker.

| Symptôme                   | Diagnostic et action                                                                                                                |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Source timeout/quota/HTML  | Lire le code et le run dans `/data` ; garder le snapshot actif, attendre le délai de reprise, ne pas contourner la source.          |
| Hash ou schéma refusé      | Examiner la quarantaine liée au run et aux anomalies ; corriger la cause puis lancer un nouveau run.                                |
| Alerte qualité persistante | Une relecture d'ancien raw ne la clôt pas ; une nouvelle vérification du contenu actif est requise.                                 |
| Job bloqué ou `dead`       | Lire son état et l'audit, vérifier le worker et le bail, annuler/relancer avec raison ; ne pas modifier directement les lignes SQL. |
| Readiness en erreur        | Vérifier disponibilité DB et révision Alembic ; utiliser la copie de migration avant toute correction de schéma.                    |
| Backup ancien ou échoué    | Vérifier espace, permissions, empreintes et clé age ; refaire le backup puis son exercice de restauration.                          |
| Session refusée / 429      | Vérifier origine/cookie, attendre Retry-After ; utiliser le reset Owner CLI si nécessaire.                                          |

Les sorties JSON, logs structurés, `ops.jobs`, les runs et l'audit servent de preuves.
Conserver les identifiants et codes d'erreur ; ne pas recopier de secrets ou de dump
dans un ticket. Pour restaurer les objets et reconstruire les projections à partir
du raw, suivre [le runbook de restauration](restore.md).
