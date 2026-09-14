# Scraping public Stake

Le collecteur lit les pages rendues par Chromium piloté par Patchright, sans clé API ni requête directe
vers un service de données Stake. Le choix technique est consigné dans
[ADR-0001](adr/0001-stake-public-dom-scraping.md).

Le [rapport Patchright](stake-patchright-20260908.md) décrit le scan autonome réussi
de 12 matchs et l'essai réel sous Docker. Un [lecteur Chrome/Edge avec import local](stake-browser-reader.md) permet aussi
d'utiliser les pages accessibles dans le navigateur habituel. Dans ce mode, le
worker lit un fichier et ne contacte pas Stake. L'extension est prête et testée
sur des pages rejouées ; son installation dans le profil personnel reste à faire.

## Mise en service

Configurer l'environnement serveur :

```dotenv
APP_DATA_MODE=real
ODDS_PROVIDER=auto
STAKE_SCRAPE_INTERVAL_SECONDS=60
STAKE_SCRAPE_TIMEOUT_SECONDS=600
STAKE_SCRAPE_MAX_EVENTS=40
STAKE_SCRAPE_CONCURRENCY=2
STAKE_SCRAPE_NAVIGATION_INTERVAL_SECONDS=5
STAKE_SCRAPE_BACKOFF_SECONDS=600
STAKE_BROWSER_CHANNEL=chromium
STAKE_BROWSER_ENGINE=patchright
STAKE_BROWSER_HEADLESS=false
```

`DATABASE_URL` doit désigner PostgreSQL migré et `OBJECT_STORE_ROOT` un répertoire
persistant accessible en écriture. Le stockage actuel utilise `filesystem`.
Aucune variable API Stake n'est requise. Les anciens flags `STAKE_PROVIDER_ENABLED`
et `STAKE_*_CONFIRMED` concernent le squelette historique, pas ce scraper.

`ODDS_PROVIDER=auto` sélectionne `mock` en mode mock et `stake_public` en mode réel.
Le choix explicite `disabled` reste disponible. La configuration `.env` locale
utilise désormais `auto` et conserve son mode courant ; changer `APP_DATA_MODE`
sélectionne donc le provider correspondant sans activer des cotes réelles en mock.

Chromium complet charge les ressources du site normalement. Sur un poste avec
interface graphique, `STAKE_BROWSER_HEADLESS=false` affiche sa fenêtre ;
`STAKE_BROWSER_CHANNEL=chrome` ou `msedge` utilise le navigateur correspondant
s'il est installé. L'image Docker fournit `chromium` et un affichage Xvfb privé,
créé automatiquement sans écoute TCP. Le mode reste fenêtré du point de vue du
navigateur. Son profil dédié est conservé dans `OBJECT_STORE_ROOT/work/stake-browser` ;
aucun profil personnel n'est importé. `STAKE_BROWSER_ENGINE=playwright` sélectionne
le moteur standard pour les comparaisons.

