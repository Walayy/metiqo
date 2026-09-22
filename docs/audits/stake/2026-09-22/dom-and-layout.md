# Atlas DOM et disposition — Stake esport / LoL

[Rapport principal](../../../stake-audit.md) · [Index des preuves](README.md) · [Toutes les cotes](markets-and-quotes.md)

Cet atlas décrit des éléments effectivement présents dans les captures du 22 septembre 2026. Il fournit des points d’ancrage pour comprendre les pages, **pas une garantie de stabilité des sélecteurs**. Les exemples ne lancent aucune collecte. Les IDs de nœuds JSON ne sont valables que dans leur capture.

## 1. Arbre fonctionnel des pages

```text
Document Stake /fr
├── lien « Aller au contenu » → #scrollable
├── navigation Primary [data-testid=left-sidebar]
│   ├── Casino / Sports
│   ├── Direct / Commence bientôt / Tout / Mes Paris
│   ├── sports mis en avant
│   └── Tous les Esports, cotes, langue, autres liens
├── #navigation-container-header
│   ├── Home / logo
│   └── Se connecter / S’inscrire
├── #scrollable
│   ├── fil d’Ariane
│   ├── #main-content
│   │   ├── LISTE : filtres, rencontre × N, pagination
│   │   └── FICHE : résumé, zone de marchés .groups
│   │       ├── Principal / Map N
│   │       ├── Rechercher
│   │       └── .secondary-accordion × N
│   │           ├── .header : titre et contrôles éventuels
│   │           └── .content : en-têtes et boutons de sélection
│   ├── iframe de statistiques, selon viewport et rencontre
│   ├── carrousel casino
│   ├── flux public de paris (autres événements)
│   └── footer
├── navigation mobile, lorsque rendue
├── bulletin de pari, pouvant être hors écran
├── bannière cookies, si non fermée
└── iframes de support / mesure
```

Ce schéma est une carte fonctionnelle : la position exacte des wrappers, du widget et du bulletin varie selon le gabarit. Le JSON conserve l’arbre physique observé. Les signatures `svelte-*`, `data-sveltekit-preload-data`, `data-sveltekit-noscroll` et `data-sveltekit-reload` sont présentes ; aucune version de framework n’est déduite.

## 2. Sélecteurs observés et portée correcte

| Élément                      | Ancre vérifiée                                                              | Usage / risque                                                                     |
| ---------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Navigation latérale          | `[data-testid="left-sidebar"]`, `[role="navigation"][aria-label="Primary"]` | Géométrie compacte ou étendue ; absente du relevé mobile 015                       |
| Basculer la sidebar          | `[data-testid="left-sidebar-close"]` ; nom `Toggle Sidebar`                 | Commande observée ; aucun test systématique de ses variantes                       |
| En-tête                      | `#navigation-container-header`                                              | Ne pas l’utiliser pour déduire les marges du contenu                               |
| Défilement principal         | `#scrollable`                                                               | Rectangle et comportement différents sur mobile                                    |
| Contenu de rencontre         | `#main-content`                                                             | Exclure footer et flux public inférieur                                            |
| Liste des sports             | `[data-testid="sport-menu-list"]`                                           | Liens à partir desquels découvrir les slugs ; éviter une liste de jeux fermée      |
| Aperçu de rencontre          | `[data-testid="fixture-preview"]`                                           | Conteneur de rapprochement marché / équipes / lien                                 |
| Sélecteur de marché de liste | `[data-testid="market-group-button"]`                                       | Valeur Vainqueur observée ; autres options non ouvertes                            |
| Concurrent                   | `[role="group"][aria-label]`, `[data-testid="competitor-item"]`             | Le nom accessible de groupe peut être abrégé                                       |
| Logo concurrent              | `[data-testid="competitor-image"]`                                          | `src` source à conserver ; ne pas inventer un chemin manquant                      |
| Score                        | `[data-testid="score-ticker"]` et `score-ticker-item`                       | Plusieurs unités et périodes : conserver les en-têtes de score                     |
| Région des marchés           | `.groups`                                                                   | Classe observée sur les fiches inspectées                                          |
| Onglet principal             | `[data-testid="tab-main"]`                                                  | Bouton natif, pas un `role=tab` dans les captures inspectées                       |
| Onglets de carte             | `[data-testid="tab-map-1"]` … `tab-map-5`                                   | Découvrir les boutons présents, ne pas itérer 1–5 arbitrairement                   |
| Recherche                    | Champ au placeholder `Rechercher` dans `.groups`                            | Placeholder prouvé par AX ; pas conservé par le filtre d’attributs du JSON initial |
| Groupe de marché             | `.groups .secondary-accordion`                                              | **Le scope `.groups` est nécessaire** : le footer réutilise `.secondary-accordion` |
| Titre de groupe              | `.header`, puis le texte du titre                                           | « Résultat final » inclut aussi Slider/Tout dans le texte du header                |
| Corps de groupe              | `.content` ; état `.is-open`                                                | Un élément présent et un contenu affiché sont deux choses distinctes               |
| Sélection                    | `[data-testid="fixture-outcome"]`                                           | La même ancre est utilisée dans liste et fiche ; toujours rattacher au bon groupe  |
| Nom visible de sélection     | `[data-testid="outcome-button-name"]`                                       | Peut être seulement `3.5`, Oui, Yes ou un nom abrégé                               |
| Cote                         | `[data-testid="fixture-odds"]`                                              | Peut disparaître lors d’une suspension ; valeur portée par un descendant           |
| Consentement cookies         | `[data-testid="cookie-consent"]`, `accept-cookie-consent`                   | Visible dans les premières captures ; gêne une partie de l’écran                   |
| Fermeture du bulletin        | `[data-testid="right-sidebar-close"]`                                       | Présence DOM ne signifie pas bulletin visible                                      |
| Paramètres de bulletin       | `[data-testid="bet-settings-button"]`                                       | Non ouverts                                                                        |
| Footer                       | `[data-testid="footer"]`                                                    | À exclure du parsing de marchés                                                    |

