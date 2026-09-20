# Collecteurs LoL et Oracle’s Elixir

Les deux commandes s’exécutent dans `apps/worker`, publient dans PostgreSQL et écrivent leurs fichiers dans `METIQUO_ARTIFACT_DIR`. L’API les lit sans accès aux sites sources. Elles ne modifient ni les composants, ni les fixtures, ni les logos historiques du frontend.

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
5. Télécharger les images déclarées sur `static.lolesports.com`, avec validation et limites. Les originaux et leurs empreintes sont conservés. Pillow convertit les PNG/JPEG/WebP/GIF en WebP, au maximum 144 × 144 px, sans agrandissement. Une URL absente conserve un repli vide ; une image déclarée invalide fait échouer la publication. Un format supplémentaire nécessite un adaptateur testé.
6. Réutiliser les validateurs HTTP ETag/Last-Modified lorsque disponibles. Un HTTP 304 n’est accepté que si les artefacts locaux sont encore vérifiés. Une même URL dont les octets changent produit une nouvelle empreinte et un nouveau chemin. Sans validateur, la source est relue.
7. Écrire les fichiers sous des chemins contenant leur SHA-256, puis publier les identités et le pointeur de version dans une seule transaction. Les anciennes versions et leurs images restent présentes. Une collecte inchangée actualise `checkedAt` sans dupliquer la version.

Les documents normalisés et les relations sont dans `catalog_versions.document`. Les pages HTML compressées, leurs URLs, dates et empreintes sont référencées dans le bilan de collecte. Les fichiers précèdent la transaction de publication : une panne peut laisser un artefact sans référence, jamais un pointeur actif vers une image en cours d’écriture. Aucune purge automatique n’est réalisée.

Le contrat historique `/catalog` ne possède qu’un `leagueId` par équipe. Sa projection utilise la ligue d’origine lorsqu’elle est sourcée, sinon une participation observée (domestique prioritaire, puis la plus récente). **Ce regroupement ne devient pas une affiliation d’origine.** La base conserve la distinction dans `leagueAssignment` et `affiliations`, accessibles par l’endpoint de référence. Les composants restent en mock ; cette distinction devra être présentée lors du futur raccordement de l’interface à ces données.

Les catégories d’affichage `major`, `regional`, `international` comportent une taxonomie éditoriale ; elles ne limitent jamais la découverte. Le référentiel n’est pas un registre exhaustif de rosters ou de contrats. Les divisions absentes et les relations saisonnières manquantes restent non renseignées. La participation historique visible ne prouve pas l’activité actuelle d’une équipe.

Une perte de plus de 20 % des ligues ou équipes par rapport à la version précédente bloque automatiquement la publication. Après vérification d’un changement légitime de couverture, une exécution **manuelle** peut utiliser `sync-lol-catalog --allow-coverage-drop`. Le planificateur n’active jamais cette option.

## Oracle : stockage et reprise

La chaîne existante reste unique : découverte Drive, export ZIP groupé anonyme, contrôle d’inventaire, longueurs et CRC, validation des CSV, SHA-256 et import PostgreSQL en flux. Les pointeurs de toutes les années collectées sont publiés ensemble. Une nouvelle livraison du même fichier ne duplique pas les lignes.

Les valeurs source restent en JSONB, sans confusion entre année du fichier, champ `year` et date. Les données partielles restent identifiées. Le fuseau des dates CSV n’est pas inventé. Voir [l’exploitation backend](backend.md) et [l’audit source](oracles-elixir-audit.md).

## SofaScore : rencontres J−7 à J+7 et directs

La commande `sync-sofascore-matches` lit les pages LoL SofaScore avec Patchright, sans client HTTP d’API SofaScore. Elle découvre les liens rendus sur chaque journée de la fenêtre J−7 à J+7, ouvre chaque fiche, extrait le statut, l’horaire, les équipes, la compétition et les scores explicitement exposés, puis publie un snapshot durable. Elle tente aussi d’ouvrir l’onglet rendu `Matchs`/`Matches` pour les détails d’une carte. Les statistiques de carte (bans, kills, CS, niveaux, champions, joueurs et objectifs) restent inconnues si la fiche ne les rend pas ; le worker ne les invente pas.

