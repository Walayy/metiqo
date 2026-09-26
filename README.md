# Metiquo

### Correction LoLTV du 26 septembre 2026

Les rencontres `WALKOVER` affichent **Forfait**, avec un filtre **Forfaits** et le score administratif publié. Ce score ne crée ni cartes jouées ni règlement des sélections Stake. Les flux anonymes identifiés mais encore vides restent indisponibles, sans nouveau relevé live. Une collecte ayant publié des observations valides se termine avec **Couverture incomplète** si d’autres lectures ont échoué ; Scripts et le journal expliquent les incidents sans exposer les réponses brutes. La migration **0021** corrige les anciens statuts uniquement avec une preuve de publication conservée, et garde les diagnostics historiques. Aucune variable d’environnement supplémentaire. Les pages périmées restent rejetées et la disponibilité de LoLTV n’est pas garantie ; voir [les détails et limites](docs/loltv.md#incident-du-26-septembre-2026).

### Ajustements du 24 septembre 2026

La liste Matchs signale les cotes consultables par un pictogramme discret. Dans le détail, chaque marché Stake apparaît une seule fois et sépare ses derniers relevés **Pré-match** et **En direct**, avec leurs dates et suspensions. Les sélections historiques gagnées, perdues ou annulées sont affichées après validation en base ; elles ne correspondent à aucun pari placé. Une phase ou un résultat absent n’est pas inventé ; les prix historiques restent sans value actuelle. Les SVG locaux LoL/LoLTV/Stake, les marges de survol et les halos des indicateurs sont documentés dans [les sources](docs/data-sources.md). Aucun nouveau paramètre d’environnement ni migration n’est nécessaire.

La fluidité bénéficie d’horloges limitées aux textes qui changent, d’un suivi de géométrie mutualisé et de surbrillances sans calcul de visibilité pendant le scroll. Les [mesures et limites](docs/audits/ui-performance/2026-09-24/README.md) décrivent le protocole avant/après ; l’instrumentation temporaire est retirée du produit.

Une application d’analyse des **values esport**, dédiée à League of Legends. Les données esport utilisent le mode explicite `mock` ou `api` ; l’inscription et la connexion par code email utilisent toujours la vraie API. Le worker synchronise le référentiel LoL, ses logos et les CSV Oracle’s Elixir dans PostgreSQL et un volume d’artefacts versionnés. **Stake est l’unique bookmaker suivi** ; son collecteur Chrome local conserve les marchés publics pré-match et en direct, leurs cotes horodatées et leurs suspensions. Les cotes mock sont fictives. En API, seules les cotes issues des snapshots Stake actifs et les values dont une estimation correspondante est déjà disponible peuvent apparaître ; aucune probabilité n’est fabriquée.

Sur mobile, les filtres de ligue défilent horizontalement avec des cibles tactiles de 48 px. **Plus** ouvre un panneau de sélection avec recherche par ligue ou région ; une ligue choisie hors des raccourcis reste visible dans la barre. **Actualiser** se trouve près du titre. Le catalogue complet reste accessible depuis l’indicateur des ligues.

Les conteneurs structurels non interactifs restent focalisables pour les liens d’évitement, sans contour englobant après un clic ou F5. Les contrôles et titres de navigation conservent leur indicateur de focus clavier ; le texte reste sélectionnable.

## Navigation et matchs par journée

Le détail d’une carte utilise des portraits ronds pour les bans, alignés avec chaque équipe sur ordinateur et regroupés par équipe sur mobile. Ces portraits ne sont pas cliquables : le survol ou le focus affiche le nom dans une infobulle, avec une surbrillance sans déplacement. Les noms restent accessibles aux technologies d’assistance. Un tableau commun compare éliminations, or et objectifs ; les joueurs conservent champion, rôle, niveau, K/D/A, CS et or dans deux colonnes sur ordinateur, puis une seule sur petit écran. Les inconnues restent `—`, avec une légende, et seules les équipes dont le camp est publié portent un repère bleu/rouge. Aucun changement de source ni lancement de collecte n’est nécessaire à cet affichage.

La sidebar place **Gestion → Utilisateurs / Scripts** en premier pour les administrateurs, puis **Esport → Matchs**, **Analyse → Les values / Performance** et **Soutenir Metiquo → Faire un don / Parrainage Stake**. Les modales de soutien gardent leur contenu pendant la fermeture. En mock, elles ouvrent ou copient un lien temporaire vers `example.com`, sans transaction. En API, `VITE_DONATION_URL` et `VITE_STAKE_REFERRAL_URL` fournissent les destinations HTTPS ; une destination absente ou invalide affiche l’état indisponible. Aucun compte bookmaker, don ni pari n’est créé dans Metiquo.

**Matchs** (vue d’accueil sur `/`, `?view=matches` reste accepté) affiche une journée de Paris entre J−7 et J+7, partageable (`date=AAAA-MM-JJ`) et restaurée par précédent/suivant ou F5. Les journées vides et la journée sélectionnée sont désactivées ; les flèches rejoignent la prochaine journée avec des rencontres. Aucun calendrier natif. Les ligues ont des accordéons Radix fermés initialement, logos sourcés, nombre de matchs, point discret au-dessus de la carte live ou décompte. Les rencontres sont triées par heure. La ligne montre seulement si des cotes Stake sont consultables. Le détail regroupe les marchés validés « Vainqueur du match » et « Vainqueur de la carte N » ; chaque marché distingue son dernier relevé pré-match et live sans répéter son intitulé. Les prix, suspensions et heures suivent les équipes ; une phase absente ne laisse pas d’emplacement. Une petite flamme signale une value positive strictement pré-match ; son pourcentage et la date complète du relevé se consultent dans l’infobulle. En match terminé, les statuts validés des sélections historiques sont visibles dans cette section ; les résultats en attente restent sans conclusion. En mock, ces cotes et résultats sont fictifs ; en API, seuls les relevés liés et résultats validés en base sont utilisés. Cliquer une rencontre ouvre aussi son score de série et ses cartes : les cartes non commencées sont désactivées, les cartes jouées détaillent les camps, champions, joueurs, K/D/A, CS, or et objectifs. Le score de série sourcé est prioritaire ; les cartes terminées servent de repli uniquement en son absence. Aucun score n’est inféré de l’heure.

**Performance** (`?view=performance`) est une simulation historique et non le relevé de paris personnels. Elle trace les gains nets cumulés avec une mise fixe, un seuil strict de value, une période de règlement, une ligue, plusieurs équipes sélectionnées (équipe sur laquelle porte la value) et un marché. Les paramètres de mise/seuil s’appliquent avec le bouton du formulaire, les autres filtres directement. La cote et la probabilité sont figées avant le début du match ; un seul engagement par marché, pas de résultats futurs. Le gain gagné vaut mise × cote − mise ; une perte vaut −mise ; une annulation vaut zéro et est exclue des mises réglées/du rendement. Calculs au centime. Le curseur du graphique fonctionne au clavier et le détail liste chaque règlement. Pas de capital initial, de réinvestissement automatique ni de promesse de rendement.

Ces vues utilisent des contrats Zod et des requêtes séparées `/catalog`, `/opportunities`, `/matches` et `/performance`, avec MSW uniquement en mode `mock`. Les rencontres, rosters, scores et 120 règlements historiques du scénario sont fictifs ; les noms de joueurs sont des alias et ne prétendent pas décrire les effectifs réels. Le catalogue complet des portraits officiels Data Dragon est conservé localement avec provenance et se met à jour avec `npm run data:champions:sync` (version et date de récupération dans `apps/web/src/domain/data/champions.json`). En API, `/matches` lit les rencontres stockées sans dépendre des marchés et laisse les statistiques inconnues ; `/performance` reste vide faute de source de règlements reliée aux décisions pré-match. Aucun collecteur live ou résultat n’est inventé. Les erreurs restent explicites. La vue Values ne présente plus d’encart date ni de date dans les lignes ; les horodatages d’analyse restent disponibles dans le détail.

Les destinations de soutien sont des variables publiques de construction, disponibles dans `apps/web/.env.example`, `.env.docker.example` et les arguments Docker. Après modification en mode API, reconstruire le frontend (`npm run build:api` ou `npm run docker:api`). N’y placer aucun secret.

## Application complète avec Docker

Prérequis : Docker Engine/Desktop avec Compose v2, Node.js pour générer la configuration locale. Depuis la racine :

```sh
npm run docker:init     # Génère les secrets ; complète auth/pgAdmin sans remplacer les réglages existants
npm run docker:up       # Démarre web, API, PostgreSQL, migrations, workers, Mailpit et pgAdmin
npm run docker:api      # Mode API sur Windows : stack et worker Stake local
npm run docker:logs
```

Ouvrir [l’application](http://127.0.0.1:8080) et [la documentation API](http://127.0.0.1:8080/api/docs). Le frontend reste en `mock`. Le worker suit les planifications persistées en base : catalogue chaque jour à 04:00, dernière année Oracle toutes les six heures et historique Oracle le dimanche à 03:00, en heure de Paris par défaut. Les premiers imports démarrent à leur prochaine échéance ou via **Gestion → Scripts → Lancer**. Les états source restent accessibles sur `/api/v1/sources/lol-esports` et `/api/v1/sources/oracles-elixir`.

`npm run docker:down` arrête l’application **en conservant les volumes**. Ne pas ajouter `-v` pour un arrêt normal. Les secrets sont exclus de Git et des images. PostgreSQL n’expose aucun port dans la configuration standard.

Le [guide backend et exploitation](docs/backend.md) détaille la collecte manuelle, l’import du catalogue, le développement, les sauvegardes et les limites avant un déploiement public.

Le [guide de déploiement de production](docs/deployment.md) décrit le VPS, Traefik, Resend, pgAdmin et le workflow GitHub déclenché par les pushes sur `master`.

### Collecte Stake pré-match et en direct

La migration `0013` conserve séparément événements, marchés, sélections, snapshots complets, cotes horodatées et preuves source ; `0016` distingue les phases pré-match et direct et archive les anciens arrêts de collecte dus au début des rencontres. Seuls les marchés de vainqueur de match et de carte ont maintenant un résultat calculé ; aucun autre marché n'est interprété. Les données historiques restaurées le 23 septembre 2026 proviennent du dump local pris avant le retour à `0012` : 20 événements, 260 marchés, 760 sélections, 227 snapshots et 14 160 relevés. Elles ne prouvent pas l’état actuel des offres.

Le worker Stake utilise Chrome Stable avec interface dans la session Windows et un profil dédié. `npm run docker:api` applique `compose.dev.yaml` pour publier PostgreSQL uniquement sur `127.0.0.1`, puis lance le worker local et attend son premier heartbeat. Après un redémarrage de Windows, relancer cette commande dans une session graphique ouverte. Contrôler ou relancer le worker seul avec :

```powershell
npm run stake:status
npm run stake:start
```

Le script `stake-markets` se planifie dans **Gestion → Scripts** ; son cron de référence est `*/20 * * * *` en heure de Paris. Le navigateur lit les marchés des événements dont le pré-match ou le direct est confirmé publiquement. Une sélection affichée mais fermée est conservée avec une cote nulle ; une ancienne cote n'est pas présentée comme ouverte. Un refus bloquant suspend la source selon `Retry-After`. Aucun compte Stake, pari ou paiement n’est utilisé. La cadence de vingt minutes et l'horodatage des relevés ne garantissent pas la disponibilité d'une cote au moment d'une consultation. Voir [le guide du collecteur](docs/stake-collector.md) pour les commandes, la base et les limites.

L'historique Admin classe un passage ayant publié au moins un snapshot « Terminée » ; les rencontres non publiées et un éventuel arrêt ultérieur restent signalés comme couverture incomplète avec leurs raisons. Une erreur sans aucune publication reste « Échec ». La migration `0019` corrige les anciens faux échecs ayant effectivement persisté des cotes ; elle garde leur ancien diagnostic et indique que les raisons détaillées n'étaient pas conservées. Les duels de joueurs portant le même titre sont identifiés par leur paire de joueurs lorsque Stake ne fournit pas d'identifiant de marché ; une ambiguïté persistante conserve le relevé antérieur sans créer de cote nouvelle.

Sur le VPS Linux, un challenge Cloudflare du document principal peut empêcher toute collecte même lorsque Chrome et le worker sont sains. Le collecteur conserve alors les dernières données valides et respecte un éventuel `Retry-After` explicite. Un cycle VPS du 24 septembre 2026 a ensuite collecté 13 rencontres et 704 cotes ; cet accès ponctuel ne garantit pas les suivants. Le [constat du 24 septembre 2026](docs/incidents/2026-09-24-stake-vps.md) distingue les faits vérifiés des causes encore inconnues et décrit les informations nécessaires à une demande d'accès officielle.

Le service Docker `settlement-worker` conclut en base les seules sélections historiques **Vainqueur du match** et **Vainqueur de la carte N**. Il vérifie le lien Stake ↔ rencontre, privilégie LoLTV puis Oracle’s Elixir, et attend 30 minutes après la première observation durable d’un résultat final cohérent. Une carte non jouée est annulée ; un résultat contradictoire reste en cours. Les corrections sont journalisées. Aucun pari placé ni mise n’est créé. Voir [les règles et limites de règlement](docs/selection-results.md).

### Matchs live et à venir

Une modale ouverte reçoit les actualisations de l’API sans F5, en conservant la carte consultée, le poste et le défilement. Les valeurs modifiées visibles reçoivent un fond discret qui disparaît en 1,2 seconde ; les données hors écran ou masquées ne rejouent pas l’effet lorsqu’on les révèle. Aucun effet à l’ouverture, au changement de carte ni sur le vieillissement du relevé ; réduction des mouvements respectée. Une panne transitoire conserve les dernières données, affiche un état de reprise et réessaie après au moins trente secondes, en respectant `Retry-After`. Le retour dans un onglet périmé relit l’API.

Le changement de carte conserve le panneau, les images déjà chargées et la position de lecture ; le fond de sélection tient compte du défilement de la modale. La victoire apparaît par une petite coche sur le logo. Le camp utilise une barre latérale fine et arrondie, à gauche ou à droite selon le bloc d’équipe : bleue ou rouge selon la carte, neutre si le camp est inconnu. Le nom reste accessible au survol, au focus et aux technologies d’assistance ; la couleur évolue sans déplacer la barre. Un service partagé de continuité couvre le document et les régions défilantes consultées : lors d’un raccourcissement, la position reste inchangée si elle est encore valide, sinon l’espace provisoire et le défilement diminuent ensemble en 300–560 ms. Les gestes de défilement suspendent cette correction ; aucune animation si les mouvements sont réduits. Ce service ne détourne pas les navigations explicites ni le scroll horizontal.

La durée est celle du relevé LoLTV, avec déduction des pauses publiées. Un zéro effectivement observé reste `0:00` ; il se distingue du zéro de remplissage du HTML. Aucun chronomètre local n’invente du temps entre deux relevés. En mode mock uniquement, `?view=matches&mock=live-updates` permet de vérifier les changements périodiques, une erreur 503 suivie d’une reprise et le passage à la carte suivante avec des données fictives.

La vue Matchs regroupe un calendrier compact, les ligues présentes dans la journée et des filtres de statut avec compteurs. Les directs précèdent les rencontres à venir et les résultats ; les accordéons sont initialement fermés, conservent leur ouverture par journée et s’ouvrent lors du choix explicite « En direct ». La recherche et les filtres locaux sont immédiats. Le skeleton de 1,2 seconde reste appliqué à l’entrée, au changement de journée et à l’actualisation manuelle, avec hauteur réservée ; les actualisations périodiques conservent le contenu.

Le détail conserve le score de série dans son en-tête et les cartes accessibles au défilement. Les onglets résument vainqueur et durée lorsqu’ils sont publiés ; chaque carte porte son propre horodatage. Le sélecteur est masqué lorsqu’il n’y a qu’une option, sans inférer le format. Les filtres de statut et de poste gardent des dimensions et une graisse stables, avec le fond de sélection animé commun à l’application. Les postes utilisent leurs icônes locales sourcées, avec noms accessibles et infobulles. Victoire et défaite sont indiquées discrètement sur les logos de la liste. L’écart d’or exige deux compositions complètes. Les bans restent des portraits ronds seuls. Le répertoire des ligues est organisé par présence dans la journée et région sourcée. Le contrat ne fournit actuellement ni parenté fiable entre chaque compétition et phase, ni lien officiel de diffusion : aucune relation ou URL n’est déduite des noms.

**LoLTV** fournit le calendrier et les détails de la fenêtre J−7/J+7 de Paris. Le worker scrape les documents HTML publics, leur JSON SSR embarqué et le flux de consultation anonyme utilisé par les fiches. L’action de session est découverte dans le JavaScript public lié ; aucun compte ni jeton utilisateur n’est nécessaire. LoL Esports conserve le rôle de référentiel officiel ; Oracle’s Elixir apporte les historiques complets rapprochés sans ambiguïté.

```sh
npm run data:loltv:sync
# ou
docker compose --env-file .env.docker run --rm --no-deps worker metiquo-worker sync-loltv-matches
```

Le script `loltv-matches` est planifié chaque minute. Les pauses entre lectures sont de 2 à 4 secondes ; le calendrier et les directs deviennent relisibles après une minute, les résultats après cinq minutes. Une file persistante poursuit la pagination et les détails dus entre passages bornés à 90 secondes, sans supprimer les éléments non traités. Les plafonds partagés sont 120 actions explicites et 600 requêtes naturelles Chromium par fenêtre de dix minutes. Les cartes terminées déjà acquises ne sont pas rouvertes avant leur échéance de correction (six heures). Les valeurs et limites sont décrites dans [le guide des collecteurs](docs/collectors.md).

Le premier 403/429 arrête le cycle, conserve ses preuves et impose un délai persistant d’au moins quinze minutes, progressif et prolongé par `Retry-After`. Les cookies anonymes restent seulement dans le client HTTP du cycle ; ils ne sont ni stockés en base ni journalisés. Le mode DOM Chromium est optionnel et désactivé par défaut. Aucun proxy tournant, changement d’identité ou mécanisme de contournement n’est ajouté.

La migration **0012** désactive l’ancien collecteur et ajoute LoLTV sans effacer les relevés historiques. Les anciennes observations ne sont plus exposées comme données courantes. `/api/v1/matches` publie les observations utilisables ; `/api/v1/sources/loltv` expose l’état source. Les bans, camps et statistiques manquants restent inconnus. Les zéros des enregistrements d’attente ne sont jamais considérés comme des mesures.

**Validation externe du 21 septembre :** les listes HTML et les fiches sont accessibles. Le parcours anonyme normal du site fournit les dix joueurs et les camps depuis le worker ; les bans ne sont pas présents dans tous les flux. Chromium a reçu un 403 lors du diagnostic initial et n’est pas utilisé dans le parcours par défaut. Voir [les vérifications](docs/verification.md) et [l’analyse des pages LoLTV](docs/loltv.md).

Le live vise une lecture toutes les **30 secondes** avec la planification continue par minute, sans attendre le tick cron suivant. Les sessions anonymes sont réutilisées en mémoire par rencontre pendant cinq minutes au maximum et dans leur durée de validité. Le budget reste **120 requêtes par dix minutes**, avec **2–4 secondes** entre requêtes ; la cadence ralentit selon le nombre de directs. Le navigateur consulte notre API toutes les quinze secondes lorsqu’un match est live. Ces délais s’ajoutent à la fraîcheur des données publiées par LoLTV, sans garantie de temps réel absolu. Voir [les réglages du collecteur](docs/collectors.md).

### Espace Admin

Connectez-vous par code email avec `metiquo@admin.fr` (email visible dans Mailpit en local). **Gestion** apparaît uniquement pour un compte administrateur, avec les entrées **Utilisateurs** et **Scripts**. Les liens `?view=users` et `?view=admin` sont conservés après rechargement ; les routes `/api/v1/admin/*` vérifient aussi le rôle et la session côté serveur, même en mode esport mock.

- **Utilisateurs** : recherche et pagination, changement de rôle, suspension/réactivation et déconnexion des sessions. Une modification du rôle ou du statut révoque les sessions. Votre propre accès administrateur et le dernier administrateur actif sont protégés.
- **Scripts** : un titre et son compteur, puis une barre dépliable pour l’état des services et leurs journaux. Six scripts autorisés, regroupés sous des titres de familles toujours visibles, avec échéances et statuts alignés. Un seul détail s’ouvre à la fois : accès à l’historique et à la planification, lancement manuel dans le menu « … ». Trois lignes de services distinguent les collectes sportives, les cotes Stake et les résultats des sélections. Leurs journaux structurés se consultent depuis la ligne du service ou une exécution précise, avec incidents, filtres et suivi du direct. Les lignes sont conservées quatorze jours à partir de la migration `0020` ; les exécutions antérieures gardent leur résumé mais n’ont pas de journal reconstitué. Sur téléphone, la prochaine échéance et l’état sont visibles ; la cadence se lit dans le détail. Le journal reprend les dialogues de l’app, avec filtres intégrés et événements dépliables pour consulter leur contexte. Le formulaire propose des fréquences simples ou un cron numérique à cinq champs ; il prévisualise trois dates en heure de Paris ou UTC.
- Les horaires sont enregistrés dans PostgreSQL et pris en compte sans reconstruire les services. La migration `0004` conserve les comptes et données existants. `npm run docker:up` reconstruit les services locaux et applique cette migration.
- La file est vérifiée toutes les cinq secondes, chaque source possède sa file indépendante. Un lancement en attente ne signifie pas que la collecte a commencé. Une interruption est visible et ne déclenche pas de reprise automatique ; relancer manuellement ou attendre le prochain cron. Une indisponibilité prolongée regroupe les échéances manquées en une collecte par script.
- Les variables `METIQUO_CATALOG_ENABLED` et `METIQUO_ORACLE_ENABLED` gardent leur rôle d’interrupteur du worker. Les anciennes variables d’intervalle en secondes ne pilotent plus `serve` : utilisez les planifications Admin. Aucune commande shell ni nouveau script arbitraire ne peut être créé depuis l’interface.

La gestion réelle passe toujours par l’API ; MSW ne simule aucun utilisateur, script ou statut. L’historique Admin commence à l’activation de cette fonctionnalité ; les anciennes exécutions CLI restent consultables dans les endpoints source. Les actions d’administration sont consignées dans `admin_audit` sans codes ni jetons. Voir [le guide d’administration](docs/administration.md).

## Administration PostgreSQL avec pgAdmin

Ouvrir [pgAdmin](http://127.0.0.1:5050). Le compte initial est `admin@metiquo.fr` ; son mot de passe est `PGADMIN_DEFAULT_PASSWORD` dans `.env.docker`. Ce compte est indépendant de celui de l’application Metiquo.

Dans **Metiquo → Metiquo — PostgreSQL**, saisir `POSTGRES_PASSWORD` du même fichier : la connexion est déjà préconfigurée vers `db:5432`, base `metiquo`, utilisateur administrateur `metiquo`. Les mots de passe restent dans la configuration locale ignorée par Git. Le volume `pgadmin_data` conserve les comptes, connexions et préférences après redémarrage. Voir [les réglages et l’accès à la base](docs/backend.md#pgadmin-et-accès-à-postgresql).

## Inscription et connexion sans mot de passe

1. Cliquer sur **Se connecter**, puis saisir une adresse email dans la modale.
2. Ouvrir [Mailpit](http://127.0.0.1:8025) et copier le code à six chiffres du dernier email.
3. Saisir ou coller le code dans la fenêtre de Metiquo qui l’a demandé : le sixième chiffre déclenche une unique vérification. Le bouton reste disponible pour une reprise manuelle. Le compte est créé à la première validation.
4. **Mon profil** affiche l’email vérifié, le rôle et la date de création ; **Se déconnecter** révoque la session côté serveur.

La migration Alembic `0005` attribue **admin** à `metiquo@admin.fr` et **user** à `metiquo@user.fr`, en créant si nécessaire ces deux comptes explicitement demandés. Elle préserve identité, vérification email et suspension, et révoque les sessions des comptes dont le rôle change. Le compte historique `admin@metiquo.fr` reste inchangé. Ces comptes doivent toujours valider un code email pour se connecter ; les inscriptions ordinaires sont créées après vérification avec le rôle `user`.

Mailpit capture les emails localement : ils ne sont pas livrés dans de vraies boîtes mail. Son interface écoute sur `127.0.0.1:8025`, son SMTP reste dans le réseau Docker standard. Les messages, conservés en mémoire, disparaissent à la recréation du conteneur et sont limités à 500 / 24 heures. Pour un vrai fournisseur, configurer le SMTP avec TLS et ses identifiants ; voir [le guide d’authentification](docs/authentication.md).

Codes à usage unique valables 10 minutes, cinq essais maximum, renvoi après 60 secondes et limites persistantes par email/IP. Sessions opaques révocables en cookie HttpOnly, expirant après 7 jours sans activité ou 30 jours au maximum. Aucun token n’est stocké dans localStorage.

La validation s’affiche directement sous le champ email ou code, dans un espace réservé : aide, erreur et confirmation se remplacent sans déplacer la modale ni les boutons. Les champs vides ou incomplets sont vérifiés avant tout appel API, sans bulle native du navigateur ; les transitions respectent la préférence de réduction des animations.

## Démarrage

Node.js **22.12+** (ou 24+) et npm. Depuis la racine du dépôt :

```sh
npm install
npm run dev:mock       # frontend mocké + API réelle pour l’authentification
# npm run dev:api      # frontend branché sur les données FastAPI
```

Ouvrir <http://127.0.0.1:5173>. Le port est fixe : Vite signale s’il est déjà occupé. Le serveur écoute uniquement en local.

L’authentification nécessite la stack Docker démarrée : Vite transmet `/api` à `127.0.0.1:8080`. Les fixtures esport fonctionnent seules, mais une API absente produit une erreur explicite dans la modale. Pour un backend Python local ou un port personnalisé, voir [authentication.md](docs/authentication.md).

```sh
npm run check        # Frontend + backend ; installer uv puis exécuter uv sync auparavant
npm run build:mock   # build avec MSW pour les données esport
npm run build:api    # build avec les endpoints de données FastAPI
npm run preview      # Production locale sur http://127.0.0.1:4173
npx playwright install chromium # navigateur requis la première fois
npm run test:e2e --workspace @metiquo/web # smoke Chromium sur le build mock
npm run format
npm run format:check
```

Les deux modes frontend sont sélectionnés explicitement avec `mock` ou `api`. Dans les deux modes, `/api/v1/auth` reste l’API réelle.

### Docker

Initialiser les secrets locaux puis démarrer la stack avec le frontend souhaité :

```sh
npm run docker:mock    # MSW pour les données esport, API réelle pour l’authentification
npm run docker:api     # données esport servies par FastAPI
npm run docker:down
```

Les scripts utilisent respectivement `compose.mock.yaml` et `compose.api.yaml`. Changer de mode reconstruit l’image web ; les volumes PostgreSQL, artefacts et pgAdmin sont conservés.
Pour consulter les rencontres réellement collectées sur LoLTV, lancer `npm run docker:api` : une API active derrière un frontend construit en `mock` ne change pas les matchs affichés. Le calendrier montre toujours J−7 à J+7, mais laisse désactivées les journées sans rencontre publiée. La pagination LoLTV peut servir un cache ancien ; le worker refuse ces listes périmées et conserve les données déjà acquises. Les captures vérifiées sont déclarées dans un manifeste et servent uniquement à découvrir des fiches à relire. La fenêtre courante se décale par date et fonctionne aussi en novembre ; pour un démarrage neuf en cas de pagination périmée, une capture couvrant les dates manquantes reste nécessaire. Voir [les limites de couverture](docs/loltv.md).

## Stack retenue

| Outil                                   | Rôle et choix                                                                                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| React 19.3 + TypeScript 6.0             | Composants typés, écosystème mature. TypeScript 6 est retenu pour rester dans la plage officiellement supportée par typescript-eslint, sans forcer les peer dependencies. |
| Vite 8.3                                | SPA rapide à développer et à compiler, sans serveur de rendu superflu.                                                                                                    |
| Tailwind CSS 4 + tokens CSS             | Utilitaires et design system sur mesure. Toutes les surfaces et couleurs possèdent une variante claire et sombre.                                                         |
| TanStack Query 5                        | Cache HTTP, annulation, chargements, erreurs et nouvelles tentatives.                                                                                                     |
| MSW 2 + Zod 4                           | Interception HTTP en mode mock et validation des contrats. L’API utilise les mêmes contrats ; la bascule de données ne demande pas de réécrire les composants.            |
| Radix UI                                | Dialogues et sélecteurs accessibles : focus, clavier, Escape.                                                                                                             |
| Motion 13                               | Transitions discrètes et respect du réglage de réduction des animations.                                                                                                  |
| Lucide                                  | Icônes SVG cohérentes, sans emoji dépendant de l’OS.                                                                                                                      |
| Inter Variable + Manrope Variable       | Typographie locale ; aucune requête Google Fonts.                                                                                                                         |
| Vitest + Playwright + ESLint + Prettier | Tests unitaires et smoke navigateur Chromium, règles de code et formatage.                                                                                                |
| Pillow                                  | Validation et conversion des logos officiels en WebP dans le worker Python.                                                                                               |
| Python 3.13 + uv                        | Workspace backend typé, dépendances verrouillées séparément du frontend.                                                                                                  |
| croniter + tzdata                       | Validation des crons, calcul des échéances et fuseaux horaires, partagés entre API et worker.                                                                             |
| FastAPI + Pydantic                      | API de données, authentification par email et validation des contrats.                                                                                                    |
| Mailpit + SMTP Python                   | Emails locaux ; transport SMTP remplaçable sans modifier le frontend.                                                                                                     |
| PostgreSQL 18 + SQLAlchemy + Alembic    | Persistance, transactions, import en flux et migrations versionnées.                                                                                                      |
| Patchright + HTTPX                      | Export Drive groupé dans le worker, puis téléchargement HTTP en flux.                                                                                                     |
| Docker Compose + Nginx                  | Services séparés, volumes persistants, proxy sur la même origine et sondes de santé.                                                                                      |

Les versions exactes installées sont dans `package-lock.json`. Le bundle des mocks est chargé séparément. Les panneaux font partie du chargement initial : leur ouverture ne dépend pas du téléchargement d’un module. Aucun routeur ou store global n’est nécessaire pour cet écran unique.

## Structure

```text
apps/
  api/src/metiquo_api/       # API et authentification réelle, sans navigateur
  worker/src/metiquo_worker/ # Catalogue LoL, logos, Oracle et collecte Stake pré-match/direct
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
      hooks/               # Thème, URL et présentation des chargements
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

Le format absent reste `null` (migration `0011`). Les correspondances entre fournisseurs reposent sur les identifiants et alias sourcés, la compétition et l’horaire vérifié. Un cas ambigu reste séparé. `METIQUO_ORACLE_DATE_TIMEZONE` reste vide tant que son fuseau n’est pas confirmé ; sans fuseau, un rapprochement nécessite une correspondance exacte des dix champions/rôles/KDA, du vainqueur et du numéro de carte déjà observés par LoLTV.

Le snapshot frontend du 14 septembre 2026 contient **35 compétitions, 262 équipes, 297 fichiers de logos**, issus des pages publiques LoL Esports. La collecte backend du 15 septembre a publié **35 ligues, 262 équipes et 295 URLs de logos distinctes** ; les deux décomptes d’images diffèrent car certaines identités partagent une URL. Les six ligues majeures et la LFL sont présentes ; les sources comprennent les ERL, les circuits Challengers et les événements internationaux. Le TFT est exclu.

Ce snapshot couvre le catalogue et les rencontres exposés par Riot à la date de collecte, **pas toutes les compétitions amateurs mondiales**. Les affiliations secondaires sont inférées des rencontres domestiques visibles ; elles ne constituent pas un registre de contrats ou de rosters actifs. Certaines compétitions internationales n’ont volontairement aucune équipe affectée comme ligue d’origine. Le modèle utilise des identifiants ouverts, sans enum de ligues ou de teams : tout nouveau circuit peut être ajouté.

**34 opportunités sur 30 compétitions sont fictives.** Le scénario est fixé aux 14–15 septembre 2026, en heure de Paris. Les rencontres, formats, horaires, probabilités, cotes, historiques et mentions de bookmakers illustrent le produit ; ils ne décrivent aucune offre réelle. Aucun pari, paiement ou modèle prédictif n’est connecté. L’authentification email est réelle et indépendante de ces fixtures.

Les [sources et droits des assets](docs/data-sources.md) sont documentés. Après démarrage de Docker, les deux collectes backend se lancent depuis la racine :

```sh
npm run data:lol:sync
npm run data:oracle:sync
```

`data:lol:sync` collecte les identités et logos, puis les publie ensemble en base ; il n’écrit pas dans le frontend. `data:oracle:sync` traite toutes les années découvertes. Les noms Python sont `uv run metiquo-worker sync-lol-catalog` et `uv run metiquo-worker sync-oracles-elixir` (connexion PostgreSQL requise). Oracle accepte `--latest` ou `--years 2026`. Les anciens noms `npm run catalog:sync` et `metiquo-worker collect` restent des alias ; les anciens scripts Node qui réécrivaient les fixtures ont été retirés.

La planification intégrée utilise les mêmes fonctions et des verrous PostgreSQL propres à chaque source. Un échec préserve la version active ; la prochaine exécution planifiée ou un lancement manuel permet de réessayer. Voir le [guide des collecteurs](docs/collectors.md) pour les paramètres, les commandes sous PowerShell et l’utilisation avec cron. Aucune modification de l’UI/UX ni bascule en mode API n’est effectuée par ces commandes.

### Audit Oracle’s Elixir

L’[audit du 15 septembre 2026](docs/oracles-elixir-audit.md) a validé la récupération des **13 CSV Oracle’s Elixir (2014–2026)** par téléchargement groupé en ZIP, malgré le quota bloquant les liens individuels. L’archive complète contenait 848,6 Mo de CSV et 1 223 472 lignes vérifiées. Les scripts temporaires de cet audit ont été supprimés. À la demande suivante, cette méthode a été implémentée dans le worker permanent, avec validation, empreintes SHA-256 et import atomique. Le mode API peut projeter les cartes Oracle uniquement après rapprochement non ambigu et preuve d’identité et format sourcé. Cette voie dépend toujours du service Google ; elle n’offre pas de garantie absolue de disponibilité.

### Audit documentaire Stake

L’[audit du 22 septembre 2026](docs/stake-audit.md) documente le DOM esport/LoL, les positions responsive, 17 rencontres listées, sept fiches et 204 sélections distinctes (174 cotées, 30 désactivées), avec captures, JSON, CSV et empreintes. Le scraper Patchright existant a reçu un HTTP 403 ; le navigateur accessible a ensuite été limité par une page Cloudflare 1015. La couverture globale reste donc partielle, explicitement détaillée dans le rapport. Cet audit ponctuel était documentaire ; le collecteur et la base rétablis le 23 septembre sont décrits dans [leur guide](docs/stake-collector.md).

### Rapprochement des rencontres Stake / LoLTV / Oracle

Le [mécanisme backend](docs/match-reconciliation.md) est précédé d’un [audit des données réelles](docs/audits/matching/2026-09-23/audit.md). La migration `0015` conserve les observations et décisions. Le premier lien exige deux équipes, un tournoi compatible et un horaire actuel ou antérieur observé à 30 minutes près, avec un candidat unique. Une fois ce lien démontré, un report même d’un jour ne le rompt pas à lui seul : l’identité sportive et les éventuelles revanches restent contrôlées. Les événements en attente sont réévalués à l’arrivée des sources. Les alias difficiles sont des données sourcées et limitées au tournoi, sans exceptions nominatives dans le résolveur. Aucun changement frontend, aucune value ni interprétation des marchés.

Après configuration de `METIQUO_DATABASE_URL`, `uv run --frozen metiquo-worker reconcile-matches --dry-run` produit un diagnostic sans écriture ; sans `--dry-run`, la commande reprend les liens de tout le stock sans collecte réseau. Le rapprochement utilise aussi les codes d'équipe du catalogue sourcé et peut démontrer une variante directement sur une rencontre unique : même édition, horaire vérifié, identités sportives et source LoLTV, sans alias global déduit. Une variante encore insuffisamment prouvée reste en attente. `import-match-aliases <fichier.json>` importe les équivalences auditées d'équipes (`aliases`) et de compétitions (`competition_aliases`) ; `revoke-match-alias <empreinte>` les révoque en réévaluant les liens. Les deux types utilisent les mêmes champs et preuves : pour une compétition, `name` est le nom Stake et `target_id` est le `competitionSourceId` LoLTV. L'alias reste limité à `competition_key` et à `valid_from` / `valid_until`. Les commandes, le SQL, la portée Oracle et les limites sont détaillés dans le guide. Aucune nouvelle variable ou dépendance.

## Vérification des états mock

- `/?mock=slow` : requête de 3 secondes pour observer la sortie du splash vers les skeletons et le spinner fixe ; les champs restent utilisables pendant l’attente.
- `/?mock=empty` : aucune opportunité.
- `/?mock=error` : erreur initiale et sa tentative automatique, puis réussite au clic sur « Réessayer ».

Ces paramètres concernent seulement MSW et ne sont pas actifs en mode API. Les données normales reviennent à `/`.

Le thème suit le système tant qu’aucun choix n’a été effectué. Un changement manuel est persisté et appliqué avant le premier rendu. Aucune session utilisateur n’est simulée.

## Chargements et transitions

L’identité Metiquo fournie le 16 septembre est intégrée à la sidebar, à la navigation mobile, au fil d’Ariane, aux pages d’erreur et au splash. Les sources sont dans `assets/brand`, les exports servis dans `apps/web/public/brand` (séparés des logos esport). WebP sans perte avec repli PNG, `srcset` et dimensions réservées ; variantes de thème sans changement de taille. Les icônes ICO et Apple PNG suivent aussi la préférence explicite dès le démarrage. Le [guide de l’identité](assets/brand/README.md) décrit les formats, les empreintes et l’archive locale du pack.

Les résultats de Matchs, Values, Performance et de l’administration ont un skeleton de **1,2 seconde minimum**, y compris après une navigation en cache, un changement de date, filtre, recherche, tri ou page. `useMinimumLoading` gère uniquement la présentation : les appels démarrent immédiatement et un réseau lent prolonge le skeleton jusqu’à disponibilité. Une nouvelle sélection remplace le délai précédent ; ses anciennes données ne sont pas affichées. Les erreurs restent prioritaires. Aucun délai ni rejeu ajouté aux écritures d’authentification ou d’administration. Les actualisations périodiques de Matchs/Scripts gardent le contenu disponible.

Les skeletons partagent les grilles des lignes finales ; Performance réserve les axes, le curseur, l’inspection et les indicateurs. Les sélections de navigation, ligue, date et période possèdent une surface animée commune. Le contenu apparaît par fondu et légère translation ; le graphique se trace progressivement, avec déplacement amorti du marqueur. Les points restent ceux du calcul, sans lissage qui inventerait des gains. `prefers-reduced-motion` supprime les mouvements et le scintillement, sans changer le délai de lecture. Aucun rechargement lors d’un changement de thème.

Les favoris ont été retirés à la demande produit du 16 septembre 2026, y compris les boutons et la logique de stockage. L’ancienne clé locale n’est plus lue ni écrite ; une ancienne URL `view=favorites` affiche la page de lien inconnu avec retour explicite.

## Interface et stabilité visuelle

- Même interface en modes mock et API, sans badges de démonstration (décision produit du 15 septembre 2026). Les fixtures restent fictives et identifiées comme telles dans cette documentation.
- Splash constitué du symbole Metiquo et d’un petit spinner, avec styles critiques intégrés au HTML. Le thème est appliqué avant la première image. L’attente des données est limitée à 700 ms ; ensuite l’interface apparaît par fondu avec des skeletons si nécessaire. L’attente indépendante des polices reste bornée à deux secondes. Une API lente ne bloque donc plus tout l’écran jusqu’au timeout HTTP.
- Inter et Manrope sont préchargées depuis `public/fonts`. Un délai de deux secondes borne l’attente des polices ; en cas d’échec ou de délai dépassé, la police système reste utilisée pour toute la page, sans remplacement tardif. `font-display: optional` complète cette protection. Le catalogue et les opportunités sont préchargés via les mêmes requêtes validées et le même cache que l’écran.
- Les erreurs de données restent visibles avec une nouvelle tentative manuelle. Un appel HTTP est limité à 20 secondes. Les statuts, délais serveur et actions de reprise sont détaillés dans [le guide des erreurs](docs/error-handling.md). Le spinner d’actualisation est fixe, en bas à droite, avec un nom accessible et sans texte de chargement visible.
- Dialogues et panneaux Radix conservés pendant leur animation de fermeture, puis démontés par Radix. Animations d’opacité et de transform, sans flou sur toute la page. Gouttière de scrollbar réservée et absence de double compensation lors des verrouillages imbriqués.
- Jusqu’à 680 px de large, tous les dialogues et la navigation s’ouvrent en bottom sheet. La poignée tactile de 44 px s’élargit et scintille discrètement pendant la prise ; un balayage franc vers le bas ferme la feuille en un geste, sans arrêt à mi-hauteur. Si le doigt repart vers le haut avant le relâchement, même légèrement, la feuille se rouvre entièrement. Un mouvement court la ramène aussi en place et le défilement du contenu reste indépendant. Escape, le bouton Fermer et le retour du focus sont conservés. L’ouverture d’un formulaire mobile cible la poignée pour éviter d’afficher le clavier avant le choix du champ. Au-delà de 680 px, les dialogues restent centrés. La préférence de réduction des mouvements supprime les animations de la feuille, de la poignée et du fond.
- Tous les contenus dépliables (Matchs, Scripts, « Cotes & résultats », historiques de cotes et d’exécutions, détail de Performance) partagent la même transition de hauteur à l’ouverture et à la fermeture, désactivée quand les mouvements sont réduits. Le dialogue de match garde sa hauteur pendant le dépliage des cotes ; les gouttières des zones défilantes sont réservées, et un panneau ouvert s’adapte à un changement de largeur sans couper son contenu. Le détail de Performance utilise le défilement de la page plutôt qu’une scrollbar intérieure. Quand une ligne Matchs dispose de moins de 900 px dans son accordéon, elle montre seulement les emblèmes d’équipes ; le nom complet reste dans le nom accessible du bouton de rencontre.
- Le catalogue API réutilise les logos Riot locaux pour les équipes LoLTV dont le nom est identique et unique, ou suit les variantes de nom visuelles documentées dans `packages/core/src/metiquo_core/catalog_logos.py`. Il ne fusionne jamais leurs identifiants ou affiliations. Le worker versionne ces réemplois et le nombre de logos manquants à chaque `npm run data:lol:sync`. Une image officielle Riot déjà sourcée peut servir directement jusqu’à sa mise en cache locale ; les autres absences restent en repli générique. Voir [les sources et limites](docs/data-sources.md).
- Les styles communs se trouvent dans `styles/interactions.css`. Ne pas réintroduire de padding nul pour les boutons à fond survolé, de fallback de chargement dans le flux, ou de montage conditionnel coupant la fermeture d’un dialogue.
- Sélecteur de jeux : League of Legends disponible ; Counter-Strike 2 et Dota 2 réellement désactivés, avec la mention « À venir » et les logos officiels locaux.
- Dans les fixtures frontend, la cote affichée, la value, les tris et la courbe reposent sur le dernier relevé fictif attribué à Stake. Un premier relevé isolé est valide. Le graphique utilise les dates pour l’axe horizontal et des paliers entre les relevés, sans inventer une évolution intermédiaire. Les relevés réels restaurés restent séparés de ces fixtures.

## Navigation, mobile et suivi

- L’URL sans `view` ouvre Matchs ; `view=values` ouvre Les values. L’URL conserve la ligue et l’équipe par identifiant (`league`, `team`), le marché (`market`), le seuil (`min`), la recherche (`q`), le tri (`sort`), la page (`page`) et le détail (`detail`). F5 et précédent/suivant restaurent ce contexte. La saisie remplace l’entrée courante de l’historique pour éviter une entrée par caractère. Les paramètres externes, dont les scénarios MSW, sont préservés. Un détail absent présente un état indisponible avec retour aux résultats.
- La pagination replace le focus et la lecture sur le titre des résultats. Sur mobile : introduction compacte, cibles de boutons d’au moins 44 × 44 px, probabilité visible et action « Détail » explicite. Les skeletons réservent les mêmes trois rangées que les cartes.
- Le catalogue recherche sans tenir compte des accents, de la casse ou des espaces périphériques. Les régions sont traduites avec un repli ouvert pour les futures régions. Choisir une équipe filtre ses opportunités par identifiant, sur les deux côtés de la rencontre.
- L’historique propose tout le suivi, les dernières 24 heures ou les 7 derniers jours, en prenant le dernier relevé comme fin de période. Les points se sélectionnent sur la courbe ou au clavier via le curseur et les boutons précédent/suivant. Le tableau affiche la même période, avec les variations par rapport au relevé précédent, même situé hors période. Le panneau comporte une seule zone de défilement, avec en-tête et pied fixes.
- La liste expose des rôles de tableau, lignes, colonnes et cellules, avec libellés des chiffres. L’en-tête Value n’affiche plus d’icône suggérant un bouton ; le tri reste dans son sélecteur. L’encart d’aide annonce explicitement le calcul expliqué.

Les vérifications et leurs limites sont consignées dans [docs/verification.md](docs/verification.md). Le collecteur Stake réel alimente les tables `bookmaker_*` ; aucun modèle d’estimation ni calcul de value réel n’est rétabli. Les anciens tableaux d’offres multi-bookmakers ne sont plus acceptés.