Les IDs `bits-c476`, `bits-c480` et similaires, classes `svelte-1b7980v`, `svelte-24re4n`, etc., sont des **valeurs observées générées**. Elles ne doivent pas devenir des identifiants métier ni des sélecteurs figés. Les attributs `data-testid` sont de meilleures ancres sémantiques dans ce corpus, mais ne constituent pas une API publique garantie.

## 3. Exemple DOM — sélection cotée

Reconstitution abrégée à partir de la capture 005, sans les classes décoratives :

```html
<div class="secondary-accordion is-open">
  <div class="header">
    <span>Vainqueur du match - Two options</span>
  </div>
  <div class="content is-open">
    <button data-testid="fixture-outcome" aria-label="FlyQuest">
      <div class="outcome-content horizontal">
        <span data-testid="outcome-button-name">FlyQuest</span>
        <div class="odds">
          <div data-testid="fixture-odds"><span>1,28</span></div>
        </div>
      </div>
    </button>
  </div>
</div>
```

Les boutons inspectés ne publient pas d’attribut `market-id` ou `selection-id`. Le libellé accessible peut différer du texte visible : `FlyQuest (-2.5)` donne davantage de contexte que le seul `-2.5` visible. Cette différence doit être conservée, sans considérer `aria-label` comme une identité globale.

## 4. Exemple DOM — seuil suspendu

Sur Pyramid–LODIS, carte 2, les deux premiers boutons du total ont un `disabled`, le texte `25.5` et « Suspendu ». Aucun `aria-label` ni nœud `fixture-odds` n’est présent dans ces boutons. Le groupe expose séparément « Plus de » et « Moins de ».

```text
Map 2 - Nombre total de tués
      Plus de                Moins de
      25.5 · Suspendu        25.5 · Suspendu
      26.5 · Suspendu        26.5 · Suspendu
      27.5 · Suspendu        27.5 · Suspendu
```

Un extracteur doit associer titre, en-tête, ligne et bouton avant de produire une observation. Le JSON garde les rectangles et l’ordre ; l’annexe dit explicitement quand le contexte de colonne remplace un nom accessible absent. Le seuil `25.5` n’est jamais une cote.

## 5. Mesures de disposition

Les rectangles utilisent les coordonnées du viewport. Une valeur `y < 0` signifie que le lecteur est déjà descendu. Les mesures ne sont ni des positions absolues dans le document, ni des contraintes CSS garanties. `rendered` contrôle dimensions et visibilité CSS, sans calculer intersection viewport ou occlusion.

### Desktop 1440 × 1000 — capture 005

