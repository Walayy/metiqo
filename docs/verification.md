# Vérifications

## Scripts et journaux allégés — 25 septembre 2026

- Scripts reprend le titre avec compteur de l’administration ; les workers tiennent dans une barre dépliable et les lignes mobiles donnent priorité au nom, à la prochaine échéance et à l’état. Le lecteur de journal utilise `Modal`, `Select`, l’indicateur de sélection et les transitions de dépliage partagés. Les informations techniques se consultent au dépliage ; les incidents restent accessibles même avec un filtre de gravité.
- Inspection dans le navigateur à 390 × 844 (clair), 768 × 1024 et 1440 × 900 (sombre), puis 320 × 568 et 844 × 390. Correction du débordement des options longues dans le sélecteur commun et de la hauteur disponible en paysage. Les tests couvrent les deux thèmes de 320 à 1920 px, l’ouverture au clavier, les états vides, la réduction des mouvements, le glissement de fermeture et le retour du focus, y compris journal → historique.
- `npm run check` : 81 tests frontend, 213 tests backend réussis et 4 tests environnementaux ignorés, types, lint et build valides. Les avertissements existants de taille du bundle mock et de dépréciation Starlette restent présents.
- Suite Playwright : 51 scénarios réussis au premier passage, puis correction de l’horloge du scénario Matchs qui dépendait de la fin de journée de Paris et rejeu réussi. Les cas des journaux vérifient aussi le suivi des nouvelles lignes sans doublon ni déplacement pendant la lecture.
- Les parcours Admin utilisent uniquement les fixtures explicites sous `apps/web/e2e/fixtures`, sans changement de l’authentification produit. Le lanceur temporaire utilisé pour l’inspection manuelle a été retiré. Docker Desktop local échoue au démarrage ; l’intégration PostgreSQL locale n’a pas été rejouée. La CI reste requise avant fusion. Aucun téléphone physique, Safari, lecteur d’écran complet ou clavier virtuel iOS/Android testé ; aucune mesure de gain de fréquence d’affichage revendiquée.

## Cotes dans le détail et statuts des sélections — 24 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, 80 tests frontend, build, Ruff, mypy et 183 tests backend hors intégration. Les 88 tests d’intégration PostgreSQL passent sur une base isolée ; `uv run --frozen alembic check` ne détecte aucune dérive. Le contrat frontend refuse deux relevés de même marché et phase. Les builds Docker `api`, `worker` et `web` réussissent. Les avertissements de taille du bundle mock Vite et les deux dépréciations Starlette subsistent.
- Le smoke Playwright Chromium passe localement : chargement du build mock, navigation vers Matchs et absence d’erreur JavaScript. Le workflow `.github/workflows/ci.yml` publie les quatre contextes exigés par la protection de `master`.
- Web et API Docker locaux reconstruits et sains. Dans la rencontre réelle Avella SU Esports–Verdant, la liste ne montre qu’un indicateur, puis le détail présente une seule fois « Vainqueur du match » et « Vainqueur de la carte 3 », chacun avec ses lignes pré-match et live. Le résultat du match est gagnée/perdue selon la base ; les cartes 1, 2 et 3 restent en attente dans `bookmaker_selection_results` et sont affichées comme telles, sans déduction depuis le score des cartes.
- Parcours contrôlés en sombre sur le build API, en clair et sombre sur le mode mock ; desktop, tablette 768 px et mobile 390 px. Aucun débordement horizontal de page ou de section observé à 390 px. Ouverture/fermeture de la section par Entrée, fermeture de la modale par Escape et retour du focus à la ligne vérifiés. Aucune erreur console observée sur le parcours API. Un appareil physique et un lecteur d’écran complet n’ont pas été testés.

## Phases de cote, hovers, icônes et fluidité — 24 septembre 2026