Oracle’s Elixir complète les cartes terminées après chaque import. Une carte n’est publiée que si Oracle fournit ses deux camps, cinq joueurs et les champs statistiques requis. L’API utilise le dernier état SofaScore pour le direct et le dernier snapshot non vide pour les cartes : un relevé live partiel ne supprime donc pas les cartes historiques déjà publiées.

```sh
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-sofascore-matches
uv run metiquo-worker sync-sofascore-matches
```

La planification par défaut est `*/1 * * * *` en heure de Paris. Elle est persistée dans `script_schedules` et modifiable dans **Admin → Scripts & planifications** ; cette cadence fréquente sert notamment aux rencontres en direct. `METIQUO_SOFASCORE_ENABLED` est l’interrupteur du worker. Le script ne contacte jamais Stake.

Chaque événement est rattaché à `match_source_links` par fournisseur et identifiant SofaScore. En l’absence de lien connu, le matching compare les équipes et leurs alias, l’ordre des camps, la compétition et une fenêtre horaire de 72 heures ; les cas ambigus sont refusés. Les snapshots `match_snapshots` sont dédupliqués par empreinte, avec URL et horodatage, et `/api/v1/sources/sofascore` expose les bilans.

## Planification intégrée ou cron

`metiquo-worker serve` consomme les planifications et la file persistées en PostgreSQL, configurables dans **Admin → Scripts & planifications** :

- Catalogue : `0 4 * * *`, chaque jour à 04:00, heure de Paris.
- Oracle récent : `0 */6 * * *`, à 00:00, 06:00, 12:00 et 18:00, heure de Paris.
- Oracle complet : `0 3 * * 0`, le dimanche à 03:00, heure de Paris.
- La migration crée une prochaine échéance future ; un premier import immédiat se lance manuellement.
- Les échéances survivent aux redémarrages. Après une panne, une seule collecte rattrape les échéances manquées pour chaque script.
- Les échecs restent visibles et n’empêchent pas les autres scripts de s’exécuter. Le prochain cron ou une action manuelle permet une nouvelle tentative. Si une commande CLI détient le verrou de la source, la file réessaie après une minute.
- Les jobs de la file s’exécutent en série, avec un verrou PostgreSQL qui empêche deux workers de consommer le même job. `serve --only lol-catalog` ou `serve --only oracles-elixir` limite le processus à une source ; l’interface est prévue pour un worker supervisé unique.
- Le heartbeat est actualisé toutes les 20 secondes, même pendant une collecte longue ; après 90 secondes sans contact, les lancements manuels sont désactivés. Le worker vérifie la file toutes les cinq secondes entre deux collectes.
- Les anciens intervalles en secondes ne configurent plus `serve`. Les interrupteurs `*_ENABLED` restent prioritaires. La pause Admin arrête les futures échéances, sans annuler une demande déjà en file ni une collecte en cours.

Voir [le guide d’administration](administration.md) pour les permissions et les limites.

La planification intégrée suffit sous Docker et Windows. Pour utiliser un cron Linux à sa place, arrêter le service `worker` persistant et employer les commandes ponctuelles. Exemple à adapter au chemin réel et au fuseau du serveur :

```cron
15 2 * * * cd /srv/metiquo && /usr/bin/docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-lol-catalog >> /var/log/metiquo-lol.log 2>&1
30 */6 * * 1-6 cd /srv/metiquo && /usr/bin/docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-oracles-elixir --latest >> /var/log/metiquo-oracle.log 2>&1
30 6,12,18 * * 0 cd /srv/metiquo && /usr/bin/docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-oracles-elixir --latest >> /var/log/metiquo-oracle.log 2>&1
30 0 * * 0 cd /srv/metiquo && /usr/bin/docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-oracles-elixir >> /var/log/metiquo-oracle.log 2>&1
```

