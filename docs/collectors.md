# Collecteurs LoL Esports, Oracle’s Elixir et SofaScore

## Session persistante et cache renforcé — 21 septembre 2026

Les valeurs du tableau intègrent la correction suivante demandée par l'utilisateur : abandon des caches de 6/24 heures et réduction de celui d'aujourd'hui. Une échéance de cache rend la page éligible au prochain passage disponible ; elle ne remplace pas le cron et ne garantit pas un intervalle réel identique quand une collecte est longue. Les pauses après chaque page et la suspension après refus restent inchangées.

Cette demande remplace les anciennes cadences SofaScore mentionnées dans les sections historiques. Chromium utilise un profil persistant dédié, réutilisé entre pages et cycles. Son cache HTTP et ses cookies sont conservés entre redémarrages. Le volume Docker `sofascore_browser` est monté uniquement dans le worker sur `/data/browser` ; il ne contient pas de données à publier et n'est pas partagé avec le navigateur personnel. Aucun `page.route()` n'est installé. Les ressources du site chargent normalement ; les réponses JSON ne sont jamais exploitées.

Chaque cycle visite une page au plus une fois, y compris après une erreur ; les liens alternatifs et recommandations sont dédupliqués par identifiant SofaScore. Les cartes terminées d'une série live ne sont plus activées pour récupérer les mêmes données. Les mises à jour des autres cartes sont publiées avec leur nouvelle provenance, tandis que les cartes historiques restent celles de leurs observations originales. Les journées découvertes sont enregistrées progressivement ; le cache des matchs est validé après leur publication. Une publication échouée ne marque pas ses cartes comme déjà acquises.

| Variable `METIQUO_…`                                          | Valeur par défaut                                                     | Rôle                                                              |
| ------------------------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `SOFASCORE_BROWSER_PROFILE_DIR`                               | `.cache/backend/sofascore-browser` ; Docker `/data/browser/sofascore` | Profil Chromium privé, persistant                                 |
| `SOFASCORE_MIN_DELAY_SECONDS` / `SOFASCORE_MAX_DELAY_SECONDS` | 15 / 30                                                               | Pause après fin de lecture et mise au repos de la page précédente |
| `SOFASCORE_LISTING_INTERVAL_SECONDS`                          | 180                                                                   | Relecture de la journée courante                                  |
| `SOFASCORE_PAST_LISTING_INTERVAL_SECONDS`                     | 3600                                                                  | Relecture des journées passées                                    |
| `SOFASCORE_FUTURE_LISTING_INTERVAL_SECONDS`                   | 900                                                                   | Relecture des journées futures                                    |
| `SOFASCORE_LIVE_REFRESH_SECONDS`                              | 120                                                                   | Intervalle minimal entre relevés live                             |
| `SOFASCORE_SCHEDULED_REFRESH_SECONDS`                         | 180                                                                   | Match proche du début, reporté, ou tentative non interprétable    |
| `SOFASCORE_UPCOMING_REFRESH_SECONDS`                          | 900                                                                   | Match programmé à plus de trente minutes                          |
| `SOFASCORE_FINISHED_REFRESH_SECONDS`                          | 3600                                                                  | Match terminé avec cartes                                         |
| `SOFASCORE_INCOMPLETE_REFRESH_SECONDS`                        | 300                                                                   | Match terminé encore sans cartes                                  |
| `SOFASCORE_BLOCK_COOLDOWN_SECONDS`                            | 900                                                                   | Base du délai progressif après refus, prolongé par `Retry-After`  |

Les pauses de 4–8 secondes entre tentatives d'onglets s'appliquent aussi après un clic échoué. L'onglet déjà sélectionné n'est pas recliqué. Le premier 403/429 observé coupe le réseau du contexte, ferme ses pages et termine le cycle : aucune navigation suivante ou relance interne. Les requêtes du site déjà émises avant la détection peuvent néanmoins atteindre le serveur. La suspension reste enregistrée en PostgreSQL et partagée avec les logos. L'ordonnanceur respecte son échéance sans accumuler plusieurs collectes concurrentes ; aucun plafond de matchs n'est réintroduit.