- Les prix Stake pré-match et live ont une projection distincte avec horodatage propre, conservation historique et suspension sans reprise d’un ancien prix. Les deux marchés autorisés sont testés dans PostgreSQL : deux cas paramétrés passent sur `metiquo_loltv_test`.
- Marges de survol augmentées, SVG locaux LoL/LoLTV/Stake sourcés, icône descriptive pour Oracle, indicateurs à cœur fixe et halo animé. Matchs et Scripts contrôlés en clair/sombre à 1440, 768 et 390 px, sans débordement horizontal observé. Navigation clavier des accordéons et infobulles contrôlée ; deux phases simultanées vérifiées avec les fixtures mock séparées.
- La page ne rerend plus entièrement chaque seconde. Les contrôles de géométrie sont regroupés et les surbrillances ne recalculent plus leur visibilité pendant le défilement. Sur des fenêtres de 12 secondes, le temps React cumulé passe de 385 à 78 ms pour la liste et de 734 à 122 ms pour le détail. Le percentile 95 des intervalles d’image reste similaire. Protocole, sonde retirée du produit et limites dans [l’audit](audits/ui-performance/2026-09-24/README.md).
- `npm run check` réussi : TypeScript, ESLint, 79 tests frontend, build, Ruff, mypy et 183 tests backend hors intégration. Les avertissements préexistants de chunk mock et de dépréciation Starlette subsistent. API et web Docker locaux reconstruits, sans nouvelle migration. Les données des workers existants restent conservées.
- Les mouvements réduits sont couverts par les garde-fous CSS et tests existants, sans modification de préférence système dans le navigateur. Aucun test sur appareil physique ou Safari ; les gains mesurés ne constituent pas une garantie universelle de fluidité.

## Barres latérales des camps — 22 septembre 2026

- Pictogrammes remplacés par des barres arrondies de 3 px aux bords extérieurs des deux blocs d’équipe. Couleur issue du camp de la carte, indépendamment de la position gauche/droite ; valeur absente ou `null` : barre neutre et nom accessible « Camp non renseigné ». Transition de couleur de 240 ms, désactivée en mouvement réduit.
- Navigateur en clair/sombre à 320, 768 et 1440 px : ancrage extérieur conservé, aucun débordement de page ou modale, cinq bans par équipe sur une ligne à 320 px. Skillcamp–Arctic Pandas présente bleu à gauche/rouge à droite ; Vivo Keyd Stars Academy–Dplus KIA Challengers présente l’inverse. Infobulle du camp vérifiée au clavier, aucune erreur console. La projection réelle ne contenait pas de carte commencée au camp inconnu pendant cette vérification ; le repli neutre est défini dans le composant et ses styles, sans modification de données source.
- `npm run check` validé : 77 tests frontend, 117 tests backend hors intégration, TypeScript, ESLint, build, Ruff et mypy. Avertissements préexistants MSW/Starlette ; aucun collecteur modifié.

## Continuité des cartes et du défilement — 21 septembre 2026

- Le changement de carte ne lance plus de remontée. Panneau conservé, animation d’apparition retirée et fond de sélection informé du scroll par Motion. Le changement de périmètre réinitialise seulement la référence des surbrillances : aucune fausse mise à jour live lors de la navigation.
- Service commun installé à la racine de l’application : document et zones verticales déjà consultées, compensations temporaires nettoyées, gestes du lecteur prioritaires, préférence de mouvement réduit et onglet masqué pris en compte. Les changements de vue explicites réinitialisent la référence. Six tests couvrent position encore valide, nouvelle borne, disparition totale de scrollbar, changement rapide vers un contenu long, interruption par le lecteur et nettoyage/réduction des mouvements.
- Navigateur réel, Skillcamp–Arctic Pandas : **396 → 396 px** sur ordinateur et **844 → 844 px** sur mobile après plusieurs changements de carte par clic réel et flèches clavier. Aucun `data-updated` déclenché par ces changements. Au passage à un poste unique, étapes observées **396 → 352 → 301 → 141 px**, avec retrait final de l’espace provisoire.
- Vérification hors modale : fermeture de l’accordéon EMEA Masters, document **239 → 176 → 162 → 0 px**, compensation finale vide. Ce parcours contrôle la compensation du document, au-delà du seul détail des matchs ; toutes les vues et tous les appareils physiques n’ont pas été exercés individuellement.
- Largeurs 320/390/768/1440 px, clair/sombre : aucun débordement horizontal constaté. Victoire réduite à une coche sur le logo ; camp publié représenté par un pictogramme distingué par couleur et géométrie, avec infobulle « Côté bleu » vérifiée au focus. Les noms d’équipes occupent une seule rangée de métadonnées. Aucune erreur console sur les parcours inspectés.
- `npm run check` : **77 tests frontend** et **117 tests backend** hors intégration, TypeScript, ESLint, build, Ruff et mypy validés. Avertissements MSW/Starlette préexistants. Aucun collecteur ni contrat de données modifié pour cette intervention.
- Web local seul reconstruit ; contrôle final sur `127.0.0.1:8080`, à 390 px : carte 1 → 2, **844 → 844 px**, zéro surbrillance de navigation, zéro débordement et aucune erreur console. API et worker non redémarrés.