Ces exemples ne créent aucun cron sur la machine. Le cron externe doit superviser les codes de sortie et gérer ses relances ; la commande ponctuelle ne passe pas par la file Admin. Un nouvel `docker:up` peut redémarrer le planificateur intégré : choisir un seul mode de planification par source.

## Configuration et état

- `METIQUO_CATALOG_ENABLED=true` : autorise le collecteur, manuel et planifié.
- Les cadences sont stockées dans `script_schedules` et modifiées depuis Admin.
- `METIQUO_CATALOG_MAX_PAGES=200` : plafond de découverte, échec explicite si dépassé.
- `METIQUO_CATALOG_MAX_PAGE_BYTES=15000000`, `METIQUO_CATALOG_MAX_IMAGE_BYTES=10000000` : limites de réponse.
- `METIQUO_CATALOG_MAX_IMAGE_PIXELS=80000000` : limite de décodage, réglable à la baisse. Les grandes images sont décodées une par une puis réduites avant conversion pour borner la mémoire ; l’original LOUD sourcé mesure 8334 × 8334 px.
- `METIQUO_CATALOG_TIMEOUT_SECONDS=60` : délai réseau par requête.
- `METIQUO_ORACLE_ENABLED=true` : activation des collectes Oracle. Les anciennes variables d’intervalle ne pilotent plus le planificateur.
- `METIQUO_SOFASCORE_ENABLED=true` : activation du scraping rendu SofaScore et du suivi des rencontres.
- `METIQUO_SOFASCORE_MIN_DELAY_SECONDS=2` et `METIQUO_SOFASCORE_MAX_DELAY_SECONDS=5` : délai aléatoire entre deux navigations du navigateur ; le minimum et le maximum sont bornés pour éviter les rafales.
- `METIQUO_SOFASCORE_LISTING_DAYS_PER_RUN=2` : nombre maximal de pages de journées découvertes par exécution ; la fenêtre J−7 à J+7 est remplie progressivement.
- `METIQUO_SOFASCORE_EVENTS_PER_RUN=12` : nombre maximal de fiches de rencontres ouvertes par exécution ; les rencontres non encore découvertes restent dans la file mémoire.
- `METIQUO_SOFASCORE_LISTING_INTERVAL_SECONDS=300` : durée de cache des pages de découverte de la fenêtre J−7 à J+7. `METIQUO_SOFASCORE_SCHEDULED_REFRESH_SECONDS=300` limite la relecture des rencontres à venir proches de leur horaire ; une rencontre live utilise `METIQUO_SOFASCORE_LIVE_REFRESH_SECONDS=60`.
- `METIQUO_SOFASCORE_BLOCK_COOLDOWN_SECONDS=900` : après un `403` ou `429`, le worker arrête les navigations SofaScore pendant cette durée et conserve les derniers relevés connus. Il ne tente ni proxy, ni contournement, ni endpoint API.
- `METIQUO_ARTIFACT_DIR` : volume commun aux CSV, pages et logos ; écriture worker, lecture seule API.

Compose transmet les interrupteurs d’activation depuis `.env.docker` ; les cadences viennent de PostgreSQL. Les paramètres avancés peuvent être ajoutés à `environment` ou passés avec `docker compose run -e METIQUO_…=…`. Un paramètre ajouté uniquement au fichier `.env.docker` n’est pas automatiquement injecté dans le conteneur.

- `/api/v1/sources/lol-esports` : version active, dernière vérification, vingt dernières exécutions et leurs bilans.
- `/api/v1/sources/lol-esports/reference` : document de la version active ; `?versionId=…` permet de lire une ancienne version.
- `/api/v1/catalog` : projection compatible avec le contrat existant, lue depuis une seule version.
- `/api/v1/catalog/logos/{sha256}.webp` : image locale immuable, ETag et cache HTTP.
- `/api/v1/sources/oracles-elixir` et `/datasets` : exécutions et versions actives Oracle.

`retrievedAt` date la version conservée ; `checkedAt` date la dernière vérification réussie. Une ancienne version disponible ne signifie pas que la source est à jour. Les erreurs ne déclenchent aucun passage en mock côté API.
