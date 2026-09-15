# Vérifications de la première version

## Corrections de l’audit — 15 septembre 2026 (points 5–9 et 11–13)

- Pagination mobile : page 2 puis 3, focus replacé sur `values-title`, premières cartes visibles. Précédent/suivant du navigateur restitue les pages 2 et 3 et leurs URL.
- Mobile 320 et 390 px : introduction compacte, probabilité et action Détail visibles, noms longs MVKA–DINO sans débordement. Aucun bouton actif de la liste inférieur à 44 × 44 px dans la mesure DOM à 320 px. Thèmes clair et sombre inspectés.
- Chargement lent à 320 px : le splash disparaît pendant la requête, avec skeletons et spinner fixe ; la recherche reste utilisable et sa saisie est conservée à l’arrivée des données. Première carte à la même position (501,48 px) et de même hauteur (220 px) dans les états skeleton et chargé.
- Favoris : favori T1, filtre LFL, vue vide expliquant le filtre ; l’action d’effacement retrouve T1 en restant dans les favoris. La vue et le favori sont conservés après F5. Le favori de test a été retiré.
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
- Ajout d’un favori, conservation après rechargement, ouverture depuis « Mes favoris ».
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

Ces contrôles ne sont pas une certification d’accessibilité ni une garantie d’absence de bugs sur tous les appareils. La réduction des animations est prise en charge par Motion et la media query CSS ; le réglage système n’a pas été modifié pendant les tests. Le backend n’existe pas encore et aucune offre de pari réelle n’a été vérifiée. Les tests navigateur ci-dessus ont été effectués dans la session de développement ; seuls les tests métier sont inclus dans la suite Vitest.
