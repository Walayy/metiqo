# Collecteurs Metiquo

La collecte Stake pré-match et en direct utilise un worker Chrome local distinct ; ses commandes et ses limites figurent dans le [guide Stake](stake-collector.md).

## Démarrage et noms des commandes

Depuis la racine du dépôt, avec Docker Desktop démarré :

```sh
npm run docker:init
npm run docker:up
npm run data:lol:sync
npm run data:oracle:sync
```

`docker:up` construit les images, applique les migrations et démarre le planificateur. Si une collecte est déjà en cours, une commande manuelle pour la même source renvoie **75**, sans lancer de doublon. Attendre la fin de l’exécution ou consulter son état. Les sources LoL et Oracle possèdent des verrous différents et peuvent fonctionner simultanément.

Commandes Docker précises, également utilisables sous PowerShell :

```sh
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-lol-catalog
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-oracles-elixir --latest
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-oracles-elixir --years 2025 2026
```

Sans argument, Oracle traite **toutes les années découvertes**, sans liste d’années fermée. `--latest` découvre la dernière année à chaque exécution : ne pas figer 2026 dans un cron permanent. Une année ciblée implique un fichier compagnon pour l’export groupé Google ; les deux fichiers sont validés et importés. `--latest` et `--years` sont mutuellement exclusifs.

Avec les dépendances locales installées (`uv sync --frozen`, `uv run patchright install chromium`) et `METIQUO_DATABASE_URL` configurée :

```sh
uv run metiquo-worker sync-lol-catalog
uv run metiquo-worker sync-oracles-elixir --latest
uv run metiquo-worker sync-oracles-elixir --years 2026
```

Pour transmettre des options via npm sous PowerShell, utiliser `npm.cmd run data:oracle:sync -- --latest` ; selon la version de PowerShell, `npm.ps1` peut consommer les options destinées au script. Les commandes Docker ci-dessus évitent cette ambiguïté. `catalog:sync` reste un alias vers la nouvelle collecte backend ; `collect` reste un alias Python d’Oracle.

Codes de sortie : **0** succès (y compris données inchangées), **1** échec de collecte, **2** arguments invalides, **75** collecte de la même source déjà en cours. Le dernier message JSON de succès contient l’identifiant d’exécution et le bilan ; les logs vont sur stderr.

## Catalogue : source, relations et publication

1. Lire le registre `Query.leagues` du JSON transporté dans le HTML public LoL Esports. Les données JSON sont analysées sans exécuter le JavaScript ; aucune clé privée ou API interne authentifiée.
2. Parcourir le filtre public `/en-US/leagues/{slug}` pour chaque ligue découverte, y compris une nouvelle ligue inconnue du code. TFT est exclu. Tout échec de page, format non reconnu ou dépassement de la limite de pages interrompt la collecte.
3. Conserver les identités Riot en chaînes, les régions source et les entités de saison, split, tournoi et division effectivement exposées. Un identifiant de région préfixé `riot:region:` est une clé interne dérivée du libellé source, pas un ID Riot prétendu.
4. Conserver les preuves de rattachement : `home` pour `Team.homeLeague`, `tournament` pour la liste de participants d’un tournoi, `match` pour un participant identifié à une rencontre. Les dates viennent de la source. `seasonId` n’est rempli que si la relation figure explicitement dans la source ; une année de date n’est jamais transformée en saison supposée.
5. Télécharger les images officielles déclarées sur `static.lolesports.com` ou déjà observées sur `cdn.loltv.gg`, avec validation et limites. Les originaux et leurs empreintes sont conservés. Pillow convertit les PNG/JPEG/WebP/GIF en WebP, au maximum 144 × 144 px, sans agrandissement. Une URL absente conserve un repli vide. Si un téléchargement échoue, le dernier artefact local vérifié est réutilisé ; sans cache valide, l’identité est publiée sans logo et l’erreur reste comptabilisée, sans détruire la version active précédente.
6. Réutiliser les validateurs HTTP ETag/Last-Modified lorsque disponibles. Un HTTP 304 n’est accepté que si les artefacts locaux sont encore vérifiés. Une même URL dont les octets changent produit une nouvelle empreinte et un nouveau chemin. Sans validateur, la source est relue.
7. Écrire les fichiers sous des chemins contenant leur SHA-256, puis publier les identités et le pointeur de version dans une seule transaction. Les anciennes versions et leurs images restent présentes. Une collecte inchangée actualise `checkedAt` sans dupliquer la version.

Les documents normalisés et les relations sont dans `catalog_versions.document`. Les pages HTML compressées, leurs URLs, dates et empreintes sont référencées dans le bilan de collecte. Les fichiers précèdent la transaction de publication : une panne peut laisser un artefact sans référence, jamais un pointeur actif vers une image en cours d’écriture. Aucune purge automatique n’est réalisée.