Une page vide `about:blank` arrête les actualisations de fond pendant l'attente et entre cycles, sans recréer le contexte. La couverture J−7/J+7 est conservée, mais ces pauses et caches peuvent retarder la découverte d'une modification et prolonger un passage au-delà du cron. Ces durées sont un compromis de charge, pas une garantie d'acceptation par SofaScore.

Le worker de l'application a été arrêté pour cette modification. Le « go » explicite reçu le 21 septembre après la refonte des cartes autorise sa reconstruction et son redémarrage, ainsi que la reprise des collectes planifiées avec ces protections. Les tests hors ligne utilisent un profil temporaire et des ressources synthétiques, jamais le profil Docker de production.

La relance à 15:43 reçoit toutefois un [nouveau 403 à 15:46:40](sofascore-403-2026-09-21-1546.md). Le worker est arrêté pendant ce diagnostic. La correction locale enregistre les métadonnées et le délai du refus avant la fermeture des pages : celle-ci peut rendre la main à la navigation interrompue et au nettoyage du cycle. L'ancien ordre pouvait perdre cette persistance et laisser l'ordonnanceur utiliser son délai de repli. Correction reproduite et vérifiée hors réseau, pas encore déployée ; aucune garantie de déblocage côté source.

## Reprise et robustesse — 21 septembre 2026

Appliquer **0009** avant le nouveau worker. `collector_state` conserve le délai après refus, le dernier accès explicite et le checkpoint de découverte. Le délai est commun au navigateur et aux téléchargements de logos ; `Retry-After` est respecté, avec attente progressive en cas de refus répétés. Une commande manuelle ne contourne pas cette attente. Le planificateur reporte le job en file jusqu’à `available_at`. Les paramètres de cadence existants sont inchangés.

Les sources disposent désormais de files d’exécution indépendantes et de verrous par source ; un import Oracle long n’arrête pas la cadence SofaScore. Les relectures du cache ne produisent aucune observation. Les lots partiellement lus sont conservés en cas de refus ultérieur et les fiches terminées restent éligibles à une revisite après six heures. Les corps JSON des requêtes du site ne sont pas exploités et le navigateur reste sur une page vide entre deux exécutions, en conservant son contexte durant le processus.

Appliquer également la migration `0010` : son index concurrent sur la version et la date brute Oracle évite de parcourir toutes les années pour rapprocher quelques jours. Le worker fusionne les plages de dates qui se recouvrent avant la requête, puis applique les mêmes critères stricts d’identité et d’horaire. Aucune convention de fuseau n’est déduite de l’index.

Les logos officiels déjà vérifiés sont réutilisés pendant 24 heures, puis révalidés. Les tournois peuvent hériter du logo de leur parent explicitement observé. `logoCoverage` liste les ligues dépourvues de logo local ; l’interface leur attribue une icône générique accessible. Voir [l’audit détaillé](sofascore-resilience-audit.md) pour les sources, les compteurs et les limites Oracle encore présentes.

