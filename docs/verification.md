# Vérifications de la première version

## Diagnostic du refus SofaScore de 15:46:40 — 21 septembre 2026

Le [rapport détaillé](sofascore-403-2026-09-21-1546.md) reconstitue huit lectures de journées avant un nouveau 403, sans fiche de match ni appel API JSON direct. Le worker a été arrêté à 15:48:49 pendant l'analyse pour empêcher la reprise prévue à 16:01:40. Aucun accès de diagnostic à SofaScore ni changement du délai conservé en base.

Une reproduction Chromium avec `--network none` établit que fermer la page avant de persister le refus peut reprendre et nettoyer le cycle avant le retour du callback. La correction inverse cet ordre et garantit la coupure dans un `finally`. La reproduction avec l'ancien code perd le refus ; avec le code corrigé, elle conserve ses métadonnées et transmet le délai. Les deux tests de régression 403/document et 429/XHR échouent avant la correction et passent après.

`npm run check` passe : 59 tests frontend, 108 tests backend hors intégration, TypeScript, ESLint, build, Ruff et mypy. Les 47 intégrations PostgreSQL ne sont pas relancées. Aucun parcours UI modifié ni nouvelle vérification visuelle nécessaire pour cette correction du worker. Avertissements préexistants du bundle et de Starlette/httpx. La correction n'est pas déployée ; le worker demeure arrêté et aucun déblocage côté SofaScore n'est annoncé.

## Relance du worker après autorisation — 21 septembre 2026

Après le « go » explicite de l’utilisateur, seul le service `worker` est reconstruit et redémarré avec `--no-deps`, à 15 h 43 (Paris). Son healthcheck et son heartbeat PostgreSQL sont valides. Le volume dédié `sofascore_browser` est monté sur `/data/browser`, le profil Chromium est créé, et les réglages effectifs correspondent aux caches et pauses documentés. L’ancien délai jusqu’à 15 h 22 n’a pas été réinitialisé. Les trois premières pages de journées (21, 22 et 20 septembre) sont relues à 15:43:23, 15:43:55 et 15:44:19 ; aucun nouveau 403 n’est enregistré à ce stade, le dernier reste celui de 13:22:54. Le cycle SofaScore est encore en cours : ce contrôle de démarrage ne prouve pas l’achèvement d’un cycle ni l’absence de blocage ultérieur. Oracle termine son import planifié dans sa file indépendante. Aucun code applicatif n’est changé lors de cette relance ; les contrôles complets de la refonte ci-dessous restent la dernière validation du code.

## Détail des cartes épuré — 21 septembre 2026

- Bans sans cartes ni noms permanents : portraits circulaires, cibles de 44 × 44 px, nom au survol et bulle Radix au clic/Entrée ; cinq portraits par ligne lorsque cinq bans sont publiés. Équipes, bans et statistiques suivent les identifiants gauche/droite de la rencontre. Une abréviation vide laisse place au nom complet.
- Comparaison unique des huit statistiques globales, inconnues `—` distinctes des zéros, et compositions sur deux colonnes puis une seule. Les détails joueurs restent accessibles, y compris les rôles, niveaux, K/D/A, CS et or ; les en-têtes de tableau restent exposés aux technologies d’assistance sur mobile.
- Navigateur en mode API sur les relevés locaux Team Liquid–FlyQuest et MVK–Saigon Warriors : thèmes clair/sombre, largeurs 320, 390, 768 et 1440 px ; aucun débordement horizontal du contenu de la modale aux dimensions vérifiées. Les onglets de cartes gardent leur propre défilement horizontal sur petit écran. Changement de carte par flèche, cartes non jouées désactivées, ouverture du nom d’un ban au clic et avec Entrée, fermeture Échap et restitution du focus au portrait puis à la rencontre vérifiés. Aucune erreur/warning console observée dans le parcours Vite. Les règles CSS désactivent les nouvelles animations avec `prefers-reduced-motion`.
- `npm run check` passe : TypeScript, ESLint, 59 tests frontend, build, Ruff, mypy et 106 tests backend hors intégration. Pas de nouvelle suite PostgreSQL ni de collecte réelle pour cette refonte d’affichage. Avertissements existants : taille du bundle mock et dépréciations Starlette/httpx.
- Seul le service Docker `web` est reconstruit en mode API avec `--no-deps`. Le worker SofaScore reste arrêté, en attente du « go » explicite ; les données affichées sont celles déjà enregistrées.

## Réduction des délais de cache SofaScore — 21 septembre 2026

Les caches des journées passent à 3 minutes / 15 minutes / 1 heure pour aujourd'hui / futur / passé. Les fiches proches / programmées / terminées avec cartes / terminées sans cartes passent à 3 minutes / 15 minutes / 1 heure / 5 minutes ; le live reste à 2 minutes. Code, Compose, exemple et `.env.docker` local sont alignés. Les tests existants de fraîcheur et de sélection des journées ont été adaptés et `npm run check` passe : 59 tests frontend, 106 tests backend hors intégration, build et contrôles statiques. Compose est valide. Aucun comportement navigateur ni parcours UI changé, aucune collecte réelle, worker confirmé arrêté en attente du « go ». Les suites PostgreSQL et navigateur de la modification précédente n'ont pas été répétées pour cet ajustement de configuration.