Avant publication, les équipes et compétitions explicitement observées par LoLTV sont rapprochées par identifiant fournisseur, alias normalisés et qualificatifs (`Fénix`, `Academy`, `Challengers`, etc.). Ces qualificatifs empêchent de fusionner une équipe secondaire avec son équipe mère. Les alias, identifiants source et URLs d’images à forte confiance sont mémorisés dans les métadonnées privées du catalogue. Une nouvelle collecte Riot conserve ces identités connues même si elles ont disparu des pages du jour ; une participation observée ne devient jamais une affiliation d’origine supposée. Cette conservation vise toutes les identités effectivement découvertes par les sources autorisées, pas une prétendue liste mondiale exhaustive.

Le contrat historique `/catalog` ne possède qu’un `leagueId` par équipe. Sa projection utilise la ligue d’origine lorsqu’elle est sourcée, sinon une participation observée (domestique prioritaire, puis la plus récente). **Ce regroupement ne devient pas une affiliation d’origine.** La base conserve la distinction dans `leagueAssignment` et `affiliations`, accessibles par l’endpoint de référence. Le mode API utilise ces identités réelles.

Les catégories d’affichage `major`, `regional`, `international` comportent une taxonomie éditoriale ; elles ne limitent jamais la découverte. Le référentiel n’est pas un registre exhaustif de rosters ou de contrats. Les divisions absentes et les relations saisonnières manquantes restent non renseignées. La participation historique visible ne prouve pas l’activité actuelle d’une équipe.

Une perte de plus de 20 % des ligues ou équipes par rapport à la version précédente bloque automatiquement la publication. Après vérification d’un changement légitime de couverture, une exécution **manuelle** peut utiliser `sync-lol-catalog --allow-coverage-drop`. Le planificateur n’active jamais cette option.

## Oracle : stockage et reprise

La chaîne existante reste unique : découverte Drive, export ZIP groupé anonyme, contrôle d’inventaire, longueurs et CRC, validation des CSV, SHA-256 et import PostgreSQL en flux. Les pointeurs de toutes les années collectées sont publiés ensemble. Une nouvelle livraison du même fichier ne duplique pas les lignes.

Les valeurs source restent en JSONB, sans confusion entre année du fichier, champ `year` et date. Les données partielles restent identifiées. Le fuseau des dates CSV n’est pas inventé. Voir [l’exploitation backend](backend.md) et [l’audit source](oracles-elixir-audit.md).

## LoLTV : J−7/J+7 et directs

`npm run data:loltv:sync` ou `uv run metiquo-worker sync-loltv-matches` exécute un passage. Le cron `loltv-matches` est modifiable dans **Gestion → Scripts**. La migration `0012` remplace l’ancienne planification, interrompt son ancienne file et conserve les données historiques. Appliquer `alembic upgrade head` avant de démarrer le nouveau worker.

Les listes HTML découvrent les liens et leur pagination. Les dates de Paris bornent J−7/J+7 ; les places TBD sont conservées dans les preuves, sans créer de fausses équipes. Une file PostgreSQL conserve les pages et fiches dues, leur échéance et les cartes terminées acquises. Le prochain passage reprend cette file ; une limite de temps ou de budget ne supprime pas sa couverture restante. Le calendrier est relu avant de conclure qu’un match programmé a commencé. Le détail HTML est publié avant l’enrichissement. Les flux de cartes utilisent la session anonyme normale du site : action découverte dans les scripts liés et mise en cache tant que le même script reste présent, cookies uniquement en mémoire, une lecture par carte nécessaire, aucune relance automatique du POST après erreur. Chaque carte est publiée immédiatement. Les cinq tags de joueurs doivent tous identifier la même équipe source ; les camps de remplissage HTML ne servent jamais au rapprochement.

| Variable (préfixe `METIQUO_`)                         | Défaut                         | Usage                                                                       |
| ----------------------------------------------------- | ------------------------------ | --------------------------------------------------------------------------- |
| `LOLTV_ENABLED`                                       | `true` dans Docker             | Active la file LoLTV                                                        |
| `LOLTV_FEED_ENABLED`                                  | `true`                         | Flux de consultation anonyme des cartes identifiées dans la fiche           |
| `LOLTV_RENDER_LIVE`                                   | `false`                        | Diagnostic optionnel par les onglets DOM                                    |
| `LOLTV_BROWSER_CHANNEL`                               | `chromium`                     | Chromium complet installé avec Patchright                                   |
| `LOLTV_BROWSER_PROFILE_DIR`                           | `.cache/backend/loltv-browser` | Docker : `/data/browser/loltv`, volume dédié                                |
| `LOLTV_MIN_DELAY_SECONDS` / `LOLTV_MAX_DELAY_SECONDS` | 2 / 4                          | Pause entre documents, clics et téléchargements explicites du CDN           |
| `LOLTV_LISTING_INTERVAL_SECONDS`                      | 60                             | Liste des matchs actuels                                                    |
| `LOLTV_RESULTS_INTERVAL_SECONDS`                      | 300                            | Pagination des résultats                                                    |
| `LOLTV_FUTURE_LISTING_INTERVAL_SECONDS`               | 900                            | Pages suivantes du calendrier futur                                         |
| `LOLTV_LIVE_REFRESH_SECONDS`                          | 30                             | Échéance minimale du détail live, adaptée au nombre de directs              |
| `LOLTV_FINISHED_REFRESH_SECONDS`                      | 21600                          | Correction des cartes terminées complètes                                   |
| `LOLTV_INCOMPLETE_REFRESH_SECONDS`                    | 900                            | Résultats incomplets et erreurs hors direct                                 |
| `LOLTV_CYCLE_SECONDS`                                 | 90                             | Budget de temps avant de commencer une nouvelle page                        |
| `LOLTV_REQUEST_BUDGET`                                | 120                            | Documents/actions explicites et logos LoLTV par fenêtre                     |
| `LOLTV_BROWSER_REQUEST_BUDGET`                        | 600                            | Requêtes naturelles observées du contexte par fenêtre                       |
| `LOLTV_BUDGET_WINDOW_SECONDS`                         | 600                            | Fenêtre persistante de budget                                               |
| `LOLTV_BLOCK_COOLDOWN_SECONDS`                        | 900                            | Base du délai progressif après refus, maximum six heures hors `Retry-After` |

