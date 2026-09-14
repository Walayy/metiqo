# Audit UI/UX — 8 septembre 2026

La [revue complémentaire du 9 septembre](ui-ux-audit-20260909.md) décrit les corrections et vérifications les plus récentes. Les résultats ci-dessous documentent la passe précédente.

L’audit porte sur l’état du dépôt, y compris la refonte du design system déjà présente avant cette intervention. Les corrections conservent l’identité visuelle de Metiquo, ses contrats et ses règles d’admission. Les scénarios de mutation sont exécutés dans la démo mock ou avec des réponses de transport synthétiques.

## Inventaire et couverture

| Route                         | Composants et parcours examinés                                                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/`                           | Opportunités, filtres URL, tri, tableau/cartes, explications ouvertes, grades, fraîcheur, cotes modifiées, absence de résultat, pagination                            |
| `/events`                     | Catalogue, cartes, compteurs, formats, noms longs, absence de résultat, page suivante                                                                                 |
| `/events/[eventId]`           | En-tête, participants, prix, courbe, marchés, provenance, chronologie, accès paper, ressources absentes et accès refusé                                               |
| `/opportunities/[signalId]`   | Signal admissible/bloqué/ancien, prix observé, modèle, incertitude, raisons d’abstention, gates, historique, liens de retour                                          |
| `/models`                     | Champions, challengers, versions bloquées/retirées, entraînement immédiat/différé/échoué, promotion, métriques absentes, calibration, backtests, faibles échantillons |
| `/data`                       | Sources multiples, snapshot, couverture, ingestions, capacités, anomalies, quarantaine, chargement/erreur/vide indépendants et collections longues                    |
| `/admin`                      | Synchronisation, état opérationnel, mapping multi-revues, candidats vides, alias, justification, décision, jobs, journal et réglages de publication                   |
| `/paper-trading`              | Création au clavier, montant invalide, signal inéligible, attente/succès/erreur, règlement fictif, résultats observés, rapport financier, pagination                  |
| `/paper-trading/[paperBetId]` | Décision, règlement, versions/snapshots, provenance du signal, ressources absentes, règlement réel depuis preuves synthétiques                                        |
| `/settings`                   | Portes de publication, raisons de refus, informations de configuration et navigation vers le thème                                                                    |
| Routes de repli               | Adresse inconnue, erreur inattendue d’affichage, retour à l’accueil                                                                                                   |

Le shell commun, `OwnerAccess`, `ThemeMenu`, `QueryRecovery`, `PagedResults`, `OddsObservation` et le composant non routé `PlaceholderPage` ont également été lus. Les routes techniques `/health` et `/api/backend/[...path]` n’ont pas d’écran ; leur comportement est vérifié par les tests de proxy et de sécurité existants.

Les huit fichiers de composants de `packages/ui/src` ont été inspectés intégralement : boutons et variantes, `MotionButton`, cartes, badges, contrôles de formulaire, présentation des valeurs et métriques, tableaux et listes de statuts, ainsi que les neuf états distants et leurs skeletons. L’application n’expose pas de composant checkbox, switch ou tooltip dédié : aucune fonctionnalité artificielle n’a été ajoutée pour en créer.

## Problèmes corrigés à leur source

| Problème constaté                                                                        | Correction                                                                                                           |
| ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Scrollbars locales de 5 px et couleurs peu perceptibles                                  | Tokens communs clair/sombre, contraste renforcé, survol, piste transparente et mode couleurs forcées                 |
| Ouverture d’un menu rétrécissant le contenu de 10 px                                     | Compensation Radix neutralisée lorsque la gouttière native conserve déjà l’espace                                    |
| Navigation fixe inaccessible sur faible hauteur                                          | Défilement vertical conditionnel du menu mobile et de la barre latérale ; fermeture et restitution du focus          |
| Défilement obligatoire même sur une page courte                                          | Shell flex avec hauteur minimale de fenêtre et pied de page, sans `min-height:100vh` additionnel sur `main`          |
| Thème actif invisible ; navigation inactive sur fiche signal                             | Menu de thèmes à sélection radio et surbrillance de la rubrique Opportunités sur les détails                         |
| Bordures de champs insuffisantes, sélection perdue au survol, erreurs atténuées au hover | Tokens de contrôle contrastés et priorité cohérente des états focus/sélection/erreur                                 |
| Bouton lien déclaré désactivé mais encore activable                                      | Blocage effectif de l’action et état accessible ; animation supprimée lorsque désactivé                              |
| Petites cibles tactiles et zoom automatique des champs                                   | Cibles de 44 px sur petit écran/pointeur tactile et champs de 16 px                                                  |
| Select requis sans explication et parcours Tab incomplet                                 | Erreur reliée au champ, focus visible, conservation de sélection et prise en compte des disclosures                  |
| Actualisation recouvrant des commandes                                                   | Bande d’actualisation de 3 px, sans modifier le contenu, le focus ou les dimensions                                  |
| Identifiants/noms longs élargissant des cellules                                         | Retour à la ligne de secours dans les primitives ; aucune troncature des valeurs techniques                          |
| Grilles de métriques déséquilibrées et listes descriptives invalides                     | `dl` propre à chaque métrique, régions nommées valides et colonnes adaptées au nombre de valeurs                     |
| Chargement affiché comme une liste vide, première source seule visible                   | États indépendants loading/error/empty et affichage de toutes les sources reçues                                     |
| Fraîcheur « À l’instant » constante et métriques manquantes assimilées à zéro            | Âge calculé, sources non vérifiées explicites et données indisponibles distinctes d’une valeur nulle                 |
| Collections silencieusement limitées à la première page                                  | Pagination ou chargement complémentaire avec conservation du contexte et compteur explicite                          |
| Formulaires paper incomplets au clavier et historique non rafraîchi après action         | Soumission Enter, validation de montants finis, verrouillage pendant requête et invalidation des lectures concernées |
| Radios de revues différentes portant le même nom                                         | Groupes indépendants, aperçu cohérent et décision figée avec feedback                                                |
| Justifications difficiles à saisir et champs étirés                                      | Textarea multi-lignes, indication de nécessité et alignement des contrôles                                           |
| Connexion sans association de l’erreur aux champs                                        | Erreur liée aux champs, focus restitué au mot de passe et états de déconnexion explicites                            |
| 403/404 de détails présentés comme panne temporaire                                      | Accès refusé, ressource absente et panne récupérable distingués, avec retour disponible                              |
| Courbe reliant des sélections différentes, marqueurs coupés/étirés                       | Série bornée au marché et à la sélection, légende explicite, identifiants SVG uniques et marqueurs ronds             |
| En-têtes serrés et formats monétaires incohérents                                        | Badges sous le titre sur mobile, formats décimaux et monétaires partagés                                             |

Les mesures sur réseau ralenti ont également révélé un pied de page apparaissant entre deux phases de chargement, puis repoussé à l'arrivée des données. Le chargement de session, les replis Suspense et les chargements de contenu principal partagent désormais `RemotePageLoadingState`. Les skeletons du catalogue reprennent sa structure ; les valeurs financières utilisent la hauteur de ligne responsive et réservent la place du bouton de téléchargement. Le panneau opérationnel intègre ses raisons dans les détails pour supprimer les rangées vides. Ces corrections conservent la hauteur naturelle des contenus chargés.

## Protocole de vérification

La matrice `ui-audit.spec.ts` visite les dix routes à 320, 390, 768, 1024, 1440 et 1920 px, en clair et sombre : 120 combinaisons de route, taille et thème. Elle vérifie les titres, erreurs JavaScript, débordements du document et du contenu principal, ainsi que l’absence de scroll vertical imbriqué dans les tableaux. Les captures pleine page et l’audit axe A/AA sont produits à 320 et 1440 px ; les tests d’accessibilité existants ajoutent 390 px.

Les tests dédiés couvrent aussi les fenêtres basses (667 × 320 et 1280 × 400), la stabilité des menus et overlays, les labels extrêmes, l’authentification simulée, les erreurs de détail, les revues simultanées et les collections de plus de 100 éléments. Les suites existantes couvrent les erreurs réseau, les délais, la reconnexion, le maintien du focus et du contenu lors du polling, les refus de permission, la stabilité CLS et le mouvement réduit.

Les primitives non directement exposées par une route sont vérifiées dans les tests de composants. L’inspection visuelle utilise le navigateur intégré et les captures Playwright ; les validations portent sur les états représentables par le code et les fixtures, et ne constituent pas une preuve de toutes les combinaisons arbitraires de données futures ou de navigateurs.

Les scénarios réel utilisent des fixtures de transport : ils vérifient le rendu et les interactions du frontend sans effectuer de pari ni d’opération de production. Le parcours d’authentification avec PostgreSQL est distinct des tests UI de connexion simulée.

Les règles réutilisables sont documentées dans [le design system](design-system.md).

## Résultats vérifiés

Le frontend a été reconstruit et testé avec le serveur Next de production local, relié à l'API mock. Les vérifications de code sont terminées :

- `pnpm build:web` : compilation réussie de toutes les routes.
- `pnpm typecheck` : contrats, composants, application et tests navigateur valides.
- `pnpm lint`, `pnpm format:check` et `pnpm spellcheck` : aucune erreur.
- `pnpm test:components` : 44 tests réussis dans 9 fichiers.

Les sept références visuelles Windows ont été relues et mises à jour pour le résultat corrigé. Les captures pleine page de la matrice couvrent les dix écrans à 320 et 1440 px, dans les deux thèmes.

La suite Playwright complète, exécutée sans mise à jour automatique des captures, termine avec **142 tests réussis, aucun échec et aucun test instable**. Les **2 tests Owner/PostgreSQL** sont ignorés par leur condition d'environnement ; les écrans de connexion et déconnexion, leurs erreurs et leurs interactions clavier sont couverts séparément avec des fixtures de transport.

Les 120 combinaisons de route, largeur et thème passent sans débordement du document ou du contenu principal, sans scrollbar verticale imbriquée dans les tableaux et sans erreur JavaScript. Les audits axe A/AA passent sur les écrans examinés. Les scénarios de stabilité mesurés restent sous **0,05 de CLS** (maximum observé dans la suite complète : **0,0412**). La variation de hauteur entre chargement et réponse des panneaux financiers et opérationnels est comprise entre **0 et 0,125 px**.

Après la dernière retouche de ponctuation dans la revue de mapping, le frontend a été reconstruit et les quatre scénarios de mapping et de stabilité de l'administration ont été revérifiés. Le rapport navigateur complet est disponible dans `playwright-report/index.html`, les résultats structurés dans `test-results/final-results.json` et les captures dans `test-results/`.