## Session SofaScore persistante, cache et pauses — 21 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, build, Ruff, mypy, 59 tests frontend et 106 tests backend hors intégration. La première suite PostgreSQL 18 isolée a validé 152 tests ; le test ajouté ensuite sur l'échec de publication a été validé avec quatre régressions d'intégration existantes, soit 153 cas backend distincts validés, dont 47 intégrations. Le conteneur PostgreSQL temporaire et son volume ont été supprimés.
- Régressions couvertes : ne relire que les journées dues ; dédupliquer les recommandations et les URLs alternatives ; ne jamais retenter une page pendant le même cycle ; terminer le cycle dès le premier document 403 ; conserver la pause après un onglet échoué ; ne rouvrir que les nouvelles cartes live ; ne pas republier les anciennes cartes comme fraîches ; démarrer la pause après lecture complète et conserver son horodatage entre instances ; invalider les cartes non publiées après échec de transaction.
- Test navigateur explicite `tests/backend/browser_sofascore_smoke.py`, exécuté dans une instance de test avec `--network none`, sources du workspace en lecture seule et profil temporaire. Seul un serveur HTTP sur loopback est accessible. Trois pages utilisent un même contexte et téléchargent leur script partagé une seule fois. Après fermeture/réouverture de Chromium, le cookie persistant et le cache sont retrouvés. Un fetch 403 synthétique ferme la page, empêche son prochain appel différé et interdit toute nouvelle navigation du cycle. Les requêtes déjà parties avant réception de l'événement par le collecteur ne peuvent pas être annulées rétroactivement.
- Configuration Compose validée sans démarrage ; `.env.docker` local aligné sur les nouvelles pauses et échéances de cache sans modification de ses secrets. Le volume de profil est déclaré pour le prochain démarrage, sans monter ce profil dans l'API.
- Aucun parcours UI modifié. Aucun appel de validation à SofaScore, aucune reconstruction/déploiement du service applicatif, aucune relance du worker : son état Docker reste `Exited (0)` après l'arrêt volontaire. **Attendre le « go » de l'utilisateur pour les essais réels et la relance.** Les avertissements Starlette et le bundle MSW de plus de 500 kB restent préexistants.

## Scraping des picks et bans, sans plafond de matchs — 21 septembre 2026

- `npm run check` réussi : 59 tests frontend, 99 tests backend hors intégration, TypeScript, ESLint, Ruff, mypy et build. Suite PostgreSQL 18 isolée : 144 tests réussis, dont 45 intégrations. Le test supplémentaire du pipeline complet sur le DOM réellement observé a ensuite passé la suite ciblée portraits (4 tests) ; 145 cas distincts validés au total. La base temporaire et son volume ont été supprimés.
- Régression de couverture hors réseau : 15 journées et 135 matchs parcourus une fois dans une exécution ; aucun nouvel accès au second passage lorsque le cache est frais. Tests des bans sans nom, déduplication, conservation des identifications récentes, ambiguïtés visuelles et absence de lecture des corps API.
- Sur la page réelle Team Liquid–FlyQuest, le script DOM relève dix portraits de joueurs et dix bans, répartis 5/5. Neuf des dix images exportées correspondent au catalogue local ; un artwork différent reste inconnu. La projection hors ligne conserve les statistiques et les dix bans, même lorsque le nom ou les octets du portrait sont indisponibles.
- Chromium dans la nouvelle image worker, avec réseau désactivé et réponses images contrôlées : deux panneaux, dont un injecté après un délai, sont lus correctement ; dix bans par carte, noms reconnus et référentiel de 173 portraits présents. Ce test exécute le fichier JavaScript réellement empaqueté et le lecteur Python.
- Navigateur sur le frontend API local : modale LCS en clair/sombre, 390 × 844, 768 × 1024 et 1440 × 1050 ; dix bans conservés, aucun débordement horizontal de page/modale, changement de carte par flèche, fermeture Échap et retour du focus au bouton de rencontre. Ces contrôles utilisent les observations historiques déjà stockées ; le repli d’un ban sans nom est vérifié par le contrat, sans injecter de faux relevé en base métier.
- Worker, API et web reconstruits et redémarrés en mode API local. Référentiel présent, client `curl_cffi` absent et paramètres de plafonds absents du worker actif. Cadences et données conservées.

Limite externe vérifiée : le worker déjà sans appels API directs a reçu un **403 document à 10:20:10 UTC (12:20 à Paris)** sur la journée du 21 septembre. L’attente persistée jusqu’à **11:20:10 UTC (13:20 à Paris)** et les trois refus consécutifs sont conservés lors du remplacement. Aucun déblocage ni collecte complète depuis Docker n’est annoncé sur la seule base du navigateur manuel et des tests hors ligne. Les avertissements préexistants Starlette et taille du bundle MSW subsistent.

## Résilience SofaScore et rapprochement Oracle — 21 septembre 2026

`npm run check` réussi : 58 tests frontend, 96 tests backend hors intégration, TypeScript, ESLint, Ruff, mypy et build. Suite PostgreSQL 18 isolée : **141 tests réussis**. Les migrations `0009–0010` et les nouvelles images sont appliquées à Docker local ; services sains, délai SofaScore conservé au redémarrage. Contrôles navigateur sur Matchs et sa modale en clair/sombre, à 390/820/1440 px et au clavier ; reprise après interruption du serveur vérifiée. Catalogue exposé : 56 logos locaux sur 58 ligues LoL. La recherche Oracle réelle est passée d’une annulation après 166,97 s à 0,603 s ; les 414 cartes sans fuseau vérifié restent explicitement non rapprochées. Voir les [preuves et limites détaillées](sofascore-resilience-audit.md).

## Audit v1-ajout-live — 21 septembre 2026

Voir le [rapport dédié](review-v1-ajout-live.md) : 58 tests frontend, 129 tests backend avec PostgreSQL, collectes réelles Riot / Oracle / Data Dragon, validation du flux local de 74 matchs LoL et vérification navigateur. L’essai SofaScore a répondu HTTP 403 ; sa disponibilité externe reste une limite explicite.

