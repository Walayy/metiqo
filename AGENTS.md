# Metiquo — instructions du projet

## Présentation

Metiquo est une application d’analyse des values sur les marchés esport. Le premier jeu pris en charge est League of Legends. Le nom du dossier historique est `metiqo`, la marque affichée est **Metiquo**. Les données esport du frontend restent en mode mock, avec un backend réel, PostgreSQL, un worker Oracle’s Elixir et Docker. À la demande produit du 15 septembre 2026, le frontend et le backend intègrent une authentification réelle par code email à six chiffres, sans mot de passe, dans une modale sans route dédiée. Mailpit capture les emails en local ; `admin@metiquo.fr` est provisionné administrateur, les inscriptions ordinaires sont des comptes utilisateur.

La demande suivante du 15 septembre 2026 autorise les commandes backend `sync-lol-catalog` (référentiel et logos versionnés) et `sync-oracles-elixir` (alias historique `collect`), en manuel ou planifiées dans le worker. Le catalogue est actualisé quotidiennement ; Oracle conserve ses cadences de six heures et d’une semaine. Ces collecteurs ne modifient ni l’UI/UX ni les fixtures frontend. Les relations saisonnières et divisions absentes de la source restent inconnues ; une participation ne doit pas devenir une affiliation d’origine supposée.

pgAdmin est intégré à la stack locale à la demande du 15 septembre 2026 : interface sur `127.0.0.1:5050`, connexion PostgreSQL préconfigurée et volume de configuration persistant. Son compte, le rôle SQL administrateur et le compte utilisateur Metiquo sont distincts. Les mots de passe restent dans `.env.docker`, ignoré par Git ; aucune publication du port PostgreSQL dans la stack standard.

La demande produit du 16 septembre 2026 ajoute un espace Admin réel, visible uniquement pour les administrateurs : gestion des rôles et suspensions, révocation des sessions, planifications cron et lancements manuels des collecteurs autorisés. Les planifications sont persistées en PostgreSQL (quotidienne, toutes les six heures et hebdomadaire par défaut), modifiables en heure de Paris ou UTC. Le worker exécute une file durable ; aucune commande arbitraire n’est acceptée. La sidebar ne présente plus les compétitions ni les encarts pédagogiques ; les raccourcis de ligues du contenu portent leurs logos sourcés.

La demande UI du 16 septembre 2026 organise la sidebar en **ESPORT** (Matchs), **ANALYSE** (Les values, Performance), **SOUTENIR METIQUO** (Faire un don, Parrainage Stake), puis **GESTION** (Utilisateurs, Scripts & planifications) réservée aux administrateurs. Les matchs sont affichés par journée de Paris dans une fenêtre J−7 à J+7. La saisie ou le collage du sixième chiffre du code déclenche une seule validation ; aucune écriture n’est relancée automatiquement après erreur.

La demande produit suivante du 16 septembre 2026 remplace explicitement les règles précédentes de ces vues : Matchs présente des accordéons de ligues fermés initialement, sans values ni paris, et une modale de scores, cartes, compositions et statistiques. Les cartes non commencées et journées sans rencontre sont désactivées ; pas de calendrier natif. Performance simule une mise fixe sur les values historiques filtrées, à partir d’une décision pré-match figée et d’un règlement explicite. Le scénario mock peut fournir des résultats, compositions et statistiques fictifs documentés ; l’API réelle n’en invente aucun et conserve un état vide en l’absence d’historique réglé. Les encarts et lignes de values n’affichent plus de date. Les modales de soutien utilisent des liens temporaires vers example.com en mock, annoncés comme temporaires sans transaction, et des URLs HTTPS configurables en mode API. Cette demande autorise les contrats de lecture `/matches` et `/performance` et la configuration des destinations, sans collecteur live, paiement ou pari réel.