Ces valeurs sont des échéances minimales, pas une garantie de fraîcheur. Une lecture commencée termine ou atteint son timeout avant la sortie du cycle. Le plafond des requêtes naturelles est observé au départ des requêtes : une requête déjà partie ne peut pas être annulée rétroactivement. Aucun routage global ne désactive le cache HTTP.

À score, statut et horaire identiques, les métadonnées d’une fiche live restent utilisables quinze minutes : seul le flux utile est relu, avec une session anonyme propre à la rencontre, réutilisable cinq minutes au maximum et sans dépasser l’expiration du cookie. Les cookies restent dans la mémoire du thread, sont remplacés lors d’un changement de rencontre et ne sont jamais sérialisés. Un 401 invalide la session sans refaire son POST pendant la même lecture. Un changement de score/statut impose une nouvelle fiche pour identifier la carte suivante. Le cache ne republie jamais ses anciennes statistiques ; `metadataObservedAt` et l’horodatage source du flux restent distincts. Les compteurs `cachedMetadata` et `reusedSessions` mesurent les requêtes évitées. Les pages non commencées et les cartes terminées acquises ne génèrent pas de lecture de flux inutile.

Avec `* * * * *` ou `*/1 * * * *`, le planificateur vérifie aussi les échéances live entre les minutes (réveil toutes les cinq secondes), sans créer de file parallèle. Les autres crons et la pause désactivent ces réveils intermédiaires. Un live redevenu dû reprend la priorité entre deux lectures historiques, même pendant un cycle long. Sa cadence minimale est le maximum du réglage live et du temps nécessaire pour répartir tous les directs sur 70 % du budget ; les 30 % restants constituent une marge de calcul pour les listes, sessions et corrections, pas un budget supplémentaire. Le plafond global reste prioritaire. Les erreurs temporaires live attendent 60 puis 120 secondes, au lieu de quinze minutes ; un refus 403/429 conserve son délai distinct. La carte en cours est lue avant les compléments terminés ; une carte invalide ne bloque pas la publication des autres cartes valides. `sourceLagSeconds` décrit l’âge du relevé source à sa récupération, sans le rajeunir.

Entre deux cartes, ou quand le flux indique `COMPLETED` avant que le HTML publie le vainqueur, les métadonnées sont revérifiées après une minute au lieu de rester figées quinze minutes. Le flux terminé n’est plus relu dans cette attente ; il est relu une fois quand le résultat HTML permet de publier une carte réglée. `feedStates` conserve l’état et l’horodatage effectivement lus, sans déduire un vainqueur. La correction historique garde son propre cache. Cela évite à la fois une composition vide pendant la carte suivante et le téléchargement répété d’un ancien relevé final.

Le premier 403/429 conserve URL sans paramètres, type de ressource, statut et délai dans `collector_state`, ferme le contexte éventuel et arrête le cycle. `Retry-After` est prioritaire. Les dernières données valides restent accessibles. L’état est publié sur `/api/v1/sources/loltv` ; les compteurs et erreurs sont dans `ingestion_runs.details`, les preuves dans `/data/artifacts/loltv-pages`, `loltv-resources` et, en mode DOM, `loltv-dom`. Les corps et cookies des réponses de création de session ne sont pas archivés.

Les sources catalogue, Oracle et LoLTV ont des files et verrous indépendants. Une actualisation frontend ne déclenche jamais de scrape. Voir [l’analyse des données et les limites vérifiées](loltv.md).

## Tests PostgreSQL isolés

Le test refuse de réinitialiser une base qui ne finit pas par `_test`. Il ne faut jamais utiliser la base applicative.

```sh
docker compose --env-file .env.docker exec -T db psql -U metiquo -d metiquo -c 'CREATE DATABASE metiquo_loltv_test'
docker compose --env-file .env.docker -f compose.yaml -f compose.test.yaml build backend-tests
docker compose --env-file .env.docker -f compose.yaml -f compose.test.yaml run --rm --no-deps backend-tests
```

La création de base n’est nécessaire qu’une fois. Aucun port PostgreSQL n’est publié. Les identifiants sont transmis par `.env.docker`, jamais écrits dans les tests ou les logs.
