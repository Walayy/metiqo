# Metiquo

Une SPA d’analyse des **values esport**, dédiée à League of Legends pour sa première version. Le frontend fonctionne intégralement en mode mock. Le premier écran permet de comparer les opportunités, filtrer les ligues et marchés, suivre des favoris locaux et examiner le calcul d’une value. **Stake est la seule source de cotes** : le suivi présente leurs relevés horodatés depuis l’enregistrement du match.

## Démarrage

Node.js **22.12+** (ou 24+) et npm. Depuis la racine du dépôt :

```sh
npm install
npm run dev
```

Ouvrir <http://127.0.0.1:5173>. Le port est fixe : Vite signale s’il est déjà occupé. Le serveur écoute uniquement en local.

```sh
npm run check        # TypeScript, ESLint, tests métier, build de production
npm run build
npm run preview      # Production locale sur http://127.0.0.1:4173
npm run format
npm run format:check
```

## Stack retenue

| Outil                             | Rôle et choix                                                                                                                                                             |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| React 19.3 + TypeScript 6.0       | Composants typés, écosystème mature. TypeScript 6 est retenu pour rester dans la plage officiellement supportée par typescript-eslint, sans forcer les peer dependencies. |
| Vite 8.3                          | SPA rapide à développer et à compiler, sans serveur de rendu superflu.                                                                                                    |
| Tailwind CSS 4 + tokens CSS       | Utilitaires et design system sur mesure. Toutes les surfaces et couleurs possèdent une variante claire et sombre.                                                         |
| TanStack Query 5                  | Cache HTTP, annulation, chargements, erreurs et nouvelles tentatives.                                                                                                     |
| MSW 2 + Zod 4                     | Interception HTTP en mode mock et validation des contrats. La future API pourra remplacer les mocks sans réécrire les composants.                                         |
| Radix UI                          | Dialogues et sélecteurs accessibles : focus, clavier, Escape.                                                                                                             |
| Motion 13                         | Transitions discrètes et respect du réglage de réduction des animations.                                                                                                  |
| Lucide                            | Icônes SVG cohérentes, sans emoji dépendant de l’OS.                                                                                                                      |
| Inter Variable + Manrope Variable | Typographie locale ; aucune requête Google Fonts.                                                                                                                         |
| Vitest + ESLint + Prettier        | Vérification des calculs, intégrité du scénario, règles de code et formatage.                                                                                             |
| Sharp                             | Optimisation des logos à l’import, uniquement en développement.                                                                                                           |

Les versions exactes installées sont dans `package-lock.json`. Le bundle des mocks est chargé séparément. Les panneaux font partie du chargement initial : leur ouverture ne dépend pas du téléchargement d’un module. Aucun routeur ou store global n’est nécessaire pour cet écran unique.

## Structure

```text
apps/
  web/
    public/logos/          # 297 logos officiels optimisés en WebP
    src/
      app/                 # Composition de l’écran, providers, frontière d’erreur
      components/
        layout/            # Navigation responsive
        ui/                # Boutons, dialogues, sélecteurs, logos, graphes, skeletons
      domain/              # Schémas Zod et calculs métier
      features/
        catalog/           # Ligues et équipes
        values/            # Liste, filtres, détail, sélection à la une
      hooks/               # Thème et favoris locaux
      lib/                 # HTTP, configuration, formatage, stockage
      mocks/               # Handlers MSW, scénario déterministe, catalogue sourcé
      styles/              # Tokens et styles responsive
docs/                      # Sources, contrat HTTP et vérifications
scripts/                   # Import et optimisation du référentiel
```

Le futur backend sera ajouté dans `apps/api`, dans ce même dépôt. Il n’est pas implémenté ici. Les workspaces npm sont prêts à accueillir d’autres applications.

## Modes de données

Copier au besoin `apps/web/.env.example` vers `apps/web/.env.local`.

```dotenv
VITE_DATA_MODE=mock
VITE_API_BASE_URL=/api/v1
```

`mock` est le défaut explicite du code. Les fixtures sont servies par MSW via `/api/v1/catalog` et `/api/v1/opportunities`, avec une latence simulée. Le mode mock fonctionne aussi dans le build de production.

Pour le futur backend, utiliser `VITE_DATA_MODE=api` et une base d’URL adaptée, puis redémarrer Vite. L’absence d’API affiche une erreur réelle ; elle ne déclenche jamais un fallback silencieux vers les mocks. Les anciennes inscriptions du service worker MSW de cette origine sont supprimées en mode API. Les variables `VITE_*` sont publiques : **n’y placer aucun secret**.

Le [contrat HTTP](docs/api-contract.md) décrit les endpoints. Les contrats exécutables sont dans les schémas Zod.

## Données et couverture

Au 14 septembre 2026 : **35 compétitions, 262 équipes, 297 logos**, issus des pages publiques LoL Esports. Les six ligues majeures et la LFL sont présentes ; les sources comprennent les ERL, les circuits Challengers et les événements internationaux. Le TFT est exclu.

Ce snapshot couvre le catalogue et les rencontres exposés par Riot à la date de collecte, **pas toutes les compétitions amateurs mondiales**. Les affiliations secondaires sont inférées des rencontres domestiques visibles ; elles ne constituent pas un registre de contrats ou de rosters actifs. Certaines compétitions internationales n’ont volontairement aucune équipe affectée comme ligue d’origine. Le modèle utilise des identifiants ouverts, sans enum de ligues ou de teams : tout nouveau circuit peut être ajouté.

**34 opportunités sur 30 compétitions sont fictives.** Le scénario est fixé aux 14–15 septembre 2026, en heure de Paris. Les rencontres, formats, horaires, probabilités, cotes, historiques et mentions de bookmakers illustrent le produit ; ils ne décrivent aucune offre réelle. Aucun pari, paiement, authentification ou modèle prédictif n’est connecté.

Les [sources et droits des assets](docs/data-sources.md) sont documentés. Pour refaire la collecte officielle, revue humaine nécessaire après import :

```sh
npm run catalog:sync
```

Le script importe exclusivement des données publiques ; il échoue si le format de source n’est plus reconnu. Les identités des équipes utilisées dans les fixtures sont vérifiées, et les tests signalent leur éventuelle disparition.

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

Les vérifications et leurs limites sont consignées dans [docs/verification.md](docs/verification.md). La future API devra fournir le nouveau contrat de suivi Stake ; les anciens tableaux d’offres multi-bookmakers ne sont plus acceptés.