## Filtres de ligue sur mobile — 16 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, build, 37 tests frontend et 51 tests backend hors intégration. Les deux avertissements de dépréciation Starlette préexistants subsistent.
- Chromium à 320, 390, 820 et 1440 px, clair et sombre : barre sur une seule rangée, logos agrandis, sélection contrastée, bouton Plus accessible et aucune largeur de page excédentaire observée. Actualiser apparaît une seule fois selon le breakpoint.
- Recherche par région (« japon »), sélection de LJL hors des raccourcis, ajout et visibilité automatique de la sélection dans la barre ; retour à toutes les ligues, actualisation, recherche sans résultat et effacement vérifiés.
- Panneau mobile ancré en bas, recherche fixe et liste défilante ; version centrée sur desktop. Entrée, Tab, boucle de focus, Escape et retour au bouton Plus vérifiés. Les animations respectent la règle CSS de mouvement réduit ; pas de test sur téléphone physique ni avec lecteur d’écran complet.

## Corrections de l’audit — 15 septembre 2026 (points 5–9 et 11–13)

- Pagination mobile : page 2 puis 3, focus replacé sur `values-title`, premières cartes visibles. Précédent/suivant du navigateur restitue les pages 2 et 3 et leurs URL.
- Mobile 320 et 390 px : introduction compacte, probabilité et action Détail visibles, noms longs MVKA–DINO sans débordement. Aucun bouton actif de la liste inférieur à 44 × 44 px dans la mesure DOM à 320 px. Thèmes clair et sombre inspectés.
- Chargement lent à 320 px : le splash disparaît pendant la requête, avec skeletons et spinner fixe ; la recherche reste utilisable et sa saisie est conservée à l’arrivée des données. Première carte à la même position (501,48 px) et de même hauteur (220 px) dans les états skeleton et chargé.
- Catalogue : `LFL` retrouve la LFL ; libellés français des régions, compteurs de rattachement explicites et participants internationaux non renseignés. Choisir T1 dans Équipes affiche ses deux marchés par identifiant, sans confondre T1 Academy ; le filtre survit à F5.
- Historique : 24 h affiche 7 relevés au lieu de 8 ; Home sélectionne le 13 septembre à 10:00 (1,64), un clic sur la courbe sélectionne le 13 septembre à 22:00 (1,70). Curseur de 44 px, tableau de la même période, un seul conteneur défilant dans le détail. En-tête à y=0 et pied à y=741 dans le viewport de 844 px après navigation clavier.
- Détail directement restauré après F5 depuis son URL. Les cellules et en-têtes de la liste sont présents dans l’arbre accessible, y compris les en-têtes visuellement masqués sur mobile. L’aide annonce son contenu et l’en-tête Value n’affiche plus un faux contrôle de tri.
- Tablette 768 × 1024 et desktop 1440 × 1000 inspectés. Catalogue en paysage 667 × 375 : défilement unique, en-tête fixe, navigation clavier vers les ligues et note de source après la liste.
- Tests ajoutés : sérialisation et validation du contexte URL, fermeture d’un détail conservé pour l’animation, filtre exact d’équipe sur les deux côtés d’un match, bornes temporelles 24 h/7 jours et premier relevé isolé.
- Vérification finale : `npm run check` réussi (TypeScript strict, ESLint, 21 tests dans 5 fichiers, build Vite). Formatage des fichiers modifiés et `git diff --check` réussis.
- Build de production sur 4173, en clair/sombre à 1280 × 900 : tableau et actions sans débordement ; filtre carte 1 + seuil 15 conservés après F5, puis effacement vers les résultats. Un lien de détail inexistant affiche un état indisponible ; son bouton ferme le panneau, nettoie l’URL et replace le focus sur le titre des résultats.

Ces vérifications sont réalisées dans Chromium. Les appareils physiques, Safari/Firefox et une mesure instrumentée des FPS restent hors de cette vérification ; aucun résultat sur ces environnements n’est déduit des contrôles locaux. Les points 1–4 et 10 de l’audit ne font pas partie de cette demande.

---

## Révision du 15 septembre 2026 — démarrage, interactions et Stake

Cette section remplace les observations antérieures sur la comparaison entre bookmakers, les badges de démonstration et le démarrage par skeletons.

### Vérifications exécutées

- `npm run check` : TypeScript strict, ESLint sans avertissement, **15 tests Vitest** et build de production réussis.
- Tests de calcul sur le dernier relevé, y compris baisse de cote et premier relevé sans variation. Contrats : intervalles irréguliers sur plusieurs jours, cotes inchangées, dates inversées ou dupliquées, dates manquantes, historique vide, cotes invalides, bookmaker autre que Stake et ancien contrat rejetés.
- Navigateur intégré Chromium, serveur de développement (5173) et build de production (4173).
- Inspections visuelles aux largeurs **320, 390, 768, 1024 et 1440 px**, en clair et sombre sur les parcours visités. Largeur du document mesurée : aucun débordement horizontal à ces formats. Images des parcours visités chargées sans erreur.
- Catalogue « Plus », filtres, aide, détail et navigation mobile ; sélecteur Radix dans une modale et dans la navigation. Escape, retour au déclencheur, bouclage du focus clavier et passage navigation → catalogue vérifiés. Le retour au bouton de navigation fonctionne après fermeture du catalogue lancé depuis le panneau mobile.
- À 1440 px, avant/pendant/après ouverture du catalogue : titre x=250, tableau x=250 et largeur=866. Dans le dernier build, le bouton Plus est à x=1051 et sa largeur vaut 65 px, avant/pendant/après ouverture. Les thèmes clair/sombre et les sélecteurs imbriqués ne changent pas la largeur du contenu.
- À 768 px, clic par coordonnées depuis une page défilée : scrollY=205 conservé à l’ouverture et à la fermeture, tableau x=24 et largeur=713. Les actions de test par locator peuvent elles-mêmes faire défiler la page avant de cliquer ; le contrôle par coordonnées distingue ce comportement d’un déplacement provoqué par la modale.
- Padding de « Plus » et « Actualiser » : 12 px à gauche et à droite. Sélecteur de tri : 8 px de chaque côté. Les règles de survol ne changent aucune dimension.
- Menu jeux : League of Legends sélectionné ; CS2 et Dota 2 désactivés avec logos locaux et mention « À venir ». Navigation clavier : les options désactivées ne deviennent pas sélectionnables.
- Détail BLG–TES : premier relevé 1,68, dernier 1,60, écart −0,08, value +7,2 %. Graphique et tableau des huit relevés cohérents sur deux dates, hausses et baisses incluses.
- Recherche catalogue « Karmine » dans les équipes : Karmine Corp et Karmine Corp Blue, avec leurs ligues.
- Build `?mock=slow` : splash avec symbole et spinner observé avant l’interface. Au clic « Actualiser », six lignes restent affichées ; spinner fixe de 44 × 44 px en bas à droite, texte visible vide, nom accessible « Actualisation des données ».
- Build `?mock=error` : erreur affichée après la tentative automatique, puis récupération des six premières lignes via « Réessayer ». Build `?mock=empty` : état vide, aucune ligne inventée.
- Favori BLG–TES conservé après rechargement du build, puis retiré à la fin de la vérification. Polices Inter et Manrope confirmées chargées via `document.fonts.check`. Aucun avertissement ni erreur console sur le dernier parcours normal de production.
- `git diff --check` réussi. Les fichiers modifiés passent Prettier ; `npm run format:check` signale uniquement le fichier préexistant `pnpm-lock.yaml`, laissé inchangé.