La demande produit suivante du 16 septembre 2026 supprime entièrement les favoris : section Suivi, route, boutons, stockage applicatif et mentions dans les autres écrans. Les anciennes URLs de cette vue sont inconnues et présentent la reprise 404. Les régions de données (Matchs, Values, Performance, Utilisateurs et Scripts) affichent un skeleton adapté au composant final pendant au moins 1,2 seconde à l’entrée, au changement de sélection et à l’actualisation manuelle, même en cache. Les requêtes commencent immédiatement ; l’affichage attend aussi leur achèvement. Les contrôles restent réactifs. Le rafraîchissement périodique conserve le contenu déjà prêt. Transitions douces de sélection et de contenu, tracé progressif et curseur amorti pour la simulation ; toutes les animations respectent la réduction des mouvements. Les comptes `metiquo@admin.fr` et `metiquo@user.fr` sont explicitement provisionnés par la migration `0005` avec les rôles `admin` et `user` ; leur connexion exige toujours le code email et la vérification n’est jamais inventée. Ce provisionnement explicite est une exception à la création des inscriptions ordinaires après vérification.

## Périmètre et données

- À la demande produit du 16 septembre 2026, les erreurs réelles ont des écrans de reprise cohérents : liens inconnus, accès, suspension, limites de requêtes et indisponibilités. Respecter `Retry-After` sans relancer automatiquement une écriture ni rediriger silencieusement. Le statut 423 d’un compte n’est révélé qu’après preuve d’accès (code email validé ou session existante) ; la demande initiale de code reste uniforme.

- Ne contredis jamais ce fichier. Faire évoluer ces règles explicitement lorsque le besoin produit évolue.
- Développer la section demandée sans ajouter de pages factices ni de boutons inactifs. Exception produit : le sélecteur de jeux affiche CS2 et Dota 2 désactivés et marqués « À venir ».
- Prévoir toutes les régions, ligues, divisions et équipes via des identifiants stables et un référentiel extensible ; ne pas coder les filtres contre une liste fermée.
- Distinguer les identités sourcées des rencontres, probabilités et cotes fictives dans le README et les sources. À la demande produit du 15 septembre 2026, l’interface est identique en modes mock et API, sans badge ni texte de démonstration. Ne pas qualifier les fixtures de calendrier officiel ni de prédiction réelle.
- Stake est l’unique bookmaker suivi. La cote courante est le dernier relevé horodaté ; l’historique commence à l’enregistrement de la rencontre. Aucune comparaison entre bookmakers.
- Documenter la source, la date de récupération et les limites de couverture du référentiel. Ne pas annoncer une exhaustivité ou une actualité non vérifiées.
- Utiliser les logos officiels sourcés, conservés localement quand possible, avec dimensions réservées et repli accessible. Ne pas recréer de faux logos ou inventer une URL.
- La value est calculée par `(probabilité estimée × cote décimale - 1) × 100`. Les chiffres affichés et tris dérivent des mêmes données. Aucune promesse de rendement.
- Aucun pari, compte bookmaker ou paiement réel dans cette version.

## Architecture et développement

