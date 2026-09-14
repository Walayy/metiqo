# Scraping autonome avec Patchright — 8 septembre 2026

## Recherche et choix

Les projets publics examinés sont [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python),
[Nodriver](https://github.com/ultrafunkamsterdam/nodriver) et
[Rebrowser](https://github.com/rebrowser/rebrowser-patches). Patchright conserve
l'interface Playwright utilisée par Metiquo ; sa version PyPI 1.62.3, publiée le
2 septembre 2026, est verrouillée avec ses hashes dans `uv.lock`. Le projet
recommande un navigateur fenêtré et un profil dédié. Les affirmations de réussite
des auteurs ne constituent pas une garantie d'accès à Stake. Rebrowser indique
explicitement que ses correctifs ne suffisent pas à supprimer tous les blocages.

## Intégration

`APP_DATA_MODE=real` et `ODDS_PROVIDER=auto` sélectionnent automatiquement le
scraper Stake et sa planification dans le worker. En mode mock, le même réglage
sélectionne le provider mock. La valeur explicite `disabled` reste respectée.

Le navigateur utilise Patchright, Chromium complet, un profil propre au collecteur
et le mode fenêtré. Sous Linux sans affichage, le code lance puis ferme Xvfb,
avec un numéro d'affichage libre et sans écoute réseau. L'image Docker embarque
les dépendances. Aucune extension ni export manuel n'est nécessaire.

Les navigations sont espacées de cinq secondes ; les URL des matchs sont mises en
cache cinq minutes pour éviter de parcourir toutes les compétitions à chaque
cycle. Les prix restent lus à nouveau, avec l'heure réelle de chaque observation.
Les archives, la déduplication et les états de fraîcheur sont conservés.

La [documentation Cloudflare](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/)
identifie les réponses de vérification via `cf-mitigated: challenge`. Le collecteur
laisse cette vérification JavaScript s'exécuter pendant un délai borné ; il exige
ensuite un document HTTP 200 et les éléments attendus. Un refus final ou une
vérification non résolue reste déclaré bloqué. Les données manquantes ne sont pas
remplacées par des valeurs de test.

La [configuration complète](stake-public-scraping.md) contient les commandes
d'installation, de migration, de collecte et les réglages du worker.

## Observations réelles

Les premiers essais comparent un profil dédié neuf avec Patchright 1.62.3 :

| Essai                                | Résultat observé                                                    |
| ------------------------------------ | ------------------------------------------------------------------- |
| Chrome sans fenêtre                  | HTTP 403, vérification Cloudflare encore présente après 45 secondes |
| Chrome fenêtré                       | HTTP 200, match GIANTX–Natus Vincere visible                        |
| Chromium fenêtré                     | HTTP 200, même match visible                                        |
| Collecteur intégré, Chromium fenêtré | Six onglets, 55 blocs, 154 sélections, aucune erreur                |

La première collecte intégrée a terminé à 20:02:06 UTC. Le scan initial des
compétitions a ensuite reçu HTTP 429 avec l'ancien intervalle d'une seconde.
Les navigations plus espacées et le cache de découverte ont été ajoutés après ce
constat, puis vérifiés sur les essais ci-dessous.

À 20:17:30 UTC, la [collecte réelle sur trois compétitions](evidence/stake-patchright-live-20260908.json)
a retourné `state=operational` : GIANTX–Natus Vincere, Hanwha Life Esports–T1
Esports et Anyone's Legend–Invictus Gaming, tous à venir. Les trois navigations
ont reçu HTTP 200 ; 165 blocs de marchés et 462 sélections ont été lus, puis 36
observations de vainqueur publiées en base. Les trois captures étaient fraîches
lors de la lecture HTTP. Cette preuve utilise les données effectivement lues
sur Stake, sans fixture ni import manuel.

Les [diagnostics initiaux](evidence/stake-patchright-probes-20260908.json) conservent
également les réponses observées avec et sans fenêtre.

À 20:21:01 UTC, le [scan autonome des compétitions](evidence/stake-patchright-discovery-20260908.json)
a lui aussi retourné `state=operational`. Il a découvert et collecté 12 matchs,
avec 620 blocs, 1 738 sélections et 144 observations de vainqueur publiées. Les
21 navigations documentées — accueil LoL, huit compétitions, douze matchs — ont
toutes reçu HTTP 200, sans challenge ni erreur. Aucun jeu d'URL fourni à la main
n'a été utilisé pour ce scan. La réponse HTTP archivée montre la première page
de dix matchs ; le bilan de collecte porte bien sur les douze événements.

À 20:24:58 UTC, un [second cycle autonome](evidence/stake-patchright-cached-20260908.json)
a relu les douze matchs en utilisant le cache de découverte : douze navigations,
toutes HTTP 200, aucun retour sur les pages de compétitions. Il a publié 144
nouvelles observations horodatées, avec le même total de marchés et de sélections.
La lecture HTTP paginée à vingt résultats montre les douze captures, toutes
fraîches à cet instant. La session du navigateur a été rouverte automatiquement
à partir du profil dédié entre les cycles.

## Vérifications

Les tests exécutent réellement Patchright sur des pages de référence contrôlées.
Ils vérifient la totalité des marchés, une vérification qui se termine, une qui
reste présente, un refus définitif, le cache d'URL et la relecture d'un prix modifié.
Un test PostgreSQL passe par le handler réel du worker configuré en mode `auto`,
puis vérifie les données et leur fraîcheur via les routes HTTP en processus.

Résultats : 553 tests Python hors infrastructure réussis, un ignoré ; 21 tests
navigateur ciblés réussis ; 13 tests PostgreSQL ciblés réussis, dont le parcours
complet du handler avec le navigateur. Ruff, mypy sur 461 fichiers, Prettier,
le correcteur orthographique ciblé et la validation Compose passent. La suite
hors infrastructure est isolée du `.env` local, avec la politique de sécurité
du projet copiée sans modification pour son test en sous-processus.

L'image Docker a été construite et son navigateur fenêtré lancé avec Xvfb :
utilisateur 10001, système de fichiers en lecture seule, mémoire temporaire bornée
et réseau désactivé pour ce test de démarrage. Un [essai réseau Docker distinct](evidence/stake-patchright-docker-20260908.json)
a ensuite collecté GIANTX–Natus Vincere entre 20:22:18 et 20:22:32 UTC : 55 blocs,
154 sélections, aucune erreur, sans affichage Windows ni intervention manuelle.

Les essais finaux ci-dessus n'ont rencontré aucun blocage. Ils démontrent le
fonctionnement sur ces pages et dans ces environnements à cet instant ; ils ne
garantissent pas qu'un changement de Stake ou de Cloudflare ne nécessitera jamais
une adaptation. Le live dépourvu de date complète reste hors du périmètre validé.

Le précédent refus de démarrage du serveur Next par la revue automatique est
distinct. Aucun démarrage de ce serveur n'a été utilisé pour valider le scraper.
