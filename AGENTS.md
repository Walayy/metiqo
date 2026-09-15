# Metiquo — instructions du projet

## Présentation

Metiquo est une application d’analyse des values sur les marchés esport. Le premier jeu pris en charge est League of Legends. Le nom du dossier historique est `metiqo`, la marque affichée est **Metiquo**. La première version est une single-page app frontend, intégralement mockée. Le backend sera ajouté ultérieurement dans `apps/api`, dans ce même dépôt.

## Périmètre et données

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

- Monorepo npm workspaces : `apps/web` pour le frontend, `apps/api` réservé au futur backend. Ne pas créer de serveur factice aujourd’hui.
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
- Caret uniquement dans les champs éditables. Texte de contenu sélectionnable ; contrôles non sélectionnables. Ne pas désactiver globalement la sélection ni le focus.
- Réserver les dimensions des images et skeletons. Skeletons correspondant au composant final, annoncés via `aria-busy`, animation discrète respectant `prefers-reduced-motion`.
- Motion pour les transitions utiles ; animer principalement opacité et transform. Ne pas animer systématiquement la mise en page ou toutes les propriétés CSS.
- Respecter `prefers-reduced-motion` pour toutes les animations. Pas de contenu masqué en attendant une animation.
- `scrollbar-gutter: stable` sur les zones défilantes pertinentes. Aucun décalage à l’ouverture des dialogues ; pas de scrollbar cachée qui rende une zone inaccessible.
- Responsive sans débordement horizontal. Transformer les lignes en cartes sur mobile ; conserver l’accès aux filtres et au détail.
- Les favoris sont locaux à l’appareil. Pas de fausse authentification, faux compte connecté, statistiques décoratives ou fonctionnalités simulées sans indication.

## Livraison

Mettre à jour le README pour les commandes, choix de stack, variables d’environnement et limitations. Consigner les sources dans `docs/data-sources.md`. Mentionner honnêtement les vérifications et les limites restantes.