- Monorepo : npm workspaces pour `apps/web` ; workspace Python 3.13 avec uv pour `apps/api` (FastAPI), `apps/worker` (collecteurs) et `packages/core` (domaine et PostgreSQL). Versions verrouillées dans les deux lockfiles.
- API, worker et base cloisonnés. Patchright/Chromium appartient exclusivement au worker. Stake reste un emplacement d’extension désactivé : aucun accès à Stake.bet dans cette livraison. Pas d’authentification simulée ni de probabilités inventées par l’API.
- L’authentification utilise toujours l’API réelle, même lorsque les données esport sont mockées. Créer les utilisateurs après vérification de l’email ; ne jamais exposer les codes ou jetons de session dans les réponses ou logs. Sessions révocables en cookie HttpOnly, codes expirables à usage unique, limites persistantes et contrôle d’origine sur les écritures. Le rôle SQL de l’API écrit seulement les tables et colonnes nécessaires à l’authentification et à l’administration : rôle/statut des comptes, planifications, demandes de lancement et journal d’audit. Il ne modifie ni les résultats d’exécution ni le heartbeat. Le worker n’accède pas aux données d’authentification ni au journal d’audit des administrateurs.
- Versionner le schéma PostgreSQL avec Alembic. Conserver les données source, leur provenance et leur empreinte ; publier les versions actives atomiquement. Les échecs de collecte doivent préserver les dernières données valides et rester observables.
- React, TypeScript strict et Vite. Organisation par feature, composants UI génériques, domaine et accès aux données séparés.
- Les composants ne lisent pas directement les fixtures. HTTP typé + validation Zod + TanStack Query ; MSW intercepte les appels en mode mock. L’adaptateur réel utilise les mêmes contrats.
- Le mode mock est explicite via `VITE_DATA_MODE=mock`. Les valeurs `api` et `mock` sont les seules permises. Ne jamais basculer silencieusement en mock en cas d’erreur API.
- Préférer l’état local aux stores globaux. Aucune dépendance sans usage concret. Verrouiller les versions via le lockfile.
- Imports de types explicites, pas de `any`, pas d’erreurs masquées. Annuler les requêtes abandonnées, gérer chargement, vide, erreur et nouvelle tentative.
- Centraliser formatage français, dates, unités, identifiants et calculs métier. Ne pas stocker de valeurs dérivables.
- Ne pas écraser les fichiers ou modifications utilisateur sans comprendre leur rôle. Ne pas publier ou déployer sans demande.
- Avant livraison : `npm run check`, puis vérification navigateur des parcours modifiés en clair/sombre, mobile/tablette/desktop et au clavier. Tester les calculs et contrats ; éviter les tests qui recopient l’implémentation.

## UI / UX

- Une interface calme, précise, dense sans surcharge. Textes français courts ; chiffres tabulaires ; icônes Lucide cohérentes, pas d’emoji décoratif interchangeable selon l’OS.
- Tokens sémantiques CSS pour chaque couleur, surface, bordure, espacement et rayon. Clair et sombre complets ; contrastes lisibles ; préférence système au premier affichage, préférence explicite persistée ensuite.
- Appliquer le thème avant le premier rendu pour éviter les flashes. Le changement de thème ne doit pas relancer les requêtes ni modifier les dimensions.
- Utiliser Radix pour les dialogues et menus : clavier, focus piégé, Escape, retour du focus, labels et descriptions accessibles.
- État focus-visible net. Zones tactiles d’au moins 44 px sur mobile. Boutons avec type explicite, noms accessibles pour les icônes et état désactivé réel.
- Validation des formulaires : messages français sous les champs, dans un espace réservé qui ne déplace ni les contrôles ni le dialogue. Utiliser le composant de retour de champ partagé ; remplacer les bulles natives par une validation accessible à la soumission, puis pendant la correction. Transitions discrètes sans animation de hauteur.
- Caret uniquement dans les champs éditables. Texte de contenu sélectionnable ; contrôles non sélectionnables. Ne pas désactiver globalement la sélection ni le focus.
- Réserver les dimensions des images et skeletons. Skeletons correspondant au composant final, annoncés via `aria-busy`, animation discrète respectant `prefers-reduced-motion`.
- Motion pour les transitions utiles ; animer principalement opacité et transform. Ne pas animer systématiquement la mise en page ou toutes les propriétés CSS.
- Respecter `prefers-reduced-motion` pour toutes les animations. Pas de contenu masqué en attendant une animation.
- `scrollbar-gutter: stable` sur les zones défilantes pertinentes. Aucun décalage à l’ouverture des dialogues ; pas de scrollbar cachée qui rende une zone inaccessible.
- Responsive sans débordement horizontal. Transformer les lignes en cartes sur mobile ; conserver l’accès aux filtres et au détail.
- Pas de fausse authentification, faux compte connecté, statistiques décoratives ou fonctionnalités simulées sans indication.

## Livraison

Mettre à jour le README pour les commandes, choix de stack, variables d’environnement et limitations. Consigner les sources dans `docs/data-sources.md`. Mentionner honnêtement les vérifications et les limites restantes.