## Filtres stables, icônes et bans — 21 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, build, **71 tests frontend**, Ruff, mypy et **117 tests backend** hors intégration. Mise en forme Prettier et `git diff --check` validés. Les avertissements préexistants MSW et Starlette restent inchangés ; aucun collecteur modifié par cette correction visuelle.
- Navigateur réel en mode API à 320, 390, 768 et 1440 px, thèmes clair/sombre : aucun débordement horizontal de page ou de modale observé. Les quatre filtres de statut gardent chacun **109,5 × 44 px** sur ordinateur avant/après sélection ; à 320 px, **67,75 × 48 px**. Les postes gardent leur position en passant de Tous à Top/ADC ; cibles de 44 px minimum, deux rangées à 320 px.
- Carte unique Vivo Keyd Stars Academy–Dplus KIA Challengers : aucun sélecteur de carte, durée et statistiques conservées, dix bans publiés affichés. Les portraits sont des `span` accessibles, sans bouton ni popover au clic ; infobulle « Karma » contrôlée au focus, curseur neutre et transformation `none`. Survol câblé par Radix Tooltip et surbrillance CSS, sans déplacement ; le pilote navigateur utilisé ne permet pas un déplacement de pointeur indépendant pour instrumenter ce survol.
- Skillcamp–Arctic Pandas : navigation des cartes par flèches, largeur des trois onglets stable à **223,66 / 223,67 / 223,67 px** sur tablette, défilement conservé à zéro en haut de la fiche. Suppression de la barre verticale parasite pendant le mouvement du fond de sélection. Fermeture Escape et retour du focus à la rencontre vérifiés ; aucune erreur console relevée.
- Les résultats de la liste utilisent une coche ou un tiret ancré au logo, avec nom accessible ; aucun libellé sous le nom d’équipe. Réduction des mouvements conservée via le composant commun et CSS. Pas de certification sur appareil physique ou lecteur d’écran complet.
- Service web seul reconstruit et healthy sur `127.0.0.1:8080` ; contrôle final de la modale BO1 sur ce build : zéro sélecteur, dix portraits de bans, zéro bouton de ban, cinq icônes de poste, aucune erreur console. API et worker laissés en fonctionnement.

## Durée LoLTV et actualisation visible — 21 septembre 2026

