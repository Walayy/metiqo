# Lire Stake depuis Chrome ou Edge

Ce lecteur reste une option. Le [moteur Patchright intégré](stake-patchright-20260908.md)
permet désormais de tester la collecte autonome sans installer cette extension.

Le nouveau mode lit le DOM public dans un navigateur où Stake est déjà accessible,
puis transmet un fichier local à Metiquo. Le processus Python ne contacte pas Stake
dans ce mode. Cela évite de dépendre de l'accès du Chromium autonome, qui a reçu
HTTP 403 sur cet hôte. L'accès du navigateur personnel reste à vérifier : aucun
code ne peut garantir que Stake l'autorisera indéfiniment.

## Installation locale

1. Ouvrir normalement un match LoL Stake dans Chrome ou Edge et vérifier que ses
   marchés s'affichent.
2. Ouvrir `chrome://extensions` ou `edge://extensions`, activer le mode développeur,
   choisir **Charger l'extension non empaquetée**, puis sélectionner ce dossier :

   ```text
   C:\Users\leotr\Documents\Projets\metiqo\browser\stake-reader
   ```

3. Cliquer sur l'extension **Metiquo — lecteur Stake**. Son panneau s'ouvre dans
   un onglet. Choisir **Lire les matchs déjà ouverts** pour les onglets accessibles,
   ou **Scanner les matchs LoL** pour découvrir les compétitions puis leurs matchs.
4. Le panneau affiche le chemin du fichier téléchargé, normalement
   `Téléchargements/Metiquo/stake-browser-latest.json`. Copier ce chemin exact.
   L'actualisation est optionnelle ; elle attend 60 secondes après chaque collecte.
   Garder le navigateur et le panneau ouverts. Le bouton **Arrêter** annule aussi
   une actualisation en attente.