### À préserver lors des prochaines modifications

Rejouer les parcours ci-dessus après toute modification des polices, du bootstrap, des boutons communs, de la gouttière, des portals ou des animations. Garder les composants de modales montés avec `open=false` pendant la fermeture Radix. Ne pas ajouter une seconde compensation de scrollbar lorsque la gouttière racine est réservée. Tester une cote en baisse et un historique d’un seul point après chaque changement de contrat.

### Limites

Tests navigateur réalisés dans Chromium sur cet ordinateur ; pas de mesure certifiée de FPS, ni de validation sur appareils physiques iOS/Android ou dans Safari/Firefox. La réduction des animations est prise en charge dans le splash, le CSS et Motion ; la préférence système n’a pas été modifiée pendant ces essais. La panne ou la lenteur des fichiers de police n’a pas été forcée dans le navigateur ; le repli système permanent est prévu dans le bootstrap. Aucun backend ni flux Stake réel n’est connecté. Les tests de contrats sont automatisés dans Vitest ; la vérification visuelle reste un parcours navigateur documenté.

---

Réalisées le 14 septembre 2026 sur le frontend local, puis sur le build de production.

## Contrôles de code

- TypeScript strict : réussi.
- ESLint : aucune erreur ni avertissement.
- Vitest : 9 tests réussis (calculs, domaines de validité, meilleure cote, intégrité du référentiel et des fixtures, filtres combinés, tris).
- Build Vite de production : réussi, sans avertissement de taille de chunk.
- Prettier : formatage vérifié.
- Les 297 assets du catalogue sont présents en WebP, pour environ 1,85 Mo au total.

## Parcours vérifiés dans le navigateur

- Chargement des 34 opportunités du scénario.
- Recherche « Karmine » : deux opportunités distinctes, KC et KCB.
- Ouverture et fermeture d’une analyse, comparaison des trois offres et cohérence du calcul affiché.
- Fermeture avec Escape et retour du focus au déclencheur.
- Seuil de value à 15 % : état vide ; réinitialisation : retour des résultats.
- Pagination : passage de 1–6 à 7–12 puis retour.
- Catalogue LFL : 10 équipes présentes, noms et logos chargés.
- Mode `?mock=error` : erreur initiale, tentative automatique, récupération après « Réessayer ».
- Mode `?mock=slow` : skeletons observés avant le résultat. À 1440 px, la hauteur d’une ligne est de 81 px dans les deux états ; largeur et position du tableau conservées.
- Thèmes clair/sombre : préférence persistée et géométrie du contenu conservée. Ouverture du drawer : position horizontale du contenu inchangée.
- Curseur de texte : transparent sur le contenu non éditable, visible dans l’input ; sélection désactivée sur les boutons.
- Formats 320, 390, 700, 768, 1024 et 1440 px : contrôles de largeur et inspection visuelle sur mobile, desktop et drawer.
- Build de production servi sur le port 4173 : chargement des mocks, panneau d’analyse, aucun avertissement/erreur console et aucune image cassée observée.

## Limites de cette vérification

Ces contrôles ne sont pas une certification d’accessibilité ni une garantie d’absence de bugs sur tous les appareils. La réduction des animations est prise en charge par Motion et la media query CSS ; le réglage système n’a pas été modifié pendant les tests. Aucune offre de pari réelle n’a été vérifiée. Les tests navigateur ci-dessus ont été effectués dans la session de développement ; seuls les tests métier sont inclus dans la suite Vitest.

## Backend et Docker — 15 septembre 2026

- `npm run check` réussi : 21 tests frontend, TypeScript, ESLint, build, Ruff et mypy strict ; 29 tests backend hors réseau. Suite backend complète avec PostgreSQL : **35 tests réussis**. Migration descendante puis ascendante vérifiée dans la base de test et `alembic check` sans divergence.
- Vérification des **13 SHA-256** publiés par l’API contre l’audit ; téléchargement complet du CSV 2026 via Nginx avec empreinte identique et lecture des 165 colonnes par l’endpoint paginé.