Installation locale et collecte ponctuelle, avec les [binaires Playwright officiels](https://playwright.dev/python/docs/browsers) :

```console
uv sync --frozen
uv run --frozen python -m patchright install --no-shell chromium
uv run --frozen alembic upgrade head
uv run --frozen oe odds-scrape --json
```

`--url` accepte aussi une ou plusieurs pages de matchs, par exemple :

```console
uv run --frozen oe odds-scrape --url https://stake.bet/fr/sports/league-of-legends/international-1/lec-2026-summer-playoffs-t3/822193-giantx-natus-vincere --json
```

Le worker existant planifie `odds.stake_scrape`. Un verrou PostgreSQL empêche deux
collectes simultanées. La temporisation reste en base après un redémarrage ; une
commande appelée trop tôt retourne `cooldown` sans contacter Stake. Après un
refus ou un échec, le délai commence à 600 secondes puis double, jusqu'à 24 heures.
Le code de sortie de la CLI vaut zéro seulement pour une collecte opérationnelle.

L'image Python embarque Chromium et ses dépendances. Compose ajoute un volume
`odds_snapshots`, 512 Mio temporaires et 256 Mio de mémoire partagée au worker.
Sous Compose, conserver `OBJECT_STORE_ROOT=/data` pour utiliser les volumes montés.
La sauvegarde et la restauration incluent les archives de cotes et vérifient leurs hashes.

## Données et affichage

La page `/odds`, onglet « Scraping Stake », affiche l'état de la collecte et les
marchés par match et par carte. Son actualisation consulte les données stockées ;
le worker assure la collecte. Les routes de lecture sont :

- `GET /api/v1/odds/stake/status` : dernier résultat, dernier succès et prochaine tentative.
- `GET /api/v1/odds/stake/events` : dernières captures par match, paginées, avec filtres
  `startsFrom` et `startsTo` exigeant un fuseau explicite.
- `GET /api/v1/odds/quotes` : projection supplémentaire des vainqueurs, par sélection.

Les pages des compétitions servent à découvrir les URL des événements ; le
scraper ne se limite pas aux matchs mis en avant sur l'accueil LoL. Il visite les
onglets annoncés, ouvre les sections repliées et les contrôles « Tout » et
« Charger Plus ». Il attend les libellés de l'onglet demandé avant d'extraire ses
prix. Les boutons de sélection des cotes ne sont jamais cliqués.

Les URL découvertes sont mises en cache pendant cinq minutes dans
`OBJECT_STORE_ROOT/work/stake-discovery.json`. Ce cache ne contient aucun prix :
chaque match est relu dans le navigateur. Un cache invalide, futur ou expiré est
ignoré. Les navigations sont espacées de cinq secondes par défaut, y compris
lorsqu'il y a deux pages en cours de lecture. Une réponse Cloudflare identifiée
par `cf-mitigated: challenge` laisse au navigateur 45 secondes pour terminer sa
vérification ; seul un document final HTTP 200 avec le DOM attendu est accepté.

Les handicaps, totaux, scores exacts et objectifs de cartes restent sous leur
libellé source complet, notamment les seuils et noms d'équipe présents dans les
libellés accessibles. Les décimales françaises sont validées strictement. Une
sélection suspendue ou sans prix conserve son état ; aucun prix de substitution
n'est généré. Une capture conserve les marchés de chacun des onglets : certains
vainqueurs apparaissent à la fois dans « Principal » et dans leur onglet de carte.

Les dates complètes visibles sont interprétées dans le fuseau du navigateur,
puis enregistrées en UTC. Le Chromium autonome utilise `Europe/Paris` ; l'extension
déclare le fuseau du navigateur personnel. Une date absente, ambiguë ou déjà passée
est refusée. La normalisation du live n'est pas validée : le périmètre vérifié
couvre les matchs à venir, y compris ceux qui commencent plus tard le jour courant.
Le format BO reste inconnu lorsqu'il n'est pas affiché explicitement.

La capture est immuable, adressée par SHA-256 et publiée transactionnellement avec
la projection des vainqueurs. Un rejeu ne duplique pas les observations. Leur
fraîcheur dépend de l'heure de lecture, jamais de l'heure d'import. L'expiration
retournée par le serveur permet aussi à l'interface de périmer une cote entre deux
actualisations. L'horodatage de mise à jour propre à Stake et les règles de
règlement ne sont pas inférés ; les cotes restent informatives.

## Vérifications du 8 septembre 2026

Un [audit complémentaire](stake-scraping-audit-20260908.md) couvre douze autres
matchs, les variations de noms Keyd, les six onglets de 9z–Golden Lions, les
pannes de navigation et le démarrage de Chromium complet sous Docker. Il
documente également le nouveau refus HTTP 403 du collecteur autonome.

Lecture des pages publiques dans le navigateur intégré :

| Match                        | Début affiché, Paris | Vainqueur du match |
| ---------------------------- | -------------------- | ------------------ |
| GIANTX – Natus Vincere       | 11 septembre, 17:00  | 2,05 / 1,78        |
| Team Vitality – Movistar KOI | 12 septembre, 17:00  | 1,78 / 2,05        |

Les six onglets de GIANTX–Natus Vincere ont été parcourus : 55 blocs de marchés et
154 sélections après dépliage, avec les doublons de présentation entre onglets.
Le contrôle « Tout » révèle six scores exacts, alors que le curseur initial
affichait une combinaison suspendue. Les cotes du vainqueur de la carte 1 de
Vitality–KOI ont aussi été vérifiées : 1,80 / 1,98, différentes des cotes du match.

La fixture `tests/fixtures/odds/stake-dom-20260908.json` conserve les valeurs lues,
sans inventer un horodatage source. Les horloges utilisées au rejeu sont des
horloges de test, et ces fixtures ne sont jamais chargées par le collecteur réel.

Validations exécutées :

- Rejeu dans Chromium : changement de fuseau après hydratation, six onglets,
  scores exacts, dépliage des handicaps et aucun clic sur une cote.
- PostgreSQL et HTTP : capture intégrale, projection, pagination, filtres,
  déduplication, péremption, refus d'accès, temporisation et immutabilité.
- Construction de l'image et démarrage de Chromium avec réseau désactivé,
  système de fichiers en lecture seule et utilisateur non privilégié.
- Tests de composants et build de production incluant `/odds`.

**Constat initial : la commande Playwright autonome a reçu HTTP 403 depuis cet hôte.**
Le test réel `oe odds-scrape --url … --json` a retourné `state=blocked`, zéro cote
ajoutée et une prochaine tentative différée. Le navigateur intégré accessible et
les tests de rejeu ne prouvent pas que le processus autonome dispose d'un accès
opérationnel. Les nouveaux essais Patchright sont consignés séparément dans le
[rapport du nouveau moteur](stake-patchright-20260908.md). Aucune disponibilité
permanente « 100 % » n'est revendiquée.

Le [rapport JSON du test autonome](evidence/stake-scraping-20260908.json) conserve
le résultat du 8 septembre à 17:09 UTC et les réponses HTTP de l'application.
Les contrôles ont couvert 513 tests Python hors infrastructure, 15 tests
PostgreSQL, trois tests Chromium et 50 tests de composants. Le contrôle global
hors infrastructure comporte également un test ignoré faute de base dans cette
invocation ; l'isolation des nouvelles routes est testée sur PostgreSQL.

La consultation de la nouvelle interface dans un navigateur n'a pas été validée :
le démarrage de l'instance web de vérification avait été refusé par la revue
automatique d'approbation. Le build et les tests de composants sont distincts de
cette vérification manquante.

## Reproduire les tests

`TEST_DATABASE_URL` doit être une base jetable, car les fixtures recréent le schéma.
Pour le test de sauvegarde/restauration, fournir les outils PostgreSQL ou
`TEST_PG_CONTAINER` pointant vers le conteneur de test.

```console
uv run --frozen python -m pytest tests/providers/test_stake_scraping.py tests/providers/test_stake_browser_resilience.py tests/integration/test_stake_scraping.py -q
pnpm test:components
```