| Région                       |      x |   y | Largeur | Hauteur / propriété             |
| ---------------------------- | -----: | --: | ------: | ------------------------------- |
| Sidebar compacte             |      0 |   0 |      60 | 1000                            |
| En-tête intérieur            |    150 |   0 |    1200 | 60                              |
| `#scrollable`                |     60 |  60 |    1380 | 940 ; `overflow-y:auto`         |
| `#main-content`              |    150 |  33 |    1200 | 1988 dans cet état défilé       |
| Colonne `.groups`            |    150 | 266 |     824 | 1755                            |
| Iframe Oddin                 |    990 |  60 |     360 | environ 994,55 ; wrapper sticky |
| Onglet Principal             |    154 | 270 |  103,16 | 44                              |
| Onglet Map 1                 | 265,16 | 270 |   85,84 | 44                              |
| Champ recherche              |    150 | 334 |     824 | 42                              |
| Titre du marché vainqueur    |    166 | 404 |  245,13 | 24                              |
| Première sélection vainqueur |    166 | 453 |     392 | 36                              |

Le widget est dans un wrapper `position:sticky` dans ce relevé. Les onglets de carte ne présentent pas la même propriété. Il serait donc incorrect de décrire toute la navigation de la fiche comme sticky.

La sidebar étendue, relevée sur Pyramid après une nouvelle navigation, mesure **260 px** ; `#scrollable` commence alors à x=260. Ne pas mélanger ses mesures avec le gabarit compact de FlyQuest. Les changements de place de contenu peuvent provenir de l’état de la sidebar et pas seulement de la largeur de la fenêtre.

### Mobile 390 × 844 — capture 015

| Région                     | Mesure observée                                                       |
| -------------------------- | --------------------------------------------------------------------- |
| Largeur utile principale   | environ 351,63 px ; x=11,69                                           |
| Onglets                    | Principal 103,16 × 44 ; Map 1 85,84 × 44                              |
| Recherche                  | 351,63 × 42                                                           |
| Marché vainqueur           | 351,63 × 153 ; deux sélections empilées                               |
| Chaque sélection vainqueur | 319,63 × 36                                                           |
| Marché Premier à atteindre | 351,63 × 221 ; deux colonnes conservées                               |
| Sélection dans ce tableau  | 157,81 × 36                                                           |
| Menu de cartes             | Conteneur horizontal `scrollX` ; plusieurs cartes au-delà du viewport |
| Widget droit               | Aucun iframe Oddin monté dans le document parent de cette capture     |
| Navigation basse           | Parcourir, Casino, Pari, Sports, Chat                                 |

Le passage en mobile ne transforme donc pas tous les marchés de la même façon. Une extraction fondée sur « deuxième bouton = deuxième équipe » sans regarder les en-têtes échoue sur les totaux, les marchés Oui/Non et les dispositions variables.

Les boutons de cote mesurés font 36 px de haut sur mobile, tandis que les onglets font 44 px. Il s’agit d’une observation de dimensions, pas d’un verdict de conformité d’accessibilité : les espacements, exceptions et parcours complets n’ont pas été audités.

### Tablette 768 × 1024 — capture 016

La région de marchés mesure environ **661,94 px** et les vainqueurs restent côte à côte, chacun à environ **310,97 × 36 px**. Les tableaux à seuils font environ **312,97 × 36 px** par sélection. La position de sidebar x≈−43,95 révèle un état de transition après redimensionnement ; aucun breakpoint exact ne doit être déduit de cette capture seule.

## 6. Couleurs, typographie et assets

| Élément observé         | Valeur calculée / source                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------- |
| Fond de sidebar         | `rgb(14, 32, 45)`                                                                           |
| Texte général atténué   | `rgb(161, 191, 214)`                                                                        |
| Texte de marché         | `rgb(236, 243, 249)`                                                                        |
| Fond de l’onglet actif  | `rgb(62, 88, 108)`                                                                          |
| Texte de l’onglet actif | Blanc                                                                                       |
| Fond du bouton de cote  | `rgba(0, 0, 0, 0.3)`                                                                        |
| Titre de marché         | 16 px, graisse 600, hauteur de ligne observée dans un rectangle de 24 px                    |
| Onglet de carte         | 16 px, graisse 600                                                                          |
| Chiffres                | Classes/variables tabulaires présentes dans le DOM                                          |
| Logos de concurrents    | 18 × 18 px dans les résumés inspectés, image arrondie, nom séparé dans un groupe accessible |

Les classes font référence à des variables `--edge-color-*`, `--edge-font-*` et à `data-ds-icon`. Les valeurs ci-dessus sont les couleurs calculées de cet état sombre ; elles ne décrivent pas toutes les variables de thème ou les états de survol.

URLs réellement lues sur les éléments `<img>`, sans téléchargement ni reconstruction :