- Construction des images web, API et worker ; démarrage PostgreSQL 18.6, migration Alembic `0001`, sondes de santé et proxy Nginx.
- Collecte réelle avec Patchright/Chromium sous Linux dans Docker : 13 CSV (2014–2026), ZIP de **233 672 676 octets**, publication atomique terminée le **15 septembre 2026 à 17:52 UTC**.
- **1 223 472 lignes**, **848 628 282 octets de CSV**, 13 versions actives. Taille PostgreSQL observée après import : environ 2 502 Mo, hors sauvegardes et versions futures.
- Nouvelle collecte ciblée 2026 avec compagnon 2014 à **17:54 UTC** : ZIP de 22 748 340 octets, **0 nouvelle version, 2 fichiers inchangés**. Pas de doublon en base.
- Catalogue Riot importé explicitement : 35 ligues, 262 équipes. Les réponses API `/catalog` et `/opportunities` passent les schémas Zod existants du frontend ; les opportunités réelles sont vides.
- Le rôle SQL de l’API est `metiquo_api` : une tentative d’écriture sans effet (`WHERE false`) est refusée par PostgreSQL. Patchright est absent de l’environnement Python de l’image API.
- Tests PostgreSQL sur une base isolée `metiquo_test` : import répété, rollback de toute la publication si le deuxième fichier échoue, préservation après archive invalide, exclusion mutuelle des workers, pagination par version, historique de cotes et expiration des estimations.
- Tests hors réseau : CRC/ZIP corrompu, fichiers inattendus, chemins de sortie, taille maximale, réponse HTML de quota en HTTP 200, longueur/MD5 incorrects, CSV invalide, nouvelles années, conservation du champ de saison et des dates originales, contrat Stake explicitement non implémenté.
- Vérification navigateur sur `http://127.0.0.1:8080` : chargement du frontend mock, ouverture du détail, fermeture avec Escape ; aucune erreur/alerte console observée. Aucun fichier dans `apps/web` modifié. Les parcours responsive et les thèmes n’ont pas été retestés intégralement lors de cette livraison backend.

Les deux avertissements de dépréciation observés dans le client de test Starlette (HTTPX et alias AnyIO) proviennent des dépendances de test. Les sauvegardes/restaurations complètes et un déploiement distant ne font pas partie des essais réalisés. L’export Google reste une dépendance externe ; le succès observé ne constitue pas une garantie permanente.

## Authentification email et Mailpit — 15 septembre 2026

- `npm run check` réussi après l’intégration : TypeScript, ESLint, **23 tests frontend**, build, Ruff, mypy strict et **31 tests backend hors intégration**. Suite backend entière avec PostgreSQL dans `metiquo_auth_test` : **50 tests réussis**, dont 19 tests d’intégration. Deux avertissements de dépréciation Starlette déjà présents ; aucune erreur de test.
- Migration `0002` testée en descente/remontée deux fois sur la base isolée, provisionnement admin conservé et `alembic check` sans divergence. Migration appliquée à la stack locale sans toucher aux données Oracle’s Elixir. Inscription et connexion réellement testées avec le rôle SQL limité de l’API dans Docker.
- Tests de sécurité : absence de compte avant validation, normalisation de l’email, six chiffres ASCII et zéros initiaux, refus des champs `role`, challenge lié au navigateur, usage unique et deux validations concurrentes, cinq essais maximum, limites minute/heure persistantes, remplacement lors d’un renvoi, panne SMTP conservant le code précédent, expiration serveur des codes et sessions, rotation du token, révocation après déconnexion, rejet d’origine et d’en-tête CSRF absents, cookies HTTPS `__Host-`/Secure/HttpOnly, aucune donnée reçue recopiée dans les erreurs de validation.
- Vérification des privilèges PostgreSQL : refus de modification de rôle et de données esport par l’API ; refus de lecture des tables utilisateurs et sessions par le worker.
- Parcours navigateur sur le build Docker : demande de code `admin@metiquo.fr`, réception SMTP dans Mailpit, erreur sur code incorrect, connexion et profil Administrateur ; création automatique du compte de contrôle `metiquo.qa@example.com` avec rôle Utilisateur. La session persiste après rechargement et dans un autre onglet ; déconnexion répercutée entre onglets. Renvoi après le délai de 60 secondes testé : ancien code refusé, nouveau code accepté. Le compte de contrôle a été supprimé après les essais, le compte admin conservé. Aucune erreur/alerte console observée sur la dernière session navigateur.
- Focus initial dans l’email, passage au code, navigation Tab, boucle de focus dans la modale, Escape et retour au bouton d’origine vérifiés. Aucune route de connexion créée. La réduction des animations système n’a pas été modifiée pendant cette session ; la modale et les boutons réutilisent les règles existantes.
- Contrôles de largeur et inspection visuelle mobile/tablette/desktop en clair et sombre : 320, 390, 768 et 1440 px. Le dernier chiffre était initialement coupé sur 320 px ; espacement corrigé et six chiffres visibles, sans défilement horizontal du champ. Boutons de la modale d’au moins 44 px sur mobile. La zone centrale défile sur faible hauteur en conservant l’en-tête et la fermeture accessibles.

Mailpit valide seulement la chaîne locale SMTP → email → code → session. La livraison dans une boîte externe, le DNS expéditeur, HTTPS sur un domaine public et une charge distribuée n’ont pas été testés. Les tests ne constituent pas une certification d’accessibilité ou de sécurité. Les données esport restent mockées ; l’authentification est réelle.

### Validation des champs sans décalage — 15 septembre 2026