Les collecteurs s’exécutent dans `apps/worker` et publient dans PostgreSQL. Les fichiers du catalogue et d’Oracle sont versionnés dans `METIQUO_ARTIFACT_DIR` ; SofaScore conserve ses observations dans les snapshots PostgreSQL. L’API les lit sans accès aux sites sources. Ces commandes ne modifient ni les composants, ni les fixtures, ni les logos historiques du frontend.

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
5. Télécharger les images officielles déclarées sur `static.lolesports.com` ou déjà observées sur `img.sofascore.com`, avec validation et limites. Les originaux et leurs empreintes sont conservés. Pillow convertit les PNG/JPEG/WebP/GIF en WebP, au maximum 144 × 144 px, sans agrandissement. Une URL absente conserve un repli vide. Si un téléchargement échoue, le dernier artefact local vérifié est réutilisé ; sans cache valide, l’identité est publiée sans logo et l’erreur reste comptabilisée, sans détruire la version active précédente.
6. Réutiliser les validateurs HTTP ETag/Last-Modified lorsque disponibles. Un HTTP 304 n’est accepté que si les artefacts locaux sont encore vérifiés. Une même URL dont les octets changent produit une nouvelle empreinte et un nouveau chemin. Sans validateur, la source est relue.
7. Écrire les fichiers sous des chemins contenant leur SHA-256, puis publier les identités et le pointeur de version dans une seule transaction. Les anciennes versions et leurs images restent présentes. Une collecte inchangée actualise `checkedAt` sans dupliquer la version.

Les documents normalisés et les relations sont dans `catalog_versions.document`. Les pages HTML compressées, leurs URLs, dates et empreintes sont référencées dans le bilan de collecte. Les fichiers précèdent la transaction de publication : une panne peut laisser un artefact sans référence, jamais un pointeur actif vers une image en cours d’écriture. Aucune purge automatique n’est réalisée.

Avant publication, les équipes et compétitions explicitement observées par SofaScore sont rapprochées par identifiant fournisseur, alias normalisés et qualificatifs (`Fénix`, `Academy`, `Challengers`, etc.). Ces qualificatifs empêchent de fusionner une équipe secondaire avec son équipe mère. Les alias, identifiants source et URLs d’images à forte confiance sont mémorisés dans les métadonnées privées du catalogue. Une nouvelle collecte Riot conserve ces identités connues même si elles ont disparu des pages du jour ; une participation observée ne devient jamais une affiliation d’origine supposée. Cette conservation vise toutes les identités effectivement découvertes par les sources autorisées, pas une prétendue liste mondiale exhaustive.

Le contrat historique `/catalog` ne possède qu’un `leagueId` par équipe. Sa projection utilise la ligue d’origine lorsqu’elle est sourcée, sinon une participation observée (domestique prioritaire, puis la plus récente). **Ce regroupement ne devient pas une affiliation d’origine.** La base conserve la distinction dans `leagueAssignment` et `affiliations`, accessibles par l’endpoint de référence. Les composants restent en mock ; cette distinction devra être présentée lors du futur raccordement de l’interface à ces données.

Les catégories d’affichage `major`, `regional`, `international` comportent une taxonomie éditoriale ; elles ne limitent jamais la découverte. Le référentiel n’est pas un registre exhaustif de rosters ou de contrats. Les divisions absentes et les relations saisonnières manquantes restent non renseignées. La participation historique visible ne prouve pas l’activité actuelle d’une équipe.

Une perte de plus de 20 % des ligues ou équipes par rapport à la version précédente bloque automatiquement la publication. Après vérification d’un changement légitime de couverture, une exécution **manuelle** peut utiliser `sync-lol-catalog --allow-coverage-drop`. Le planificateur n’active jamais cette option.

## Oracle : stockage et reprise

La chaîne existante reste unique : découverte Drive, export ZIP groupé anonyme, contrôle d’inventaire, longueurs et CRC, validation des CSV, SHA-256 et import PostgreSQL en flux. Les pointeurs de toutes les années collectées sont publiés ensemble. Une nouvelle livraison du même fichier ne duplique pas les lignes.

Les valeurs source restent en JSONB, sans confusion entre année du fichier, champ `year` et date. Les données partielles restent identifiées. Le fuseau des dates CSV n’est pas inventé. Voir [l’exploitation backend](backend.md) et [l’audit source](oracles-elixir-audit.md).

## SofaScore : rencontres J−7 à J+7 et directs