- TypeScript, ESLint, build et **71 tests frontend** validés par `npm run check`. Après les derniers cas de pause et de priorité des métadonnées, `npm run check:backend` valide Ruff, mypy et **117 tests backend** hors intégration. Les 56 tests PostgreSQL n’ont pas été relancés pour cette modification. Avertissements préexistants : chunk MSW et dépréciations Starlette/httpx.
- Comparaison avec le composant public LoLTV et les trames archivées : Pyramid–LODIS donne **36:28** et **34:15**, comme la fiche du site. Tests des pauses cumulées/chevauchantes, reprise explicite, pause ouverte, reprise orpheline, zéro réellement observé et priorité de l’horloge du flux sur le HTML incomplet.
- Recalcul hors réseau de **8 cartes sur 5 rencontres**, par rejeu des flux terminés conservés, contrôle de leur empreinte et verrou source partagé. Historique conservé, aucune nouvelle rencontre créée, aucune requête LoLTV. Exécution journalisée `8b1b80e8-dd49-41b0-9a99-7cf25897196a`, portée `reprocess-duration-offline`, avec les chemins de preuve et dates source. Les métadonnées ultérieures ne peuvent pas réintroduire le temps des pauses.
- Vérification réelle sur `127.0.0.1:8080` : modale ouverte sur Pyramid–LODIS carte 2 ; **35:49 → 34:15** reçu automatiquement, sans rechargement. Carte 2 et `scrollTop=0` conservés ; date de trame inchangée `2026-09-21T19:14:39.960Z`. Web/API/worker reconstruits, services healthy.
- Scénario explicitement fictif `mock=live-updates` : polling effectif, panne 503 puis reprise sans F5, arrivée de la carte suivante sans détourner la lecture de la précédente. À 390 px, filtre ADC et `scrollTop=450` conservés durant les mises à jour. Aucun effet à l’ouverture/réouverture ; changements limités aux valeurs visibles, pas aux joueurs hors écran ni à la liste masquée sous la modale. Les compteurs relatifs ne déclenchent aucun effet.
- Navigateur à 320/390/768/1440 px, clair et sombre : aucun débordement horizontal constaté, Escape et retour du focus vérifiés, aucune erreur console sur les parcours inspectés. Tests de visibilité : conteneurs défilants, onglet masqué, superposition, annulation et réduction des mouvements. Aucun match encore live dans la projection réelle au contrôle final : les transitions live et la panne ont donc été vérifiées avec le scénario contrôlé, complétées par la correction réelle ci-dessus.

## Refonte UI/UX de Matchs — 21 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, **64 tests frontend**, build, Ruff, mypy et **101 tests backend** hors intégration. Les nouveaux tests couvrent les statuts modifiés, la priorité live, l’ordre stable, les écarts d’or incomplets et les horodatages. Avertissements préexistants : taille du chunk MSW et dépréciations Starlette/httpx.
- Navigateur réel en mode API : clair/sombre, largeurs 320, 390, 768, 1024, 1440 et 1920 px, paysage 844 × 390. Aucun débordement horizontal global constaté ; fermeture de modale de 44 px à 320 px. Contrôles échantillonnés au clavier : Échap, retour du focus et flèches des onglets.
- Parcours terminés G2–Movistar KOI, direct Team Aqua–CITA, rencontres WSCI à venir ; recherche et effacement, combinaison de filtres avec état vide explicite, répertoire des ligues, filtre de poste, changement de carte et actualisation manuelle avec conservation des ouvertures. Les onglets restent visibles au défilement et le changement de carte replace son contenu sous la navigation.
- Mesures indicatives : premier accordéon à environ 485 px sur desktop 1440 px (environ 630 auparavant) ; lignes joueurs mobile de 75 px dans l’échantillon contre environ 109 auparavant ; zone défilante de détail en paysage d’environ 320 px contre 236 auparavant.
- Service web local seul reconstruit en mode API sur `127.0.0.1:8080`, état healthy. Fiche à venir vérifiée sur la version reconstruite à 320 px et liste à 1920 px ; aucune erreur console relevée. Aucun changement du worker ni de la collecte. Réduction des mouvements conservée dans le code ; pas de certification lecteur d’écran ou sur appareils physiques.
- Les portraits de bans restent sans libellé visible ajouté. Aucune relation compétition/phase ni URL de diffusion n’est inventée lorsque le contrat ne la fournit pas.

## Latence LoLTV — 21 septembre 2026, après 20 h 40 Paris