- `npm run check` réussi : 23 tests frontend, 31 tests backend hors intégration, TypeScript, ESLint, build, Ruff et mypy. Pas de modification du backend pour cet ajustement.
- Build Docker actualisé et contrôlé au navigateur. Email vide au clic ou avec Entrée, email mal formé, correction vers une adresse valide ; code vide, incomplet puis refusé par la vraie API.
- Mesure des rectangles de la modale, de l’input, du bouton et du pied : **écart maximal 0 px** lors des changements d’état email en clair/sombre à 320, 390, 768 et 1440 px. Même stabilité pour les erreurs locales et serveur du code sur 320 px.
- Espace de retour calculé à partir des textes possibles, avec leur retour à la ligne réel. Aide, erreurs et confirmation se remplacent dans cette zone ; les messages de renvoi et de déconnexion utilisent aussi le composant partagé. Aucun texte coupé et aucun débordement horizontal observé.
- `noValidate` supprime les bulles natives ; `required`, `aria-invalid`, `aria-describedby`, région d’annonce et focus sur le champ restent présents. Escape ramène le focus au déclencheur. Les champs invalides sont rejetés avant la mutation HTTP ; les recherches et curseurs n’ont pas de validation obligatoire à ajouter.
- Aucune erreur/alerte console observée. Les transitions d’opacité/translation durent 160 ms et sont annulées par `useReducedMotion` ; la préférence système n’a pas été changée pendant la vérification.

## Collecteurs LoL et Oracle’s Elixir — 15 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, **23 tests frontend**, build, Ruff, mypy strict et **43 tests backend hors intégration**. Suite backend complète dans la base PostgreSQL isolée `metiquo_collectors_test` : **67 tests réussis**, dont 24 d’intégration. Les deux avertissements de dépréciation Starlette préexistants subsistent.
- Migration `0003` appliquée à la stack locale. Les essais PostgreSQL comprennent la descente/remontée des migrations et `alembic check`, la lecture avec les rôles limités, l’import répété, le rollback de la publication et les verrous. L’import administratif historique ne peut pas remplacer le catalogue pendant une collecte.
- Collecte réelle LoL terminée à **20:31:09 UTC** : **36 pages publiques, 35 ligues, 262 équipes, 295 URLs de logos**. Version publiée : `8e2e46aa-62c1-4773-9f40-d867b29bb522`. La liste des pages vient du registre source, sans liste fermée de compétitions dans le collecteur.
- Relance réelle à **20:38:07 UTC** : même version et même SHA-256, `changed=false`. La date de vérification avance sans nouvelle version. Tous les fichiers source déclarés restent rattachés aux exécutions ; les images sont immuables et partagées lorsque leurs octets sont identiques.
- Vérification via Nginx et l’API du document de référence, du contrat `/catalog` et des **291 fichiers WebP distincts** correspondant aux 295 URLs source : HTTP 200, SHA-256 identique au chemin, image décodable, dimensions au maximum 144 × 144 et réponse conditionnelle HTTP 304. Le premier essai réel a révélé un original LOUD de 8334 × 8334 px : la limite de pixels a été adaptée et le décodage sérialisé pour maîtriser la mémoire.
- Le référentiel contient **2 339 preuves de rattachement** : 58 `home`, 193 `tournament`, 2 088 `match`. Ces chiffres comptent des preuves, pas des équipes supplémentaires ni des affiliations saisonnières complètes. Les relations de saison absentes de la source restent nulles.
- Oracle : collecte réelle complète réussie à **20:25:14 UTC**, **13 fichiers 2014–2026**, 12 inchangés et une nouvelle version 2026. La base possède **1 223 508 lignes actives**, dont **104 712 pour 2026**. Les versions précédentes sont conservées.
- Oracle ciblé avec `--latest` : réussite à **20:36:54 UTC**, année 2026 et compagnon 2014, **0 import, 2 fichiers inchangés**. Une sélection Drive instable observée pendant les essais a été corrigée : attente de la sélection de chaque ligne et vérification de l’ensemble avant export. L’échec antérieur n’avait pas modifié les versions actives. Téléchargement du CSV 2026 par l’API avec SHA-256 vérifié.
- Tests de panne et de cache : source illisible, inventaire tronqué, URL d’image non autorisée, image invalide ou trop grande, octets modifiés à URL constante, publication annulée, ancienne version toujours lisible et absence de doublon. Le test du planificateur confirme qu’un échec LoL ne supprime pas une échéance Oracle.
- Images Docker API et worker reconstruites, services redémarrés et sains. Le worker annonce les deux collecteurs actifs ; les échéances persistées évitent de recollecter au redémarrage. Les commandes manuelles, alias, codes de sortie et exemples cron sont documentés dans [le guide des collecteurs](collectors.md).
- `git diff --check` et Prettier sur les fichiers de documentation et configuration concernés réussis. Aucun composant, style, fixture ou asset du frontend n’a été modifié pour cette livraison ; seul l’ancien outil de conversion Sharp a été retiré des dépendances. Aucun parcours UI n’a été modifié, donc la matrice navigateur clair/sombre et responsive n’a pas été rejouée.

La découverte couvre les données exposées par les pages publiques Riot à la collecte, pas tous les rosters et toutes les saisons de LoL. Les essais réseau attestent du fonctionnement observé, pas d’une disponibilité permanente de Riot ou de Google. Les cadences du planificateur sont testées sans attendre une semaine réelle ; aucun cron système ni déploiement distant n’a été créé.

## pgAdmin dans Docker — 15 septembre 2026