La commande `sync-sofascore-matches` lit les pages LoL SofaScore avec Patchright. Elle découvre les liens rendus sur chaque journée de la fenêtre J−7 à J+7, ouvre chaque fiche, extrait le statut, l’horaire, les équipes, la compétition et les scores explicitement exposés, puis publie un snapshot durable. Elle parcourt aussi chaque onglet rendu `Carte`/`Game` et interprète les libellés français ou anglais. Depuis la demande suivante du 21 septembre, aucun enrichissement HTTP ni interception de corps JSON n’est utilisé. Le parseur conserve le DOM rendu et le JSON SSR `__NEXT_DATA__` embarqué dans le HTML. Les requêtes naturelles du site restent autorisées ; leurs refus sont surveillés sans lire les données API. Les portraits sans libellé identifiable gardent un nom inconnu ; les bans auparavant fournis uniquement par l’API ne sont plus collectés par cette voie. Les cartes déjà terminées sont publiées pendant la série avec objectifs, joueurs, niveaux, K/D/A, CS, or, noms, images de champions et bans lorsqu’ils sont disponibles. Les durées, bans ou noms non exposés restent inconnus et leur absence ne supprime plus les autres informations de la carte.

Le réseau Docker `ingestion` active IPv4 et IPv6. Sur l’environnement de validation du 20 septembre 2026, le frontal Fastly de SofaScore refusait le chemin IPv4 public avec un `403`, alors que le même Chromium, le même code et la même machine obtenaient `200` par IPv6. Cette configuration n’est ni un proxy ni une falsification d’en-têtes ; elle laisse le navigateur utiliser la connectivité dual-stack déjà disponible sur l’hôte. Sans connectivité IPv6 sortante, Chromium revient à IPv4 et un refus propre à cette adresse reste possible.

Oracle’s Elixir complète les cartes terminées après chaque import. Une carte n’est publiée que si Oracle fournit ses deux camps, cinq joueurs et les champs statistiques requis. L’API utilise le dernier état SofaScore et conserve chaque carte compatible déjà publiée. Le score de série vient de la source, pas du nombre de cartes disponibles. Oracle ne clôture une série que si les cartes satisfont le format sourcé indépendant ; un historique partiel ne transforme jamais un BO5 en BO1 ou BO3.

```sh
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-sofascore-matches
uv run metiquo-worker sync-sofascore-matches
```

La planification par défaut est `*/1 * * * *` en heure de Paris. Elle est persistée dans `script_schedules` et modifiable dans **Admin → Scripts & planifications** ; cette cadence fréquente sert notamment aux rencontres en direct. `METIQUO_SOFASCORE_ENABLED` est l’interrupteur du worker. Le script ne contacte jamais Stake.

Chaque événement est rattaché à `match_source_links` par fournisseur et identifiant SofaScore. En l’absence de lien connu, le matching compare les équipes et leurs alias observés, l’ordre des camps, la compétition et une fenêtre horaire de 72 heures. Un cas ambigu n’est pas fusionné avec un autre fournisseur, mais son identifiant SofaScore distinct reste publié comme rencontre sourcée. Les phases `Regular Season`, `Playoffs`, `Play-ins`, `Group Stage`, `Qualifiers` et `Promotion` héritent du logo local lorsque leur nom de base, leur slug ou le tournoi parent explicitement publié correspond à une ligue du catalogue. Un match terminé sans cartes n’est pas considéré stable : il est revisité afin de réparer un relevé incomplet. Les snapshots `match_snapshots` sont dédupliqués par empreinte, avec URL et horodatage, tandis que `match_source_links.last_seen_at` est actualisé à chaque observation ; l’API utilise ce dernier champ pour l’heure « Relevé à ». `/api/v1/sources/sofascore` expose les bilans.

## Planification intégrée ou cron

`metiquo-worker serve` consomme les planifications et la file persistées en PostgreSQL, configurables dans **Admin → Scripts & planifications** :

