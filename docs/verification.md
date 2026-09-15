# Vérifications de la première version

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