- Mesure avant correction dans `ingestion_runs.details.resources` : cartes live relues toutes les 90–93 secondes en moyenne, maxima observés de 108–117 secondes. Le cron à la minute arrondissait l’échéance de 60 secondes. Une réponse de Pyramid–LODIS sans horodatage avait repoussé la fiche de 18:38 à 18:53 UTC.
- Cadence corrigée : échéance live de 30 secondes, réveils intermédiaires pour le cron continu, priorité renouvelée pendant le remplissage historique, sessions anonymes réutilisées par rencontre dans leur validité, erreurs temporaires live à 60 puis 120 secondes. Pauses 2–4 secondes, budget 120/600 secondes, arrêt 403/429 et `Retry-After` conservés. Pause administrateur et crons personnalisés testés.
- Sur la version finale, entre 18:55 et 18:56:53 UTC : trois lectures de Pyramid–LODIS et deux lectures de la troisième carte Team Aqua–CITA ; intervalle moyen **35 secondes** pour chacune, 35–36 secondes sur Pyramid. Âge moyen des données source à leur réception : 34 et 26 secondes respectivement. Ces petites fenêtres de mesure ne constituent pas une garantie de latence permanente.
- À 18:56:53 UTC : six derniers cycles sans erreur, aucune fiche due restante ; compteur **51/120** dans la fenêtre ouverte à 18:48:09 UTC. Aucun nouveau refus pendant la validation : le dernier 403 enregistré reste celui du diagnostic initial, à 17:32:43 UTC. Le worker reste actif ; ni compteur ni protection n’ont été effacés.
- Cas source distinct : Team Aqua–CITA carte 2 renvoyait un flux `COMPLETED` de 18:28:22 UTC alors que les métadonnées indiquaient encore `STARTED`. Le relevé n’a pas été rajeuni. Les flux terminés sont maintenant conservés pendant l’attente du résultat HTML ; les métadonnées entre cartes expirent après une minute pour découvrir rapidement la suivante, sans répéter le flux final.
- `npm run check` réussi : TypeScript, ESLint, build, Ruff, mypy, **60 tests frontend et 101 backend**. **56 tests PostgreSQL** réussis dans la base isolée. Tests supplémentaires : réveil hors tick cron, préemption des historiques par un live dû, conservation des refus/budgets, isolation/expiration des sessions, absence de POST répété après 401, reprise après erreur et découverte de carte à score inchangé.
- Navigateur : la carte Pyramid–LODIS ouverte se met à jour sans actualisation manuelle (temps au relevé, or, K/D/A), tout en conservant la sélection. Contrôles clair/sombre, mobile/tablette/desktop et clavier ; carte future désactivée, historique consultable, Escape et retour du focus. Le frontend conserve sa lecture API toutes les quinze secondes et le skeleton de sélection prévu ; aucun délai artificiel n’est ajouté aux rafraîchissements périodiques.

## Migration LoLTV — 21 septembre 2026

- `npm run check` réussi : TypeScript, ESLint, build Vite, Ruff, mypy, **60 tests frontend et 95 tests backend**. **52 tests PostgreSQL** réussis dans la base isolée `metiquo_loltv_test`, avec les rôles SQL restreints. Avertissements préexistants : taille du chunk MSW et dépréciations Starlette/httpx.
- Migration `0012` appliquée ; API, web en mode API et worker reconstruits et démarrés. La planification LoLTV remplace l’ancienne, les relevés historiques et les autres sources sont conservés.
- HTML public analysé sur calendrier, résultats paginés, série live et finale. La fenêtre du 14 au 28 septembre contient **87 rencontres connues**. Vers 18:36 UTC, la projection contient **134 cartes avec dix joueurs, dont 106 avec des bans**. Les cycles de 18:34 et 18:35 UTC se terminent sans erreur et sans fiche due restante ; le cache évite respectivement quatre et trois documents. Ces compteurs sont datés, pas une promesse de couverture totale.
- Parcours normal de consultation anonyme validé depuis Docker : découverte de `getFeedSession` dans le script public, cookie en mémoire, flux de carte HTTP 200. Une lecture directe sans session a répondu 401. Le diagnostic Chromium initial a répondu 403 : délai conservé puis respecté ; le parcours par défaut n’utilise pas Chromium. Aucun contournement ni rotation d’identité.
- Équipes et camps réels contrôlés sur les flux. Les codes UCAM/UE et les suffixes d’équipes secondaires utilisent uniquement les alias publiés et la règle du composant source, avec cinq tags concordants. Un premier rapprochement Oracle complet de **trois cartes** a été publié ; les jeux sans fuseau vérifié restent inconnus sauf preuve statistique exacte et unique.
- Tests de régression : Flight fragmenté et UTF-8, BO inconnu, faux zéros/camps des placeholders, mauvais identifiant de carte, alias contradictoires, confidentialité des cookies, arrêt au premier refus, cache de métadonnées sans nouvelle observation, conservation du dernier relevé live sans rajeunir sa date et rejet des remakes.
- Navigateur local : données réelles, compositions et camps, changement de carte au clavier, fermeture Escape et retour du focus, lecture à 390/768/1440 px en clair et sombre, absence de débordement horizontal observée. La reprise du calendrier et de la session après le redémarrage de l’API a été contrôlée. Pas de test sur appareil physique ni de lecteur d’écran complet.
- Finale LEC G2–Movistar KOI : trois cartes consultables, cartes 4/5 non jouées désactivées, dix bans sur la première carte avec noms accessibles et popover. Admin : worker connecté, LoLTV planifié chaque minute, historique consultable, lancement désactivé pendant une exécution. Les réglages Oracle existants de l’utilisateur sont conservés.

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