- Image officielle `dpage/pgadmin4:9.17` épinglée par digest ; service `pgadmin` sain, exposé sur `127.0.0.1:5050` uniquement. Connexion au réseau interne PostgreSQL, volume `pgadmin_data`, exécution non privilégiée, capacités Linux supprimées et sonde `/misc/ping` validés au démarrage réel.
- Connexion au compte pgAdmin dans Chromium, présence du serveur préconfiguré **Metiquo — PostgreSQL**, saisie du mot de passe PostgreSQL et message **Server connected.** observés. Le mot de passe de base n’a pas été enregistré via la case « Save Password ». Les identifiants existants de la base fonctionnent sans rotation.
- Le conteneur pgAdmin a été recréé après son initialisation pour appliquer le réglage SMTP : le compte et l’unique connexion préconfigurée sont conservés dans le volume. Mailpit est configuré comme SMTP local ; l’envoi d’un email de réinitialisation n’a pas été déclenché.
- Initialisation testée dans un dossier temporaire avec un template CRLF : cinq secrets distincts, relance sans changement, ajout des réglages auth/pgAdmin sur une ancienne configuration sans remplacer les trois mots de passe PostgreSQL. Une nouvelle exécution sur `.env.docker` réel le conserve octet pour octet. Aucun secret ajouté aux fichiers versionnés.
- `docker compose config --quiet` et `npm run check` réussis : 23 tests frontend, 43 tests backend hors intégration, TypeScript, ESLint, build, Ruff et mypy. Les deux avertissements Starlette déjà documentés subsistent. Aucune modification de l’interface Metiquo ni de son schéma SQL ; les tests PostgreSQL complets et la matrice UI responsive/thèmes n’ont pas été rejoués pour cet ajout d’infrastructure.

## Erreurs et reprise — 16 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, **37 tests frontend**, build, Ruff, mypy et **51 tests backend hors intégration**. Suite PostgreSQL complète dans `metiquo_errors_test` : **82 tests réussis**, dont 31 d’intégration. Deux avertissements Starlette préexistants. Prettier et `git diff --check` réussis.
- Chromium : 404 en clair desktop et sombre mobile, retour par Tab/Entrée, focus initial ; 401 sur une vraie session anonyme, ouverture de la modale email et retour du focus avec Escape ; 403 en Admin et 423 sur petit écran ; 429 des données et du formulaire, attente conservée après F5 et réouverture ; reprise des données après un 503. Largeurs 320, 390, 820 et 1440 px, thèmes clair et sombre, sans débordement observé.
- Injection des erreurs de service par un proxy HTTP de test isolé, sans couper la stack utilisateur, sans créer de compte ni modifier de rôle. Les autorisations, limites et suspensions réelles sont couvertes par les tests PostgreSQL ; aucun scénario d’authentification fictive livré dans MSW.
- Démarrage du build avec modules JavaScript volontairement indisponibles : repli HTML et lien de rechargement fonctionnels. Le contrôle a détecté un identifiant retiré par Vite ; la détection utilise maintenant les scripts modules émis par le build. Aucun test d’un appareil physique ou d’un lecteur d’écran complet.
- Nginx dans un conteneur temporaire : chemin inconnu = HTTP 404 avec HTML applicatif ; ressource `/assets/` absente = HTTP 404 sans HTML applicatif ; API inaccessible = JSON HTTP 503, `Retry-After: 30`, `Cache-Control: no-store`. Aucun déploiement public.

## Contour de focus après F5 — 16 septembre 2026

- Reproduction navigateur : clic sur le titre de page puis F5, le `main[tabindex="-1"]` reçoit `:focus-visible` et un contour de 2 px. La règle commune retire uniquement le contour des conteneurs structurels non interactifs ; titres, contrôles, widgets avec rôle et champs éditables sont préservés.
- Vérification en clair et sombre aux formats 1440 × 900, 768 × 1024 et 390 × 844 : aucun contour du conteneur ni débordement horizontal. Rechargement réel, lien d’évitement puis Tab, pagination au clavier et fermeture de modale avec retour au bouton déclencheur vérifiés ; indicateurs clavier conservés. Sélection du texte inchangée.
- `npm run check` réussi : 37 tests frontend et 51 tests backend hors intégration, TypeScript, ESLint, build, Ruff et mypy. Deux avertissements de dépréciation Starlette préexistants. Aucun test d’intégration PostgreSQL ni appareil physique rejoué pour cette modification CSS.
- Frontend Docker local reconstruit seul et correction confirmée sur `http://127.0.0.1:8080`.

## Navigation, calendrier et code automatique — 16 septembre 2026

- `npm run check` : TypeScript, ESLint, 41 tests frontend, build Vite, Ruff, mypy et 51 tests backend hors intégration réussis. Deux avertissements de dépréciation préexistants Starlette/httpx/anyio restent présents. Aucun code backend modifié dans cette intervention.
- Tests ajoutés pour les dates de Paris autour de minuit et des changements d’heure, les bornes J−7/J+7, les dates invalides, les liens partagés et le regroupement des marchés sans fusionner des rencontres à des horaires différents.
- Navigateur sur Vite (5173), API Docker existante : desktop 1440 px, tablette 820 px et mobile 390 px, clair/sombre. Pas de débordement horizontal observé ; cartes mobiles, logos locaux, sidebar défilante, filtres Radix, date sélectionnée maintenue visible au redimensionnement.
- Bornes du calendrier vérifiées par sélection du premier et dernier jour : flèche précédente/suivante désactivée à la borne respective ; jour précédent et retour navigateur restaurent la date. Saisie au clavier dans le champ date, retour à aujourd’hui, détail contrôlé. Rechargement sur la date sélectionnée : huit rencontres du jour, marchés multiples regroupés.
- Performance : filtre « En baisse » sélectionné au clavier, 11 marchés affichés sur 34 comparables ; aucune métrique de gain ajoutée. Accès directs Utilisateurs et Scripts & planifications contrôlés avec le compte administrateur ; Gestion absente après déconnexion. Modales Faire un don et Parrainage Stake, fermeture Escape et parcours de navigation mobile contrôlés.
- Authentification réelle avec le compte admin existant et Mailpit : cinq chiffres conservent le formulaire, le sixième déclenche la vérification et affiche le profil. Journal HTTP : une demande de code et une seule vérification, toutes deux 200. Aucun clic de validation nécessaire. Le collage est normalisé par le même gestionnaire, mais n’a pas fait l’objet d’une seconde connexion réelle lors de cette vérification.
- Limites : aucune opportunité réelle disponible côté API, pas de vérification d’un calendrier esport officiel, ni de transaction de soutien. Les tests PostgreSQL d’intégration n’ont pas été relancés pour cette évolution frontend. Les services locaux existants db, Mailpit, API et web ont été redémarrés pour vérifier l’authentification, sans reconstruction des images.

