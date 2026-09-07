# Restauration de test et reconstruction

La commande `oe restore` importe une sauvegarde vérifiée dans une nouvelle base
PostgreSQL et un nouveau dossier d'objets. Elle exige `APP_ENV=test` et
`APP_DATA_MODE=real`. Elle ne remplace pas une base ou un dossier existant. Les
objets sont restaurés localement, y compris si le dépôt est chiffré.

## Préparer l'exercice

1. Disposer du dépôt décrit dans [Sauvegardes](backups.md), du `backupId` et de
   l'`indexSha256` retournés par `oe backup --json`. Conserver cette empreinte hors
   du dépôt de sauvegarde ; recalculer une empreinte sur un index inconnu ne prouve
   pas son authenticité. Elle est aussi enregistrée dans `ops.backup_runs.sha256`.
2. Pour un dépôt chiffré, disposer séparément de la clé privée age correspondante.
   La sauvegarde ne contient pas cette clé. Ne pas la placer dans les variables
   publiques ou dans les arguments de configuration d'un worker permanent.
3. Utiliser un serveur PostgreSQL de test accessible via `DATABASE_URL`, avec un
   compte autorisé à créer une base. Le nom demandé doit commencer par
   `metiquo_restore_`, puis contenir uniquement lettres minuscules, chiffres ou
   underscores, pour un total maximal de 63 caractères. Il doit être différent de
   la base de connexion. Le service se connecte à la base de maintenance
   `postgres` sur le même serveur ; la base sauvegardée n'a pas besoin d'exister.
4. Choisir un dossier inexistant dont le parent existe déjà, hors du dépôt de
   sauvegarde et du stockage source. Les liens, jonctions et remontées de chemin
   sont refusés. Prévoir l'espace nécessaire au dump déchiffré et aux objets.
5. Arrêter la rétention concurrente sur le dépôt pendant sa lecture. Aucun worker
   applicatif ne doit cibler la nouvelle base pendant l'exercice.

Exemple avec des valeurs à remplacer, après configuration des variables privées :

```text
oe restore --backup-id <UUID> --index-sha256 <SHA256_CONSERVE> --target-database metiquo_restore_exercice --target-objects <NOUVEAU_DOSSIER_ABSOLU> --identity <CLE_PRIVEE_AGE> --json
```

Omettre `--identity` pour une sauvegarde en clair. Le client `pg_restore` doit être
compatible avec le dump ; celui de l'image Python est de version majeure 18. Les
chemins d'exécutables peuvent être configurés via `BACKUP_PG_RESTORE_BINARY` et
`BACKUP_AGE_BINARY`. Dans un conteneur, monter le dépôt et la clé en lecture seule,
et uniquement le parent du nouveau dossier en écriture.

## Vérifications et résultat

L'empreinte de l'index est contrôlée en premier, puis celles du manifeste, du dump
et des blobs. Les contenus déchiffrés sont comparés à leurs empreintes et tailles
d'origine. Un identifiant de sauvegarde différent, un chemin invalide, une clé
incorrecte ou un fichier corrompu empêche la création de la base cible.

Le service crée la base depuis `template0`, puis exécute `pg_restore` en transaction
unique, sans restaurer les propriétaires ni les ACL de la source. PostgreSQL
documente cette [restauration transactionnelle](https://www.postgresql.org/docs/18/app-pgrestore.html).
Il vérifie ensuite la révision Alembic, les ensembles d'identifiants de snapshots
et de modèles, ainsi que les fichiers référencés par la base restaurée. Un événement
`backup.restored` est ajouté à son journal central avec la trace de la commande.

Le JSON de succès contient le nom de la nouvelle base, son dossier d'objets, la
révision des migrations et le nombre d'objets vérifiés. Le dossier temporaire de
décryptage est retiré après succès. La commande n'active aucun scheduler, modèle ou
connexion à un provider et ne bascule pas l'application sur cette copie.

Avant la création SQL, un échec nettoie uniquement le dossier réservé par la
commande. Après création de la base, l'ensemble est conservé pour diagnostic et
l'opération est signalée en échec ; cette cible ne doit pas être utilisée comme
restauration validée. Un échec de `pg_restore` annule sa transaction. Choisir une
nouvelle cible pour recommencer, ou supprimer explicitement les seules ressources
de cet exercice après inspection. Les erreurs détaillées des processus externes
ne sont pas imprimées avec des informations de connexion.

## Reconstruire le canonique

Configurer `DATABASE_URL` et `OBJECT_STORE_ROOT` pour la copie validée, puis lancer :

```text
oe rebuild-canonical --from 2014-01-01 --json
```

La commande relit les snapshots validés actifs depuis les raw locaux et vérifie
leur hash et leur taille avant chargement. Si une projection raw manque, le
chargement reprend sa dernière révision conservée avant de rejouer le fichier,
sous le verrou et dans la transaction du chargement. Il ne recrée pas une
révision 1 ni un historique concurrent. Les autres lignes restent préservées.
Les dimensions, games, statistiques, observations de roster et séries sont ensuite
reconstruites depuis la projection courante ; les ambiguïtés restent explicites.
Les modèles, prédictions et preuves financières immuables ne sont pas recalculés.

Le paramètre `--from` sélectionne les fichiers dont la période maximale atteint
la date demandée ; chaque fichier retenu est rejoué en entier. La reconstruction
des tables `core` utilise toute la projection courante. Le rapport distingue
lignes raw depuis cette date, games, séries et observations de roster.

## Exercice reproductible

`tests/integration/test_restore.py` effectue une vraie ingestion de fixture, un
dump et une restauration PostgreSQL, en clair et avec age. Il refuse une mauvaise
empreinte, une corruption et une clé incorrecte avant création SQL, vérifie les
raw et l'objet modèle de fixture, refuse les cibles existantes, puis supprime
uniquement la projection raw dans sa base éphémère. La commande de reconstruction
retrouve les douze clés et empreintes, conserve les douze révisions historiques
et matérialise la game. L'état de la source est comparé après l'exercice. Les bases
créées par le test sont supprimées dans son nettoyage final.

La CI habituelle exécute ces tests avec les migrations. Le workflow
`restore-drill.yml` ajoute un lancement manuel et un exercice hebdomadaire le
dimanche à 03:17 UTC, avec rapport JUnit conservé 30 jours. Sa planification ne
devient effective qu'après publication sur la branche par défaut du dépôt.
Cet exercice utilise des fixtures ; il faut également exercer régulièrement une
copie privée représentative, avec ses modèles enregistrés et ses volumes réels,
avant de considérer le plan de reprise de l'installation validé.