- Catalogue : `0 4 * * *`, chaque jour à 04:00, heure de Paris.
- Oracle récent : `0 */6 * * *`, à 00:00, 06:00, 12:00 et 18:00, heure de Paris.
- Oracle complet : `0 3 * * 0`, le dimanche à 03:00, heure de Paris.
- La migration crée une prochaine échéance future ; un premier import immédiat se lance manuellement.
- Les échéances survivent aux redémarrages. Après une panne, une seule collecte rattrape les échéances manquées pour chaque script.
- Les échecs restent visibles et n’empêchent pas les autres scripts de s’exécuter. Le prochain cron ou une action manuelle permet une nouvelle tentative. Si une commande CLI détient le verrou de la source, la file réessaie après une minute.
- Les jobs d’une même source s’exécutent en série, avec un verrou PostgreSQL qui empêche deux workers de consommer le même job ; les sources distinctes disposent de boucles indépendantes. `serve --only lol-catalog` ou `serve --only oracles-elixir` limite le processus à une source ; l’interface est prévue pour un worker supervisé unique.
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

- `METIQUO_ORACLE_DATE_TIMEZONE` : fuseau IANA des dates CSV dépourvues d’offset, à renseigner seulement après vérification de la convention source. Vide par défaut : les CSV restent conservés, mais ces dates ne sont pas utilisées pour le rapprochement temporel. Les dates avec offset restent exploitables.
- La déduplication SofaScore concerne uniquement les états consécutifs identiques. Un retour A → B → A produit trois observations ; la migration `0008` retire l’unicité globale de l’empreinte. Les snapshots restent immuables et le rôle worker ne peut toujours ni les modifier ni les supprimer. La migration rétablit également les formats depuis le champ `bestOf` explicite de la dernière observation SofaScore.
- Seules les fiches dont la catégorie source est `lol` sont admises. Les anciennes recommandations d’autres jeux restent archivées et sont exclues du calendrier et des identités SofaScore du catalogue LoL.
- Un cache non revisité ne met jamais `last_seen_at` à jour. Les blocages de navigation restent des échecs visibles, même en présence d’un cache. Aucun enrichissement API SofaScore ne subsiste.
- Le score d’éliminations n’établit pas le vainqueur ; sans marqueur de victoire, la carte terminée n’est pas publiée. Home/away n’indique pas le côté bleu/rouge : ce côté reste `null` dans le relevé SofaScore. Les doublons de bans sont dédupliqués avant projection.
- Le contrôle de chute de couverture Riot compare les identités réellement redécouvertes avant réintégration des identités historiques. La conservation de l’historique ne peut donc plus masquer une perte de couverture.