## Accordéons, cartes, simulation et soutien — 16 septembre 2026

- `npm run check` : TypeScript, ESLint, tests unitaires frontend, build Vite, Ruff, mypy et tests backend hors intégration exécutés. Les tests de simulation couvrent mises/gains/pertes/remboursements, centimes, rendement, seuil strict et flottants, filtres combinés, chronologie et rejet du futur/doublons ; les contrats de matchs couvrent compositions, côtés, vainqueurs et états. Le test PostgreSQL existant est étendu pour vérifier que les rencontres demeurent disponibles après expiration d’une estimation, mais l’intégration PostgreSQL n’est pas relancée.
- Navigateur Vite `127.0.0.1:5173` : ordinateur 1440 px, tablette 820 px, mobiles 390 et 320 px. Thèmes clair/sombre utilisés ; aucun débordement de page ou de modale observé aux dimensions contrôlées. Accordéon fermé initialement, score 1–0, carte active, carte future désactivée et navigation entre cartes avec flèche droite vérifiés. Les compositions se replient sur une colonne sur mobile ; les très petites largeurs affichent les statistiques des joueurs en cartes.
- Performance : passage de 10 à 20 € double le gain net (26,70 → 53,40 €) sans changer le rendement. Sélection simultanée de T1 et G2, courbe négative, remise à zéro, validation de mise nulle et touche Home du curseur contrôlées. Les axes du SVG suivent la largeur réelle du conteneur.
- Soutien : don et parrainage ouverts via navigation mobile ; copie du lien de don réussie. Pendant l’animation de fermeture, le titre reste « Soutenir Metiquo » et aucun contenu Stake n’apparaît. Escape et retour du focus à la navigation contrôlés. Liens temporaires `example.com` seulement ; aucune transaction externe effectuée.
- Limites : scores, joueurs et règlements sont les fixtures horodatées du mode mock. Aucun fournisseur de direct ni règlement réel n’est raccordé. API `/performance` vide par conception ; les nouveaux endpoints nécessitent de reconstruire l’API Docker si l’on utilise la stack déjà démarrée. Aucun déploiement réalisé.

## Chargements, transitions, comptes et identité — 16 septembre 2026

- `npm run check` réussi après les derniers ajustements : TypeScript, ESLint, **52 tests frontend**, build Vite, Ruff, mypy et **51 tests backend hors intégration**. Deux avertissements Starlette préexistants. Deux tests PostgreSQL ciblés réussis dans `metiquo_experience_test` : migrations descendantes/ascendantes et provisionnement des rôles avec conservation des identités, vérifications et suspensions, puis révocation des seules sessions dont le rôle change. La base de test a été supprimée après vérification ; la suite d’intégration complète n’a pas été rejouée.
- Migration `0005` appliquée à la base locale : `metiquo@admin.fr` est administrateur et `metiquo@user.fr` utilisateur. Les rôles sont aussi confirmés dans l’écran Utilisateurs. Le second compte reste « À vérifier » et sans session ; aucun email n’a été artificiellement vérifié. Le compte administrateur historique est conservé.
- Durées observées dans Chromium : **1 242 ms** pour un filtre Values en cache, **1 220 ms** pour une période Performance, **1 218 ms** pour un changement de journée Matchs. En scénario mock lent, l’actualisation Values conserve le skeleton environ **2 981 ms**, jusqu’à la réponse de trois secondes. Ce sont des mesures navigateur ponctuelles ; le minimum est fixé à 1 200 ms dans le hook partagé. Les requêtes démarrent immédiatement, les contrôles restent utilisables et les changements successifs aboutissent à la dernière sélection.
- Parcours contrôlés sur Vite et sur le build Docker à `127.0.0.1:8080`, en clair/sombre, aux largeurs **320, 390, 820 et 1440 px** : dates et retour à aujourd’hui, ligues Values, actualisation, périodes et réinitialisation Performance, recherche Utilisateurs, entrée dans Scripts. Skeletons de lignes/cartes, axes du graphique et panneaux latéraux adaptés à leurs composants finaux ; aucun débordement horizontal observé. Utilisation de Home sur le curseur, ouverture au clavier et fermeture Escape des modales, retour du focus à l’analyse de value vérifiés.
- Favoris absents de la navigation et du détail des values. L’ancienne URL `?view=favorites` mène à la reprise 404 ; son lien Retour aux values fonctionne au clavier.
- Logo fourni organisé sous `assets/brand/` et `apps/web/public/brand/`, avec archive complète conservée dans `.cache/brand-import/`. Source PNG et **20 exports** contrôlés par SHA-256 ; les octets servis par Docker correspondent aux fichiers importés. WebP chargé, variantes clair/sombre et favicon commutés, dimensions identiques ; logo vérifié dans sidebar, navigation mobile, fil d’Ariane, splash et en-tête 404. Les replis PNG sont présents ; le SVG encapsulant un gros bitmap n’est pas distribué.
- API et frontend Docker reconstruits, recréés et sains. Aucune erreur ou alerte console observée sur le parcours final du build. README, provenance et règles du projet actualisés ; aucun déploiement public.

Les animations utilisent les garde-fous de réduction des mouvements de Motion et CSS ; la préférence système n’a pas été changée pendant ces essais. Pas de test sur Safari, appareil physique, lecteur d’écran complet ou ajout réel d’icône à l’accueil iOS. Les données esport restent les fixtures documentées en mode mock ; l’authentification et l’administration utilisent la vraie API.
