# Metiquo

Une application d’analyse des **values esport**, dédiée à League of Legends. Les données esport du frontend restent en mode mock ; l’inscription et la connexion par code email utilisent toujours la vraie API. Le worker synchronise le référentiel LoL, ses logos et les CSV Oracle’s Elixir dans PostgreSQL et un volume d’artefacts versionnés. **Stake est l’unique bookmaker prévu** ; son collecteur n’est pas implémenté et aucun accès à Stake.bet n’est effectué. Les cotes et probabilités affichées dans le frontend restent fictives.

## Application complète avec Docker

Prérequis : Docker Engine/Desktop avec Compose v2, Node.js pour générer la configuration locale. Depuis la racine :

```sh
npm run docker:init     # Génère les secrets ; complète auth/pgAdmin sans remplacer les réglages existants
npm run docker:up       # Démarre web, API, PostgreSQL, migrations, worker, Mailpit et pgAdmin
npm run docker:logs
```

Ouvrir [l’application](http://127.0.0.1:8080) et [la documentation API](http://127.0.0.1:8080/api/docs). Le frontend reste en `mock`. Le worker synchronise le catalogue LoL chaque jour, lance un import complet des années Oracle découvertes, puis actualise le dernier fichier toutes les six heures et l’historique chaque semaine. Le premier import prend plusieurs minutes ; les états sont accessibles sur `/api/v1/sources/lol-esports` et `/api/v1/sources/oracles-elixir`.

`npm run docker:down` arrête l’application **en conservant les volumes**. Ne pas ajouter `-v` pour un arrêt normal. Les secrets sont exclus de Git et des images. PostgreSQL n’expose aucun port dans la configuration standard.

Le [guide backend et exploitation](docs/backend.md) détaille la collecte manuelle, l’import du catalogue, le développement, les sauvegardes et les limites avant un déploiement public.

### Administration PostgreSQL avec pgAdmin

Ouvrir [pgAdmin](http://127.0.0.1:5050). Le compte initial est `admin@metiquo.fr` ; son mot de passe est `PGADMIN_DEFAULT_PASSWORD` dans `.env.docker`. Ce compte est indépendant de celui de l’application Metiquo.

Dans **Metiquo → Metiquo — PostgreSQL**, saisir `POSTGRES_PASSWORD` du même fichier : la connexion est déjà préconfigurée vers `db:5432`, base `metiquo`, utilisateur administrateur `metiquo`. Les mots de passe restent dans la configuration locale ignorée par Git. Le volume `pgadmin_data` conserve les comptes, connexions et préférences après redémarrage. Voir [les réglages et l’accès à la base](docs/backend.md#pgadmin-et-accès-à-postgresql).

## Inscription et connexion sans mot de passe

1. Cliquer sur **Se connecter**, puis saisir une adresse email dans la modale.
2. Ouvrir [Mailpit](http://127.0.0.1:8025) et copier le code à six chiffres du dernier email.
3. Saisir le code dans la fenêtre de Metiquo qui l’a demandé. Le compte est créé à la première validation.
4. **Mon profil** affiche l’email vérifié, le rôle et la date de création ; **Se déconnecter** révoque la session côté serveur.

Le compte **admin@metiquo.fr** est provisionné administrateur par Alembic. Il se connecte par le même code email, sans accès automatique ni mot de passe. Tous les autres comptes sont créés avec le rôle `user`. Aucun écran d’administration factice n’est ajouté.

Mailpit capture les emails localement : ils ne sont pas livrés dans de vraies boîtes mail. Son interface écoute sur `127.0.0.1:8025`, son SMTP reste dans le réseau Docker standard. Les messages, conservés en mémoire, disparaissent à la recréation du conteneur et sont limités à 500 / 24 heures. Pour un vrai fournisseur, configurer le SMTP avec TLS et ses identifiants ; voir [le guide d’authentification](docs/authentication.md).

Codes à usage unique valables 10 minutes, cinq essais maximum, renvoi après 60 secondes et limites persistantes par email/IP. Sessions opaques révocables en cookie HttpOnly, expirant après 7 jours sans activité ou 30 jours au maximum. Aucun token n’est stocké dans localStorage. Les favoris restent locaux à l’appareil.

La validation s’affiche directement sous le champ email ou code, dans un espace réservé : aide, erreur et confirmation se remplacent sans déplacer la modale ni les boutons. Les champs vides ou incomplets sont vérifiés avant tout appel API, sans bulle native du navigateur ; les transitions respectent la préférence de réduction des animations.

## Démarrage

Node.js **22.12+** (ou 24+) et npm. Depuis la racine du dépôt :

```sh
npm install
npm run dev
```

Ouvrir <http://127.0.0.1:5173>. Le port est fixe : Vite signale s’il est déjà occupé. Le serveur écoute uniquement en local.

L’authentification nécessite la stack Docker démarrée : Vite transmet `/api` à `127.0.0.1:8080`. Les fixtures esport fonctionnent seules, mais une API absente produit une erreur explicite dans la modale. Pour un backend Python local ou un port personnalisé, voir [authentication.md](docs/authentication.md).

```sh
npm run check        # Frontend + backend ; installer uv puis exécuter uv sync auparavant
npm run build
npm run preview      # Production locale sur http://127.0.0.1:4173
npm run format
npm run format:check
```

## Stack retenue

| Outil                                | Rôle et choix                                                                                                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| React 19.3 + TypeScript 6.0          | Composants typés, écosystème mature. TypeScript 6 est retenu pour rester dans la plage officiellement supportée par typescript-eslint, sans forcer les peer dependencies. |
| Vite 8.3                             | SPA rapide à développer et à compiler, sans serveur de rendu superflu.                                                                                                    |
| Tailwind CSS 4 + tokens CSS          | Utilitaires et design system sur mesure. Toutes les surfaces et couleurs possèdent une variante claire et sombre.                                                         |
| TanStack Query 5                     | Cache HTTP, annulation, chargements, erreurs et nouvelles tentatives.                                                                                                     |
| MSW 2 + Zod 4                        | Interception HTTP en mode mock et validation des contrats. L’API utilise les mêmes contrats ; la bascule de données ne demande pas de réécrire les composants.            |
| Radix UI                             | Dialogues et sélecteurs accessibles : focus, clavier, Escape.                                                                                                             |
| Motion 13                            | Transitions discrètes et respect du réglage de réduction des animations.                                                                                                  |
| Lucide                               | Icônes SVG cohérentes, sans emoji dépendant de l’OS.                                                                                                                      |
| Inter Variable + Manrope Variable    | Typographie locale ; aucune requête Google Fonts.                                                                                                                         |
| Vitest + ESLint + Prettier           | Vérification des calculs, intégrité du scénario, règles de code et formatage.                                                                                             |
| Pillow                               | Validation et conversion des logos officiels en WebP dans le worker Python.                                                                                               |
| Python 3.13 + uv                     | Workspace backend typé, dépendances verrouillées séparément du frontend.                                                                                                  |
| FastAPI + Pydantic                   | API de données, authentification par email et validation des contrats.                                                                                                    |
| Mailpit + SMTP Python                | Emails locaux ; transport SMTP remplaçable sans modifier le frontend.                                                                                                     |
| PostgreSQL 18 + SQLAlchemy + Alembic | Persistance, transactions, import en flux et migrations versionnées.                                                                                                      |
| Patchright + HTTPX                   | Export Drive groupé dans le worker, puis téléchargement HTTP en flux.                                                                                                     |
| Docker Compose + Nginx               | Services séparés, volumes persistants, proxy sur la même origine et sondes de santé.                                                                                      |

Les versions exactes installées sont dans `package-lock.json`. Le bundle des mocks est chargé séparément. Les panneaux font partie du chargement initial : leur ouverture ne dépend pas du téléchargement d’un module. Aucun routeur ou store global n’est nécessaire pour cet écran unique.

## Structure

```text
apps/
  api/src/metiquo_api/       # API et authentification réelle, sans navigateur
  worker/src/metiquo_worker/ # Catalogue LoL, logos, Oracle et extension future Stake
  web/
    public/logos/          # 297 logos officiels optimisés en WebP
    src/
      app/                 # Composition de l’écran, providers, frontière d’erreur
      components/
        layout/            # Navigation responsive
        ui/                # Boutons, dialogues, sélecteurs, logos, graphes, skeletons
      domain/              # Schémas Zod et calculs métier
      features/
        auth/              # Modale email/code/profil, contrats et client HTTP réel
        catalog/           # Ligues et équipes
        values/            # Liste, filtres, détail, sélection à la une
      hooks/               # Thème et favoris locaux
      lib/                 # HTTP, configuration, formatage, stockage
      mocks/               # Handlers MSW, scénario déterministe, catalogue sourcé
      styles/              # Tokens et styles responsive
docs/                      # Sources, contrat HTTP et vérifications
packages/core/             # Domaine, contrats et modèles PostgreSQL
migrations/                # Évolutions du schéma avec Alembic
infra/docker/              # Images API, worker et web ; Nginx et initialisation SQL
scripts/                   # Initialisation de l’environnement Docker
```

Le backend est séparé en `apps/api` (FastAPI), `apps/worker` (collecteurs, Patchright/Chromium) et `packages/core` (contrats, domaine, SQLAlchemy). Le workspace Python 3.13 est géré par uv avec `uv.lock`. PostgreSQL 18 et Alembic gèrent la persistance et les migrations. Les fichiers Docker et Nginx sont dans `infra/docker`.

## Modes de données

Copier au besoin `apps/web/.env.example` vers `apps/web/.env.local`.

```dotenv
VITE_DATA_MODE=mock
VITE_API_BASE_URL=/api/v1
```

`mock` est le défaut explicite du code. Les fixtures sont servies par MSW via `/api/v1/catalog` et `/api/v1/opportunities`, avec une latence simulée. Le mode mock fonctionne aussi dans le build de production.

Pour une future bascule, utiliser `VITE_DATA_MODE=api` et une base d’URL adaptée, puis reconstruire le frontend. Docker route déjà `/api/` vers FastAPI sur la même origine. Vérifier qu’une collecte `sync-lol-catalog` a publié son catalogue et ses images avant cette bascule ; aucune opportunité réelle ne sera renvoyée tant que des cotes et des estimations valides ne sont pas disponibles. L’absence d’API affiche une erreur réelle ; elle ne déclenche jamais un fallback silencieux vers les mocks. Les anciennes inscriptions du service worker MSW de cette origine sont supprimées en mode API. Les variables `VITE_*` sont publiques : **n’y placer aucun secret**.

Le [contrat HTTP](docs/api-contract.md) décrit les endpoints. Les contrats exécutables sont dans les schémas Zod.

## Données et couverture

Le snapshot frontend du 14 septembre 2026 contient **35 compétitions, 262 équipes, 297 fichiers de logos**, issus des pages publiques LoL Esports. La collecte backend du 15 septembre a publié **35 ligues, 262 équipes et 295 URLs de logos distinctes** ; les deux décomptes d’images diffèrent car certaines identités partagent une URL. Les six ligues majeures et la LFL sont présentes ; les sources comprennent les ERL, les circuits Challengers et les événements internationaux. Le TFT est exclu.

Ce snapshot couvre le catalogue et les rencontres exposés par Riot à la date de collecte, **pas toutes les compétitions amateurs mondiales**. Les affiliations secondaires sont inférées des rencontres domestiques visibles ; elles ne constituent pas un registre de contrats ou de rosters actifs. Certaines compétitions internationales n’ont volontairement aucune équipe affectée comme ligue d’origine. Le modèle utilise des identifiants ouverts, sans enum de ligues ou de teams : tout nouveau circuit peut être ajouté.

**34 opportunités sur 30 compétitions sont fictives.** Le scénario est fixé aux 14–15 septembre 2026, en heure de Paris. Les rencontres, formats, horaires, probabilités, cotes, historiques et mentions de bookmakers illustrent le produit ; ils ne décrivent aucune offre réelle. Aucun pari, paiement ou modèle prédictif n’est connecté. L’authentification email est réelle et indépendante de ces fixtures.

Les [sources et droits des assets](docs/data-sources.md) sont documentés. Après démarrage de Docker, les deux collectes backend se lancent depuis la racine :

```sh
npm run data:lol:sync
npm run data:oracle:sync
```

`data:lol:sync` collecte les identités et logos, puis les publie ensemble en base ; il n’écrit pas dans le frontend. `data:oracle:sync` traite toutes les années découvertes. Les noms Python sont `uv run metiquo-worker sync-lol-catalog` et `uv run metiquo-worker sync-oracles-elixir` (connexion PostgreSQL requise). Oracle accepte `--latest` ou `--years 2026`. Les anciens noms `npm run catalog:sync` et `metiquo-worker collect` restent des alias ; les anciens scripts Node qui réécrivaient les fixtures ont été retirés.

La planification intégrée utilise les mêmes fonctions et des verrous PostgreSQL propres à chaque source. Un échec préserve la version active et entraîne une nouvelle tentative progressive. Voir le [guide des deux collecteurs](docs/collectors.md) pour les paramètres, les commandes sous PowerShell et l’utilisation avec cron. Aucune modification de l’UI/UX ni bascule en mode API n’est effectuée par ces commandes.

### Audit Oracle’s Elixir

L’[audit du 15 septembre 2026](docs/oracles-elixir-audit.md) a validé la récupération des **13 CSV Oracle’s Elixir (2014–2026)** par téléchargement groupé en ZIP, malgré le quota bloquant les liens individuels. L’archive complète contenait 848,6 Mo de CSV et 1 223 472 lignes vérifiées. Les scripts temporaires de cet audit ont été supprimés. À la demande suivante, cette méthode a été implémentée dans le worker permanent, avec validation, empreintes SHA-256 et import atomique. Le frontend n’utilise pas encore ces données. Cette voie dépend toujours du service Google ; elle n’offre pas de garantie absolue de disponibilité.

## Vérification des états mock

- `/?mock=slow` : requête de 3 secondes pour observer la sortie du splash vers les skeletons et le spinner fixe ; les champs restent utilisables pendant l’attente.
- `/?mock=empty` : aucune opportunité.
- `/?mock=error` : erreur initiale et sa tentative automatique, puis réussite au clic sur « Réessayer ».

Ces paramètres concernent seulement MSW et ne sont pas actifs en mode API. Les données normales reviennent à `/`.

Le thème suit le système tant qu’aucun choix n’a été effectué. Un changement manuel est persisté et appliqué avant le premier rendu. Les favoris sont propres à cet appareil ; aucune session utilisateur n’est simulée.

## Interface et stabilité visuelle

- Même interface en modes mock et API, sans badges de démonstration (décision produit du 15 septembre 2026). Les fixtures restent fictives et identifiées comme telles dans cette documentation.
- Splash constitué du symbole Metiquo et d’un petit spinner, avec styles critiques intégrés au HTML. Le thème est appliqué avant la première image. L’attente des données est limitée à 700 ms ; ensuite l’interface apparaît par fondu avec des skeletons si nécessaire. L’attente indépendante des polices reste bornée à deux secondes. Une API lente ne bloque donc plus tout l’écran jusqu’au timeout HTTP.
- Inter et Manrope sont préchargées depuis `public/fonts`. Un délai de deux secondes borne l’attente des polices ; en cas d’échec ou de délai dépassé, la police système reste utilisée pour toute la page, sans remplacement tardif. `font-display: optional` complète cette protection. Le catalogue et les opportunités sont préchargés via les mêmes requêtes validées et le même cache que l’écran.
- Les erreurs de données restent visibles avec une nouvelle tentative manuelle. Un appel HTTP est limité à 15 secondes. Le spinner d’actualisation est fixe, en bas à droite, avec un nom accessible et sans texte de chargement visible.
- Dialogues et panneaux Radix conservés pendant leur animation de fermeture, puis démontés par Radix. Animations d’opacité et de transform, sans flou sur toute la page. Gouttière de scrollbar réservée et absence de double compensation lors des verrouillages imbriqués.
- Les styles communs se trouvent dans `styles/interactions.css`. Ne pas réintroduire de padding nul pour les boutons à fond survolé, de fallback de chargement dans le flux, ou de montage conditionnel coupant la fermeture d’un dialogue.
- Sélecteur de jeux : League of Legends disponible ; Counter-Strike 2 et Dota 2 réellement désactivés, avec la mention « À venir » et les logos officiels locaux.
- La cote affichée, la value, les tris et la courbe reposent sur le dernier relevé Stake. Un premier relevé isolé est valide. Le graphique utilise les dates pour l’axe horizontal et des paliers entre les relevés, sans inventer une évolution intermédiaire.

## Navigation, mobile et suivi

- L’URL conserve la vue (`view=favorites`), la ligue et l’équipe par identifiant (`league`, `team`), le marché (`market`), le seuil (`min`), la recherche (`q`), le tri (`sort`), la page (`page`) et le détail (`detail`). F5 et précédent/suivant restaurent ce contexte. La saisie remplace l’entrée courante de l’historique pour éviter une entrée par caractère. Les paramètres externes, dont les scénarios MSW, sont préservés. Un détail absent présente un état indisponible avec retour aux résultats.
- Un lien vers les favoris conserve la vue ; les favoris eux-mêmes restent locaux à l’appareil et ne sont pas inclus dans l’URL.
- La pagination replace le focus et la lecture sur le titre des résultats. Sur mobile : introduction compacte, cibles de boutons d’au moins 44 × 44 px, probabilité visible et action « Détail » explicite. Les skeletons réservent les mêmes trois rangées que les cartes.
- Un résultat vide dans les favoris distingue l’absence de favoris, les filtres bloquants et les opportunités sorties des données disponibles. Effacer les filtres conserve la vue des favoris.
- Le catalogue recherche sans tenir compte des accents, de la casse ou des espaces périphériques. Les régions sont traduites avec un repli ouvert pour les futures régions. Choisir une équipe filtre ses opportunités par identifiant, sur les deux côtés de la rencontre.
- L’historique propose tout le suivi, les dernières 24 heures ou les 7 derniers jours, en prenant le dernier relevé comme fin de période. Les points se sélectionnent sur la courbe ou au clavier via le curseur et les boutons précédent/suivant. Le tableau affiche la même période, avec les variations par rapport au relevé précédent, même situé hors période. Le panneau comporte une seule zone de défilement, avec en-tête et pied fixes.
- La liste expose des rôles de tableau, lignes, colonnes et cellules, avec libellés des chiffres. L’en-tête Value n’affiche plus d’icône suggérant un bouton ; le tri reste dans son sélecteur. L’encart d’aide annonce explicitement le calcul expliqué.

Les vérifications et leurs limites sont consignées dans [docs/verification.md](docs/verification.md). L’API implémente le contrat de suivi Stake, en attente du collecteur et d’un modèle d’estimation réels ; les anciens tableaux d’offres multi-bookmakers ne sont plus acceptés.