L'extension utilise les [scripts de contenu Chrome](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
pour lire le DOM rendu et les [téléchargements Chrome](https://developer.chrome.com/docs/extensions/reference/api/downloads)
pour écrire l'export. Ses permissions sont limitées à ces opérations et aux pages
françaises LoL de `stake.bet`. Elle ne lit ni cookies, ni jetons, ni historique
général de navigation ou de téléchargement. Les erreurs d'accès arrêtent le cycle ;
les captures déjà terminées restent dans l'export.

## Validation sans serveur ni base

Depuis la racine du projet, avec le chemin réellement affiché par le panneau :

```powershell
uv sync --frozen
uv run --frozen python -m metiquo.providers.stake_browser_file "C:/Users/leotr/Downloads/Metiquo/stake-browser-latest.json"
```

La commande affiche le nombre de matchs, marchés et sélections. Son code de sortie
vaut zéro uniquement pour un export complet, non vide et encore frais. Une capture
de plus de 90 secondes est signalée `BROWSER_EXPORT_STALE` par défaut. Les temps
de lecture originaux sont conservés, même si le fichier est importé plusieurs fois.

## Brancher le collecteur existant

Configurer le worker local avec une base PostgreSQL migrée et un stockage
persistant, comme dans le [guide du collecteur](stake-public-scraping.md), puis
ajouter le chemin du fichier à son environnement :

```dotenv
APP_DATA_MODE=real
ODDS_PROVIDER=stake_public
STAKE_BROWSER_CAPTURE_FILE=C:/Users/leotr/Downloads/Metiquo/stake-browser-latest.json
```

Cette variable sélectionne le transport fichier à la place du lancement de
Playwright. Il n'y a aucun repli automatique vers une requête Stake. Le fichier
`.env` de travail n'a pas été basculé : il reste dans sa configuration existante.
La variable doit être visible du processus worker, qui doit être redémarré après
un changement de configuration.

```console
uv run --frozen alembic upgrade head
uv run --frozen oe odds-scrape --json
uv run --frozen python -m metiquo.worker
```

La première commande applique les migrations sur la base configurée. La deuxième
importe une fois. La troisième lance le worker et son ordonnanceur existant.
Le verrou, la déduplication et les archives immuables continuent de s'appliquer.
Le mode fichier utilise l'intervalle local de 60 secondes par défaut, y compris
après un export manquant ou invalide. Le délai réseau d'un ancien HTTP 403 est
ramené à cet intervalle pour l'import local, qui ne contacte pas Stake. Pendant
cette attente, la commande indique `cooldown` et la nouvelle échéance `nextAttemptAt`.

Ce parcours est celui d'un worker Windows local. Un worker dans Docker nécessite
un montage explicite du fichier téléchargé, en lecture seule, et un chemin Linux
dans `STAKE_BROWSER_CAPTURE_FILE` ; le chemin Windows n'est pas accessible depuis
le conteneur par défaut.

## Périmètre et diagnostic

- Le lecteur visite les onglets Principal et cartes 1 à 5, déplie les marchés et
  active « Tout » et « Charger Plus ». Les sélections de paris ne sont pas cliquées.
- Un scan est séquentiel, limité à 30 compétitions et 40 matchs. Une limite atteinte
  ou une page incomplète est signalée ; la couverture n'est pas déclarée totale.
- Un scan volumineux peut durer plus longtemps que la validité des premières
  observations. Pour suivre quelques matchs avec davantage de fraîcheur, utiliser
  leurs onglets ouverts. Le lecteur ne rajeunit jamais artificiellement les prix.
- Les dates sont interprétées dans le fuseau renvoyé par le navigateur. Le live
  sans date complète reste non pris en charge. Les prix absents restent absents.
- `ACCESS_CHALLENGE` : le navigateur affiche un refus d'accès. La collecte et
  l'actualisation s'arrêtent. Vérifier l'accès normal au site avant de relancer.
- `BROWSER_EXPORT_MISSING` : contrôler le chemin et le téléchargement ;
  `BROWSER_EXPORT_INVALID` : refaire un export avec cette version du lecteur.
- `BROWSER_EXPORT_STALE` : refaire une lecture. Un import tardif peut conserver
  l'historique, mais les routes de cotes le signalent comme périmé.

## Preuves du 8 septembre 2026

La [capture publique de 9z Team–Golden Lions](evidence/stake-browser-dom-20260908.json)
a été lue entre 18:18:05 et 18:18:42 UTC dans le navigateur intégré : match annoncé
le même jour à 22:00, heure de Paris ; 11 blocs, 22 sélections, six onglets.
Les prix du vainqueur étaient 1,22 et 3,80. Les valeurs et horodatages ont été
transcrits depuis le DOM, sans modification. Pour cette lecture assistée seulement,
le fuseau Paris provient de l'environnement utilisateur ; l'évaluateur du
navigateur intégré ne permettait pas de lire `Intl`.

La commande locale a d'abord validé cet export encore frais. L'[import ultérieur
sur PostgreSQL et la lecture HTTP en processus](evidence/stake-browser-import-20260908.json)
ont conservé 11 blocs et 12 observations de vainqueur, avec réponse 200. Les prix
étaient alors correctement signalés périmés. Aucun serveur réseau n'a été lancé
pour cette vérification. Cela prouve le transport des données réellement lues,
mais pas l'installation ni l'accès de l'extension dans le profil Chrome personnel.

Les tests du lecteur installent réellement l'extension dans un profil Chromium
isolé, avec pages enregistrées rejouées : navigation par compétitions, onglets
déjà ouverts, téléchargement, import Python, arrêt de l'actualisation et refus
d'accès après une capture réussie. Les tests PostgreSQL vérifient également le
choix du transport fichier sans création de navigateur, la publication HTTP,
la déduplication et la péremption.

Contrôles finaux exécutés sur cette version : 547 tests Python hors infrastructure
réussis, un test ignoré ; 19 tests Chromium réussis, dont trois avec l'extension
installée ; six tests PostgreSQL ciblés réussis. Ruff, mypy sur 457 fichiers,
Prettier et le correcteur orthographique ciblé passent. La suite hors infrastructure
a été lancée dans un dossier isolé du `.env` local, avec une copie inchangée de
`config/security-policy.json` pour le test de politique de sécurité.

```console
uv run --frozen python -m pytest tests/providers/test_stake_browser_file.py -q
uv run --frozen python -m pytest tests/integration/test_stake_browser_file.py -q
```

Le deuxième test exige `TEST_DATABASE_URL` vers une base jetable. Après modification
de l'extracteur Python, régénérer son équivalent navigateur avec
`uv run --frozen python infra/scripts/build_stake_reader.py` ; un test impose leur
identité exacte.

## Refus de démarrage web distinct

La revue automatique a refusé `next start` sur le port 3002, y compris avec une
écoute limitée à `127.0.0.1`. Le seul motif retourné était `blocked by policy`.
L'extension et son diagnostic local n'exigent pas ce serveur. Le refus de la revue
n'a pas été levé et la nouvelle interface web n'a pas été vérifiée dans un
navigateur sur ce serveur.

La [documentation officielle de la revue automatique](https://learn.chatgpt.com/docs/sandboxing/auto-review)
décrit une réautorisation ciblée de l'action refusée via le parcours prévu par
Codex ; dans le terminal interactif compatible, il s'agit de `/approve` et du
sélecteur des refus. Sa disponibilité dans cette application de bureau n'est pas
confirmée. Cette autorisation doit venir de l'utilisateur ; changer de lanceur
pour exécuter la même action refusée ne résout pas ce contrôle.