## Restauration Stake pré-match — 23 septembre 2026

- Migration `0013` appliquée à la base locale revenue à `0012`. Les sept tables `bookmaker_*` ont reçu les données du dump pris avant ce retour : 20 événements, 260 marchés, 760 sélections, 227 snapshots, 14 160 cotes, 31 preuves et 5 liens de rapprochement. Les contrôles de clés orphelines, de correspondance des événements et de dates des cotes n’ont révélé aucune anomalie. Le rôle API possède la lecture et non l’insertion des cotes ; le worker possède l’insertion.
- Worker Stake natif relancé, distinct du worker Docker. La planification `stake-markets` est active toutes les dix minutes. Un cycle planifié complet a réussi : 13 événements examinés, 10 collectés, 3 arrêtés, 0 échec et 528 nouvelles cotes ; le total était alors de 14 688 cotes. La disponibilité de la source et le nombre d’offres peuvent changer.
- Administration vérifiée dans le navigateur local sur ordinateur, tablette et mobile, en clair et sombre : script visible, worker connecté, cadence et prochain lancement affichés. Le formulaire propose la fréquence de dix minutes en heure de Paris ; Escape ferme le dialogue et rend le focus au bouton d’origine. Aucun débordement horizontal observé à 390 px.
- `npm run check` et ses contrôles de types, lint, tests hors intégration et build relancés après restauration. Les tests PostgreSQL marqués `integration` et les anciens scripts de smoke Chrome synthétique n’ont pas été rejoués. Le moteur de values supprimé reste absent ; aucun calcul de value réel n’a été vérifié ici.

## Purge SofaScore et cadence Stake — 23 septembre 2026

- Le balayage des colonnes texte et JSON de la base locale n’a trouvé aucun enregistrement contenant `sofascore` ; les sources présentes dans `matches`, `match_snapshots`, `match_source_links`, `ingestion_runs` et `collector_state` sont LoLTV, Oracle et Stake. La migration `0014` supprime les éventuels restes SofaScore lors d’une mise à niveau et retire aussi son ancien cron.
- La migration `0014` règle Stake à `*/20 * * * *` en heure de Paris. La base a été migrée et la prochaine échéance recalculée sur le prochain intervalle de vingt minutes.

## Rapprochement Stake / LoLTV / Oracle — 23 septembre 2026

Audit préalable et exports sous `docs/audits/matching/2026-09-23`. Migration additive `0015` appliquée à la base locale ; quatre alias sourcés importés avec le rôle SQL worker. Résultat réel : **12 liens démontrés, 8 événements en attente**, cinq anciens liens archivés avant revalidation. Reprise mesurée à **0,119 s** sur les 20 événements présents. Le [bilan JSON](audits/matching/2026-09-23/validation.json) conserve les compteurs et heartbeats ; les empreintes sont dans le manifeste du dossier. Ce corpus ne prouve pas une couverture universelle des fournisseurs.