- `METIQUO_CATALOG_ENABLED=true` : autorise le collecteur, manuel et planifié.
- Les cadences sont stockées dans `script_schedules` et modifiées depuis Admin.
- `METIQUO_CATALOG_MAX_PAGES=200` : plafond de découverte, échec explicite si dépassé.
- `METIQUO_CATALOG_MAX_PAGE_BYTES=15000000`, `METIQUO_CATALOG_MAX_IMAGE_BYTES=10000000` : limites de réponse.
- `METIQUO_CATALOG_MAX_IMAGE_PIXELS=80000000` : limite de décodage, réglable à la baisse. Les grandes images sont décodées une par une puis réduites avant conversion pour borner la mémoire ; l’original LOUD sourcé mesure 8334 × 8334 px.
- `METIQUO_CATALOG_TIMEOUT_SECONDS=60` : délai réseau par requête.
- `METIQUO_ORACLE_ENABLED=true` : activation des collectes Oracle. Les anciennes variables d’intervalle ne pilotent plus le planificateur.
- `METIQUO_SOFASCORE_ENABLED=true` : activation du scraping rendu SofaScore et du suivi des rencontres.
- `METIQUO_SOFASCORE_MIN_DELAY_SECONDS=2` et `METIQUO_SOFASCORE_MAX_DELAY_SECONDS=5` : délai aléatoire entre deux navigations du navigateur ; le minimum et le maximum sont bornés pour éviter les rafales.
- Aucun plafond de journées ou de fiches par passage : toutes les pages dues de J−7 à J+7 sont visitées séquentiellement. Les anciennes variables `METIQUO_SOFASCORE_MAX_EVENTS`, `METIQUO_SOFASCORE_EVENTS_PER_RUN` et `METIQUO_SOFASCORE_LISTING_DAYS_PER_RUN` sont ignorées et peuvent être retirées des fichiers locaux. Le cron peut échoir pendant un passage long ; aucun passage concurrent de la même source n’est lancé.
- `METIQUO_SOFASCORE_LISTING_INTERVAL_SECONDS=300` : durée de cache des pages de découverte de la fenêtre J−7 à J+7. `METIQUO_SOFASCORE_SCHEDULED_REFRESH_SECONDS=300` limite la relecture des rencontres à venir proches de leur horaire ; une rencontre live utilise `METIQUO_SOFASCORE_LIVE_REFRESH_SECONDS=60`.
- `METIQUO_SOFASCORE_BLOCK_COOLDOWN_SECONDS=900` : après un `403` ou `429`, le worker arrête les accès explicites SofaScore au moins pendant cette durée, respecte Retry-After et augmente l’attente si le refus se répète et conserve les derniers relevés connus. Le refus conserve aussi l’URL sans paramètres et le type de ressource dans `collector_state` ; les anciennes entrées ne permettent pas toujours de distinguer document et XHR. Aucun appel API direct n’est utilisé pour compléter un relevé.
- `METIQUO_ARTIFACT_DIR` : volume commun aux CSV, pages et logos ; écriture worker, lecture seule API.

Compose transmet les interrupteurs d’activation depuis `.env.docker` ; les cadences viennent de PostgreSQL. Les paramètres avancés peuvent être ajoutés à `environment` ou passés avec `docker compose run -e METIQUO_…=…`. Un paramètre ajouté uniquement au fichier `.env.docker` n’est pas automatiquement injecté dans le conteneur.

- `/api/v1/sources/lol-esports` : version active, dernière vérification, vingt dernières exécutions et leurs bilans.
- `/api/v1/sources/lol-esports/reference` : document de la version active ; `?versionId=…` permet de lire une ancienne version.
- `/api/v1/catalog` : projection compatible avec le contrat existant, lue depuis une seule version.
- `/api/v1/catalog/logos/{sha256}.webp` : image locale immuable, ETag et cache HTTP.
- `/api/v1/sources/oracles-elixir` et `/datasets` : exécutions et versions actives Oracle.

`retrievedAt` date la version conservée ; `checkedAt` date la dernière vérification réussie. Une ancienne version disponible ne signifie pas que la source est à jour. Les erreurs ne déclenchent aucun passage en mock côté API.

## Champions et bans sans API SofaScore — 21 septembre 2026

Le navigateur attend les contrôles rendus, puis le panneau sélectionné et ses portraits (jusqu’au timeout de 45 secondes). Les cinq bans de chaque équipe sont lus dans leur colonne DOM, sans déduire les camps bleu/rouge ni l’ordre chronologique du draft. Les libellés connus sont prioritaires ; à défaut, seuls les octets des portraits déjà chargés par le site sont comparés au catalogue Riot local. Aucun appel JSON ou téléchargement supplémentaire de portrait n’est lancé par cette étape.

Le référentiel `apps/worker/src/metiquo_worker/data/champion-portraits.json` se construit avec `npm run data:champions:reference`, sans réseau. Les empreintes de l’image source et du référentiel, la méthode et les octets d’origine sont conservés dans les preuves du relevé et le volume d’artefacts. Un artwork différent, illisible ou ambigu reste sans nom ; les bans visibles restent présents. Les seuils conservateurs ne garantissent pas la reconnaissance de tous les portraits.
