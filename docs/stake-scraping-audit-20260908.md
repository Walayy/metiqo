# Audit complémentaire du scraping Stake — 8 septembre 2026

<!-- cspell:words Keyd Hanwha -->

Douze pages de matchs supplémentaires ont été lues dans le navigateur intégré,
dans neuf compétitions. Les valeurs ci-dessous sont celles du relevé, sans
prétendre qu'elles restent actuelles. La fixture
[`stake-additional-matches-20260908.json`](../tests/fixtures/odds/stake-additional-matches-20260908.json)
conserve les en-têtes et les marchés vainqueurs ; elle ne représente pas une
capture intégrale de chaque match.

<!-- cspell:disable -->

| Match et page source                                                                                                                                                                       | Compétition                           | Début affiché, Europe/Paris   | Vainqueur du match     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------- | ----------------------------- | ---------------------- |
| [9z Team – Golden Lions](https://stake.bet/fr/sports/league-of-legends/international-1/liga-regional-sur-2026-split-2-t10/820307-9z-team-golden-lions)                                     | Liga Regional Sur 2026 Split 2        | 22:00 08/09/2026              | 1,25 / 3,50            |
| [Keyd Academy – KaBuM! Ilha das Lendas](https://stake.bet/fr/sports/league-of-legends/international-1/circuito-desafiante-2026-split-2-t8/826033-keyd-stars-academy-kabum-ilha-das-lendas) | Circuito Desafiante 2026 Split 2      | 22:00 08/09/2026              | 1,85 / 1,85            |
| [mCon esports – Frites Esports Club](https://stake.bet/fr/sports/league-of-legends/international-1/road-of-legends-2026-summer-playoffs-t8/826635-mcon-esports-frites-esports-club)        | Road Of Legends 2026 Summer Playoffs  | Date absente, match en direct | Marché du match absent |
| [Hanwha Life Esports – T1 Esports](https://stake.bet/fr/sports/league-of-legends/international-1/lck-2026-season-playoffs-t3/823841-hanwha-life-esports-t1-esports)                        | LCK 2026 Season Playoffs              | 07:00 12/09/2026              | 1,60 / 2,35            |
| [Anyone's Legend – Invictus Gaming](https://stake.bet/fr/sports/league-of-legends/international-1/lpl-2026-grand-finals-t3/826446-anyone-s-legend-invictus-gaming)                         | LPL 2026 Grand Finals                 | 11:00 12/09/2026              | 2,00 / 1,82            |
| [Cloud9 – Shopify Rebellion](https://stake.bet/fr/sports/league-of-legends/international-1/lcs-2026-summer-playoffs-t4/824269-cloud9-shopify-rebellion)                                    | LCS 2026 Summer Playoffs              | 22:00 12/09/2026              | 1,22 / 3,80            |
| [Sentinels – FlyQuest](https://stake.bet/fr/sports/league-of-legends/international-1/lcs-2026-summer-playoffs-t4/824271-sentinels-flyquest)                                                | LCS 2026 Summer Playoffs              | 22:00 13/09/2026              | 1,58 / 2,20            |
| [G2 NORD – BIG](https://stake.bet/fr/sports/league-of-legends/international-1/prm-1st-division-2026-summer-playoffs-t6/819250-g2-nord-big)                                                 | PRM 1st Division 2026 Summer Playoffs | 14:00 12/09/2026              | 1,62 / 2,15            |
| [White Dragons – Dominion Goblins](https://stake.bet/fr/sports/league-of-legends/international-1/lplol-2026-summer-playoffs-t7/825818-white-dragons-dominion-goblins)                      | LPLOL 2026 Summer Playoffs            | 20:00 08/09/2026              | 1,12 / 5,30            |
| [LOS – FURIA Esports](https://stake.bet/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5/826336-los-furia-esports)                                               | CBLOL 2026 Split 2 Playoffs           | 18:00 12/09/2026              | 1,72 / 2,00            |
| [LOUD – paiN Gaming](https://stake.bet/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5/826339-loud-pain-gaming)                                                 | CBLOL 2026 Split 2 Playoffs           | 18:00 13/09/2026              | 1,22 / 3,80            |
| [RED Canids – Keyd Stars](https://stake.bet/fr/sports/league-of-legends/international-1/cblol-2026-split-2-playoffs-t5/825431-red-canids-keyd-stars)                                       | CBLOL 2026 Split 2 Playoffs           | 18:00 19/09/2026              | 2,80 / 1,38            |

<!-- cspell:enable -->

## Cas rencontrés et corrections

- Le match Keyd présente « Keyd Academy » dans l'en-tête et « Keyd Stars Academy »
  dans les sélections, y compris sur la carte 1. L'ancien rapprochement strict
  supprimait la projection des vainqueurs. La correction utilise le marché
  vainqueur de cette page et l'adversaire identique comme ancrage exact. Elle
  conserve l'ordre des participants et refuse deux noms sans correspondance.
  Aucun dictionnaire d'alias ni rapprochement approximatif n'est utilisé.
- Les six onglets de 9z–Golden Lions ont été parcourus : onze blocs de marchés et
  vingt-deux sélections. Chaque onglet de carte contient seulement son vainqueur.
  Les cartes 1, 2 et 3 affichent 1,42 / 2,70 ; la carte 4, 1,48 / 2,50 ;
  la carte 5, 1,50 / 2,40. Leur fixture complète est
  [`stake-9z-dom-20260908.json`](../tests/fixtures/odds/stake-9z-dom-20260908.json).
- Le contrôle « Tout » de Keyd expose six scores exacts : 0:3 à 5,80 ;
  1:3, 3:1, 2:3 et 3:2 à 4,40 ; 3:0 à 6,30. Le curseur initial affichait une
  combinaison suspendue. Les contrôles apparus après ouverture d'une section
  sont désormais traités ; terminer exactement à la limite d'actions ne produit
  plus un faux avertissement.
- Une observation récente sans prix ne reprend plus la cote ouverte d'un onglet
  antérieur, même si les horodatages sont identiques.
- Une page indisponible ou trop lente n'annule plus les autres matchs. Une
  compétition indisponible n'arrête plus la découverte des suivantes. Un refus
  d'accès suspend les nouvelles navigations, conserve les captures terminées et
  déclenche le délai d'attente en base. Le délai global conserve aussi les
  captures terminées.
- Le match mCon–Frites était en direct, avec les onglets 3 à 5 et sans date complète.
  Il est refusé avant de parcourir les marchés. Aucun début ni statut programmé
  n'est inventé. Des scores numériques apparaissaient aussi sur la page à venir
  Sentinels–FlyQuest : leur présence seule ne permet donc pas de déduire un statut live.

## Navigateur et accès réel

Le collecteur utilise maintenant Chromium complet, avec chargement normal des
images, polices et scripts. Le mode `channel="chromium"` correspond au navigateur
complet décrit par [Playwright](https://playwright.dev/python/docs/browsers).
Les options de configuration permettent aussi Chrome ou Edge installés et
un affichage avec fenêtre sur un poste disposant d'un environnement graphique.

Le démarrage du navigateur complet a été testé dans l'image Docker, en utilisateur
10001, réseau désactivé et système de fichiers en lecture seule. Ce test a révélé
un échec du gestionnaire de rapports d'erreurs : ses répertoires auxiliaires étaient
en lecture seule. La configuration et le cache utilisent désormais le répertoire
temporaire inscriptible, selon les [emplacements documentés par Chromium](https://chromium.googlesource.com/chromium/src/+/main/docs/user_data_dir.md).
Le test de démarrage et de rendu DOM passe après correction.

**L'accès autonome à Stake reste bloqué sur cet hôte.** Le 8 septembre à
17:28 UTC, Chromium complet, sans blocage de ressources, a reçu HTTP 403 sur
Hanwha Life–T1. Aucune cote n'a été produite par cette tentative.
Le [résultat JSON](evidence/stake-full-chromium-20260908.json) conserve ce constat.
L'accès du navigateur intégré et les replays contrôlés ne prouvent pas
la disponibilité d'un flux autonome.

## Validation reproductible

Les tests navigateur exécutent le vrai Chromium avec des pages de test servies
par interception réseau. Ils couvrent les DOM relevés et des pannes synthétiques
annoncées comme telles : 401, 403, 429, 451, 500, 503, erreur réseau, délai de page,
délai global, annulation, déduplication, ressources visuelles et fermeture du navigateur.
L'extrait Keyd couvre seulement le vainqueur du match et la carte 1.

Les tests PostgreSQL utilisent une base jetable et vérifient aussi les réponses
HTTP, la sauvegarde/restauration, les migrations et la conservation des captures
lors d'un refus partiel. Ils ne placent aucun pari et n'utilisent aucune API Stake.

Résultats de cette passe :

- 529 tests Python hors infrastructure réussis ; un test ignoré faute de base
  dans cette invocation et 167 tests d'infrastructure exclus de cette commande.
- 16 tests Chromium et 16 tests PostgreSQL ciblés réussis. La commande groupée
  rapporte 69 succès, dont 37 tests unitaires déjà comptés dans les 529.
- 50 tests de composants réussis : 30 dans la bibliothèque UI et 20 dans le web.
- Vérifications Ruff, mypy sur 453 fichiers, orthographe et configuration Compose réussies.
- Image Docker reconstruite avec Chromium complet ; démarrage et rendu DOM vérifiés
  en lecture seule, sans réseau et sans privilèges administrateur.

Les autres tests d'infrastructure du dépôt n'ont pas été relancés dans cette passe.
Ces résultats ne certifient ni le live sans date source ni l'accès autonome refusé par Stake.
