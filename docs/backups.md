# Sauvegardes

`oe backup --json` (ou `make backup JSON=1`) sauvegarde la base réelle et les
objets locaux. Dans la stack, utiliser
`docker compose exec -T worker oe backup --json`. Le mode mock est refusé avant tout accès SQL. Le worker planifie la
même opération chaque jour, avec un verrou PostgreSQL commun aux lancements
manuels. `BACKUP_ENABLED=false` désactive aussi cette planification.

## Cohérence et contenu

Le service ouvre une transaction PostgreSQL `REPEATABLE READ`, exporte sa vue,
lit les références raw/modèles, puis transmet cette vue à `pg_dump --snapshot`
au format custom. Le dump reste importable avec `pg_restore`. Le client embarqué
est de version majeure 18, compatible avec le serveur de la stack. Les garanties
et limites de cet export sont décrites dans la
[documentation PostgreSQL](https://www.postgresql.org/docs/18/app-pgdump.html).

Les fichiers de `raw`, `models` et `quarantine` sont conservés ; les fichiers
temporaires cachés et `.part` sont exclus. Chaque référence SQL doit correspondre
au SHA-256 et à la taille de l'objet copié. Une absence, modification ou corruption
fait échouer la sauvegarde. Les liens et remontées de chemin sont refusés. Les
objets publiés après la vue SQL peuvent être inclus en supplément ; ils ne
remplacent aucune référence du dump. Un stockage S3/MinIO est actuellement
refusé par cette commande (`BACKUP_STORAGE_UNSUPPORTED`).

Le dépôt contient :

- `runs/<UUID>/database.dump` et `manifest.json`, suffixés `.age` si chiffrés ;
- `runs/<UUID>/index.json`, avec empreintes, tailles et références des blobs ;
- `blobs/<SHA-256 stocké>`, partagés entre sauvegardes.

Le manifeste contient la révision Alembic, les identifiants des snapshots et
modèles, les chemins logiques et les empreintes des fichiers. L'index ne contient
ni chemin logique, ni URL de base, ni clé privée. Son SHA-256 est conservé dans
`ops.backup_runs` ; il faut conserver cette preuve séparément du dépôt pour un
exercice de restauration après perte de la base. Les identifiants, empreintes et
tailles de l'index ne sont pas chiffrés.

Le stockage est incrémental pour les objets immuables : un deuxième passage ne
recopie pas les blobs inchangés et vérifie les blobs réutilisés. Chaque run a son
propre dump cohérent. Une rotation du destinataire de chiffrement produit de
nouveaux blobs chiffrés, sans réutiliser ceux de l'ancien destinataire.

## Chiffrement et paramètres

`BACKUP_ROOT` désigne le dépôt (par défaut `<OBJECT_STORE_ROOT>/backups`). Il ne
doit pas chevaucher les répertoires de données. Pour un stockage externe, définir
`BACKUP_EXTERNAL=true` et `BACKUP_AGE_RECIPIENT` avec une clé publique age ; les
chemins réseau UNC exigent aussi un destinataire. Tout montage distant doit être
déclaré externe : un chemin local ne permet pas d'identifier son support physique.

La génération de clés et le déchiffrement suivent la
[documentation officielle age](https://github.com/FiloSottile/age). Le worker
reçoit uniquement la clé publique. Conserver la clé privée séparément, avec un
accès limité à la restauration. Sans elle, les fichiers chiffrés sont perdus.
Le dump et le manifeste temporaires en clair restent sur le volume raw local,
dans `.backup-work`, et sont nettoyés après l'opération. Un arrêt forcé peut y
laisser un répertoire temporaire ; il est exclu des sauvegardes suivantes.

| Paramètre                      | Valeur initiale | Effet                                       |
| ------------------------------ | --------------- | ------------------------------------------- |
| `BACKUP_INTERVAL_SECONDS`      | 86400           | Fréquence du scheduler                      |
| `BACKUP_FRESHNESS_SLA_SECONDS` | 129600          | Seuil de fraîcheur, 36 heures               |
| `BACKUP_RETENTION_COUNT`       | 7               | Nombre de sauvegardes réussies conservées   |
| `BACKUP_TIMEOUT_SECONDS`       | 3600            | Limite de chaque processus dump/chiffrement |
| `BACKUP_AGE_BINARY`            | `age`           | Exécutable de chiffrement                   |
| `BACKUP_PG_DUMP_BINARY`        | `pg_dump`       | Exécutable PostgreSQL                       |

## Échecs, rétention et supervision

`ops.backup_runs` conserve succès, erreurs et interruptions. Les preuves terminées
et leur historique sont immuables ; seule la disponibilité après rétention peut
être retirée. Une nouvelle exécution ferme les anciennes tentatives interrompues
après acquisition du verrou. Une annulation coopérative est vérifiée entre les
objets et autour du dump ; le processus externe en cours reste borné par son délai.

La supervision affiche dernière réussite, dernier échec et code d'erreur. Une
sauvegarde absente, périmée ou échouée déclenche l'alerte persistée
`BACKUP_UNHEALTHY`. Une erreur de rétention ne détruit pas une nouvelle preuve
valide : la commande retourne `BACKUP_RETENTION_FAILED` dans ses avertissements,
et un événement identique est visible dans l'audit. Ce cas doit être traité même
si la dernière sauvegarde reste fraîche.

La rétention retire d'abord la disponibilité SQL, puis supprime les anciens
fichiers et les blobs connus qui ne servent plus aux sauvegardes conservées. Une
suppression interrompue est reprise au passage suivant. L'historique SQL reste
présent. Les fichiers inconnus, et les blobs orphelins dont l'index a disparu,
ne sont pas supprimés automatiquement. Une sauvegarde échouée peut laisser des
fichiers incomplets ; ne jamais les considérer comme une preuve de restauration.

## Vérification exécutée

Les tests PostgreSQL utilisent une ingestion réelle alimentée par une fixture
identifiée et un objet modèle de fixture, puis un vrai `pg_dump`. Ils vérifient
la copie incrémentale, la rétention, la reprise après interruption, les refus de
corruption/absence, l'immutabilité SQL, l'annulation et le chiffrement/déchiffrement
age. L'exercice de [restauration et reconstruction](restore.md) complète cette
preuve technique ; il ne valide pas la performance financière d'un modèle.