- FlyQuest : `https://cdn.oddin.gg/assets/teams/icons/flyquest.png`.
- Shopify : `https://cdn.oddin.gg/assets/teams/icons/sr_1685574964456.png`.
- Pyramid : `https://cdn.oddin.gg/assets/teams/icons/pyramid.png`.
- LODIS : `https://cdn.oddin.gg/assets/teams/icons/lodis.png`.
- KT Challengers : `https://cdn.oddin.gg/assets/teams/icons/ktc.png`.

Ces URLs prouvent les assets utilisés par la page, pas une licence ou leur caractère officiel auprès des équipes. Les images ont un `alt` vide dans les éléments inspectés ; le nom du concurrent est porté par le groupe et le texte adjacent. Une image absente ne doit pas être reconstituée à partir d’un nom.

## 7. Accessibilité observée et limites

Les contrôles d’onglets et de cote sont des boutons. Les onglets audités possèdent `data-testid` et `type="button"`, mais pas de `role="tab"` ni d’`aria-selected` dans les attributs relevés ; l’état choisi est représenté par les classes et couleurs. Il faut donc vérifier le panneau associé plutôt que supposer un contrat ARIA Tabs.

Les headers d’accordéon inspectés sont des `div` avec des classes de header, sans nom de bouton ou `aria-expanded` dans ces nœuds. Leur fonctionnement au clavier n’a pas été testé. Des classes `focus-visible` apparaissent sur les boutons, ce qui ne certifie pas le parcours ni le contraste effectif du focus.

Le nom accessible du bouton actif peut être « FlyQuest » alors que la cote est dans ses descendants. Un bouton suspendu peut avoir le seul nom « suspended » ou aucun nom explicite avec l’équipe. La restitution finale doit conserver le contexte du groupe. Aucun audit complet avec lecteur d’écran n’a été effectué.

Les scores et dates ne sont pas tous des structures sémantiques dédiées. Aucun élément `<time>` n’a été trouvé dans les captures 004, 005 et 015 ; l’horodatage du match vient ici de chaînes rendues. Les placeholders des scores futurs restent `-` et ne doivent pas être convertis en zéros.

## 8. Procédure de lecture documentaire reproductible

1. Vérifier que l’URL et le contenu chargé décrivent la même rencontre ; une URL mise à jour ne suffit pas pendant une navigation Svelte.
2. Identifier la région de liste ou `.groups`, et exclure footer, widgets, jeux casino et flux public de paris.
3. Dans une liste, extraire un objet par `fixture-preview`, avec le lien complet et les deux groupes concurrents.
4. Dans une fiche, inventorier les onglets présents et noter lequel est affiché. Un onglet absent ne prouve pas le format de la série.
5. Lire chaque accordéon avec titre, en-têtes et sélections. Conserver le texte du groupe pour justifier les contextes de colonne.
6. Relever les contrôles « Charger Plus » et « Tout » dans ce groupe, puis vérifier l’état résultant avant extraction.
7. Pour chaque sélection, conserver texte visible, nom accessible, cote brute, disabled et position. Normaliser la virgule des cotes séparément du point des seuils.
8. Archiver une date de lecture, une URL et une empreinte. Une seconde capture est une seconde observation locale, pas automatiquement une nouvelle cote publiée.
9. Si la page devient un refus/challenge ou une limitation, conserver cette preuve, interrompre la navigation et ne pas interpréter la page comme un calendrier vide.

Cette procédure est un cahier d’observations pour une éventuelle suite. Elle n’ajoute ni collecteur actif, ni cadence sûre, ni droit d’accès automatique. Les preuves de refus montrent que la faisabilité opérationnelle reste à établir.

## 9. Contrôles de lecture hors ligne

Exemple depuis la racine du dépôt pour lire une capture JSON gzip, sans réseau :

```powershell
uv run --frozen python -c "import gzip,json,pathlib; p=pathlib.Path('docs/audits/stake/2026-09-22/005-flyquest-principal.dom.json.gz'); d=json.loads(gzip.decompress(p.read_bytes())); print(d['url'], d['viewport'], len(d['nodes']))"
```

Exemple d’empreinte d’une preuve :

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath docs/audits/stake/2026-09-22/005-flyquest-principal.dom.json.gz
```

Comparer le résultat à l’entrée correspondante du manifeste. Les champs `parent` / `i` reconstruisent l’arbre des nœuds exportés ; certains nœuds non retenus peuvent manquer. Le champ `text` est le texte direct regroupé du nœud : l’arbre AX complète la lecture de l’ordre textuel et des noms accessibles. Un rectangle ou une classe conservée ne constitue pas, seul, une preuve d’interactivité.
