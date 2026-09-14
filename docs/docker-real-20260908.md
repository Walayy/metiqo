# Docker local en mode réel — 8 septembre 2026

L'installation utilise le projet Compose `metiquo` de ce dépôt. L'interface est
accessible à <http://localhost:3000>, les cotes à <http://localhost:3000/odds>.
L'API écoute sur `127.0.0.1:8000`. PostgreSQL reste sur le réseau Docker interne.

## Configuration effective

Le fichier privé `.env` contient notamment :

```dotenv
APP_DATA_MODE=real
ODDS_PROVIDER=auto
APP_PUBLIC_ORIGIN=http://localhost:3000
APP_PUBLISH_HOST=127.0.0.1
DATABASE_URL=postgresql+psycopg://metiquo@postgres:5432/metiquo
OBJECT_STORE_BACKEND=filesystem
OBJECT_STORE_ROOT=/data
WORKER_SCHEDULER_ENABLED=true
STAKE_BROWSER_ENGINE=patchright
STAKE_BROWSER_CHANNEL=chromium
STAKE_BROWSER_HEADLESS=false
STAKE_SCRAPE_INTERVAL_SECONDS=60
STAKE_SCRAPE_TIMEOUT_SECONDS=600
STAKE_SCRAPE_MAX_EVENTS=40
STAKE_SCRAPE_CONCURRENCY=2
STAKE_SCRAPE_NAVIGATION_INTERVAL_SECONDS=5
STAKE_SCRAPE_BACKOFF_SECONDS=600
```

`auto` se résout en `stake_public` dans le worker et l'API. Aucun fichier de
captures ni extension manuelle n'est nécessaire. Le navigateur et Xvfb sont dans
l'image Python. Le profil dédié persiste dans le volume `metiquo_ingestion_work`.
Les anciennes variables `STAKE_PROVIDER_ENABLED` et de validation de l'ancien
connecteur restent désactivées : elles ne sélectionnent pas le scraping public.

Les images sont construites depuis le contenu actuel du dépôt avec les versions
verrouillées. Les volumes de données sont conservés lors des reconstructions.
Les quatre services persistants redémarrent avec la politique `unless-stopped`.
Le conteneur `volume-init` doit terminer avec le code 0.

## Vérifications et correction du navigateur

La première exécution complète a rencontré des délais d'attente. Le diagnostic
dans le conteneur a observé HTTP 200 mais des modules JavaScript refusés par
Chromium avec `ERR_INSUFFICIENT_RESOURCES`. Le DOM initial n'était pas hydraté ;
ses liens et dates ne satisfaisaient pas le contrat de lecture.

Le scraper borne maintenant à 32 les téléchargements simultanés des ressources
statiques `https://stake.bet/_app/**`. Chaque place est conservée jusqu'à la fin
ou l'échec du téléchargement. Une navigation ou fermeture invalide également les
requêtes de l'ancien document, y compris celles qui attendaient leur place.
Le routage désactive le cache HTTP du navigateur ; le profil et le cache des URL
de découverte restent persistants. Les prix sont relus dans les pages.

La navigation JavaScript dans le même document conserve les téléchargements.
Seuls un remplacement du document, le détachement d'une frame ou sa fermeture
invalident les requêtes devenues inutiles. Les tests distinguent ces situations.

Nongshim–DN SOOPers a révélé deux cas supplémentaires : un onglet avec beaucoup
de lignes de marchés et des libellés français se terminant par « sur la carte 1 ».
Le contrôle des scores cherche uniquement les en-têtes qui proposent le bouton
« Tout ». Les libellés de carte sont reconnus par leur préfixe ou suffixe exact,
avec un test négatif pour éviter de confondre les cartes 1 et 10.

Les tests navigateur couvrent une rafale de modules, un téléchargement en échec,
la fermeture d'une page et la navigation avec des téléchargements encore en file.
Le test de navigation reproduisait un blocage avant la correction. Le parcours
worker → navigateur → PostgreSQL → API a aussi été exécuté sur une base jetable,
distincte de la base personnelle.

Huit pages de l'interface ont été parcourues dans Chromium en mode REAL, sans
erreur JavaScript ni réponse serveur 5xx. Les contrôles de la page Paramètres,
y compris axe, passent aux largeurs 1440 et 390 pixels. Le texte inconditionnel
« Provider Stake désactivé » a été remplacé par un lien vers l'état de la collecte.

Les captures anciennes restent signalées comme telles : le seuil de fraîcheur
est toujours de 90 secondes. Une collecte intégrale prend plus d'une minute et
n'est pas un flux de cotations instantané.

À **21:16:24 UTC**, le cycle autonome du worker a terminé avec l'état
`operational` : **12 matchs, 796 blocs de marchés et 2 570 sélections**. Les douze
navigations des matchs ont reçu HTTP 200. Les douze captures étaient fraîches
lors du contrôle HTTP. Le test de l'interface a parcouru les trois pages et les
72 onglets, et comparé les 2 570 prix ou états affichés aux réponses de l'API.
La [preuve du déploiement](evidence/docker-real-20260908.json) conserve les images
en cours d'exécution, les empreintes du code et les résultats horodatés.

Validation finale : **71 tests Python Stake**, **1 intégration PostgreSQL du
handler** et **2 tests E2E Paramètres avec axe** réussis, plus les huit parcours
de pages et le contrôle détaillé des cotes dans le navigateur. Les migrations,
la readiness et la correspondance des images construites avec les conteneurs
en cours d'exécution ont été vérifiées.

## Base et sauvegardes

L'ancienne base ne contenait aucune donnée métier, seulement la révision Alembic
`20260904_0002`. Une sauvegarde préalable est conservée localement dans
`test-results/docker-real-startup/before-real.dump`.

Une incompatibilité de version de collation entre l'ancien environnement et
l'image PostgreSQL actuelle a été constatée. L'ancienne base a été conservée sous
le nom `metiquo_before_real_20260908`. La nouvelle base `metiquo` utilise la
collation intégrée `C.UTF-8` et les 46 migrations jusqu'à `20260908_0046`.
La sauvegarde automatique du worker a été exécutée avec succès.

## État des fonctions qui nécessitent des données historiques

Cette base ne contient pas encore de source annuelle Oracle's Elixir active,
de dataset d'entraînement ni de modèle champion. La découverte distante a
retourné un catalogue vide ; l'état `SOURCE_CATALOG_MISSING` reste visible dans
l'administration. Les opportunités et événements canoniques restent donc vides.
Les matchs observés sur Stake se consultent dans la page Cotes.

Le dépôt contient des modifications non commitées. `APP_CODE_COMMIT` reste absent,
conformément au mécanisme de provenance existant : renseigner simplement le HEAD
ne décrirait pas le code construit. L'entraînement nécessite un commit vérifié
et un dataset réel. Le fonctionnement de ces étapes n'est pas déclaré validé.

## Commandes de gestion

Depuis la racine du dépôt :

```powershell
docker compose ps --all
docker compose logs --tail 100 worker
docker compose up -d --wait
```

Pour une mise à jour, sauvegarder les données avant toute nouvelle migration,
puis reconstruire et démarrer les services :

```powershell
docker compose build
docker compose up -d --wait postgres volume-init
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d --wait api worker web
```

`make up` et `make mock-demo` sont destinés au mock ; ne pas les utiliser pour
cette installation réelle. Ne pas supprimer les volumes pour faire une mise à jour.