`npm run check` passe : TypeScript, ESLint, **77 tests frontend**, build, Ruff, mypy et **179 tests backend hors intégration**. **83 tests PostgreSQL** passent dans `metiquo_matching_test`, base isolée : migrations aller/retour et absence de dérive Alembic, rôles SQL, historique immuable, concurrence, publications atomiques, événements futurs, changements d’horaire/adversaire, alias révoqués, rematches et signatures Oracle contradictoires. Les anciens tests ont été alignés sur la purge SofaScore et le cinquième collecteur ; les tables bookmaker de test sont réinitialisées entre cas. Les dépréciations FastAPI/httpx et l’avertissement de taille d’un chunk Vite existaient déjà et restent non bloquants.

Images backend reconstruites ; worker Docker et worker Stake natif redémarrés. Le diagnostic exécuté dans le conteneur avec le rôle worker retrouve le même bilan. Aucun fichier frontend ni parcours UI modifié par cette tâche ; pas de nouvelle vérification navigateur de l’interface. Aucune nouvelle collecte réseau Stake effectuée pour l’audit : les collecteurs reprennent leurs planifications existantes et leurs politiques d’accès. Les liens n’interprètent pas encore les catégories, cuts ou règles de règlement.

## Marchés Stake en direct — 23 septembre 2026

- Migration `0016` appliquée à la base locale : les cinq anciens arrêts `live` / `live_listing` sont archivés dans `bookmaker_collection_resumptions` puis levés. Les 266 snapshots déjà présents et leurs 16 270 lectures ont été conservés. Un `alembic check` sur une base PostgreSQL isolée ne signale aucune dérive de schéma.
- `npm run check` réussi : TypeScript, ESLint, 77 tests frontend, build, Ruff, mypy et 180 tests backend hors intégration. Les 16 tests ciblés Stake passent sur la base isolée, dont les cas PostgreSQL de direct avec début passé ou absent, suspension sans cote, transition de phase, provenance et arrêt terminal.
- Rejeu local hors réseau de l'extracteur sur la liste LoL et trois captures live archivées du 21 septembre : la liste reconnaît le direct `845075`, les fiches live exposent leurs marchés suspendus sans cote et l'en-tête d'équipe évite les collisions entre les lignes « Oui/Non ».
- Exécution réelle `2fbc9710-39c4-4c5d-83f3-7febd9edcfa3`, de 19:08:18 à 19:13:49 UTC : 13 événements collectés sur 13 découverts, dont 3 live, 712 lectures dont 4 suspendues ; aucun échec ni refus déclaré. Dans les trois snapshots live, 182 lectures cotées, 2 suspendues et au moins un marché « Gagnant » coté par rencontre. Aucun couple `disabled`/cote incohérent dans ces relevés. Le worker natif reste actif, avec le cron `*/20 * * * *`.
- API et web locaux reconstruits ; Admin vérifié avec authentification réelle par code Mailpit, en clair et sombre à 1440 × 900, 768 × 1024 et 390 × 844, sans débordement horizontal. L'historique affiche les trois rencontres en direct et les quatre suspensions du passage réel ; son dialogue s'ouvre au clavier, se ferme avec Escape et rend le focus au bouton. Captures de vérification locales sous `.cache/admin-browser-check/`.
- Les prix live sont des observations horodatées. Avec la cadence actuelle, un prix peut avoir changé ou être suspendu entre deux passages ; aucune disponibilité instantanée, prise de pari ou transaction n'a été vérifiée.

## Correction visuelle de Matchs et Scripts — 24 septembre 2026

- Reprise de la grille des cotes sous les deux équipes, suppression des codes d’équipe répétés et des espaces réservés aux values absentes. Le marché reste au centre ; les lignes sans cote restent compactes. Le point live pulse uniquement en opacité. Une value positive affiche une petite flamme et un éclairage contenu, avec son pourcentage dans une infobulle accessible au clavier.
- Scripts présente des familles permanentes, une seule fiche ouverte à la fois, des colonnes fixes pour l’état et la prochaine échéance, puis des détails et actions regroupés. L’historique utilise des lignes dépliables ; le lancement manuel est accessible dans le menu du script. Les skeletons suivent la nouvelle composition.
- Vérification navigateur sur Vite, en clair et sombre, à 390, 768 et 1536 px : données réelles de Matchs (notamment FUEGO / T1 Esports Academy), Scripts, détails, historique et planification. Aucun débordement horizontal observé. Navigation mobile, Tab, ouverture des détails d’historique avec Entrée, fermeture Escape et retour du focus contrôlés. Aucune planification modifiée ni exécution lancée pendant cet audit.
- Les cas de value et de suspension ont été contrôlés avec les fixtures explicites dans un serveur mock temporaire séparé, arrêté après vérification. Ils ne démontrent pas une value réelle côté API. Les garde-fous `prefers-reduced-motion` sont présents dans les styles ; la préférence système n’a pas été modifiée. Aucun appareil physique ni lecteur d’écran complet utilisé.
- `npm run check` réussi après les derniers ajustements : TypeScript, ESLint, 78 tests frontend, build, Ruff, mypy et 183 tests backend hors intégration. `git diff --check` réussi. L’avertissement de taille du bundle mock et les deux dépréciations Starlette préexistantes subsistent ; les 86 tests d’intégration PostgreSQL n’ont pas été rejoués pour cette correction visuelle.

## Bottom sheets mobiles — 24 septembre 2026

- Les dialogues partagés et la navigation mobile utilisent une feuille depuis le bas jusqu’à 680 px. La poignée de 44 px offre deux positions et une fermeture par glissement ; le premier rabattement depuis la position haute ne ferme pas la feuille. Les contenus longs gardent une zone de défilement indépendante. La position de lecture du détail de match est conservée après réduction puis remontée.
- Dans le navigateur local, contrôle visuel à 320 × 568 et 390 × 844 en clair et sombre, puis à 768 × 1024 et 1440 × 900. Parcours vérifiés : filtres, sélecteur de ligues, aide, value, match, profil, soutien, navigation, historique et planification Admin. Le pied du formulaire reste accessible par défilement sur le petit téléphone. Escape et le retour du focus ont été vérifiés ; les flèches haut/bas agissent sur la poignée.
- `npm run check` réussi : TypeScript, ESLint, 80 tests frontend, build, Ruff, mypy et 191 tests backend hors intégration. Deux tests Playwright supplémentaires couvrent le drag, les positions, la fermeture, le focus, la feuille email anonyme, la réduction des mouvements et la présentation centrée sur tablette. Aucune écriture Admin ni demande de code email n’a été faite dans ces parcours.
- Les gestes ont été vérifiés dans Chromium émulé ; un téléphone physique, les claviers virtuels iOS/Android et un lecteur d’écran complet n’ont pas été testés. L’alignement sur le clavier virtuel utilise `visualViewport`, à valider sur appareil réel avant d’en garantir tous les modèles.

## Disponibilité LoLTV et forfaits — 26 septembre 2026

- Audit en lecture seule des exécutions et captures du VPS : statut source `WALKOVER`, flux `UNSTARTED` vide, pagination servie avec un cache de plus de 24 heures et fiches sans identité embarquée. Les détails et limites sont conservés dans `docs/loltv.md`.
- `npm run check` passe : 83 tests frontend, 221 tests backend hors intégration (quatre tests facultatifs Stake ignorés), types, lint et build. Les 107 tests PostgreSQL passent dans un conteneur et une base isolés, dont publication partielle, refus 429 et délai persistant, forfait prioritaire sur Oracle, absence de règlement implicite et migration des anciens statuts avec preuve de snapshot. `alembic check` ne détecte aucune dérive.
- Les 12 tests navigateur ajoutés passent sur Chromium à 320, 768 et 1440 px, en clair et sombre : filtre et statut Forfait, absence de cartes déduites, incidents de collecte partielle, ouverture au clavier, fermeture Escape et retour du focus. Les réponses synthétiques sont limitées aux tests, sans modification des fixtures applicatives ni écriture sur le VPS.
- La suite locale de 64 parcours a d’abord produit 62 succès et deux échecs dans les tests tactiles préexistants : le ressort avait déjà dépassé le seuil de mesure après le relâchement sous six workers concurrents. Les quatre tests de feuille mobile passent ensuite sans concurrence ; aucun comportement tactile n’a été modifié par cette correction.
