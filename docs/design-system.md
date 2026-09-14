# Système de présentation

Le socle visuel est défini dans `packages/ui/src`. Les écrans composent ses primitives et conservent leurs données, actions, règles métier et états distants.

## Diagnostic initial

| Cause partagée                                                 | Effet visible                                                                     | Point de correction                                                       |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Tableaux HTML et largeurs minimales définis par écran          | Colonnes comprimées, contenu à droite hors champ, défilement horizontal permanent | `table.tsx` et `table.css`                                                |
| `break-all` sur des blocs mêlant texte naturel et identifiants | Mots humains cassés et UUID aussi présents que les noms                           | `TechnicalText`, `InlineValues` et politique globale de retour à la ligne |
| Cartes bordées imbriquées et accents répétés                   | Candidats, aperçu et formulaire en concurrence                                    | `Card`, `SelectionItem`, `ContextPanel`, `Section`                        |
| État principal et chaque sous-état rendus en badge             | Cellules Gates bruyantes et lignes excessivement hautes                           | `Badge` pour la synthèse, `StatusList` pour les détails                   |
| Select natifs décorés seulement dans leur état fermé           | Menu système étranger au thème                                                    | `Select` partagé et `form-controls.css`                                   |
| Tailles, espacements et paddings répétés localement            | Hiérarchie et alignements variables                                               | Tokens de `styles.css`, classes de `layout.css`                           |

## Tokens et hiérarchie

Les espacements utilisent `--metiquo-space-*` : `xs` = 4 px, `sm` = 8 px, `md` = 12 px, `lg` = 16 px, `xl` = 24 px, `2xl` = 32 px. Utiliser cette échelle pour les relations récurrentes : valeur → métadonnée (`xs`), label → champ (`sm`), contrôles voisins (`md`), groupes (`lg`), sections (`xl`). Les dimensions fonctionnelles, comme une hauteur de graphique, restent distinctes des espacements.

Les contrôles partagent `--metiquo-control-height` (40 px), `--metiquo-control-radius` et le même focus visible. `ui-content-width` définit la gouttière horizontale commune ; `ui-page-stack`, `ui-toolbar` et `ui-field` fournissent les alignements et espacements usuels.

| Niveau                           | Usage                                           |
| -------------------------------- | ----------------------------------------------- |
| `ui-page-title`                  | Titre de page, taille adaptative de 24 à 30 px  |
| `ui-section-title` / `CardTitle` | Section ou composant, 18 px, graisse 600        |
| `text-body`                      | Texte courant, 15 px                            |
| `ui-metadata`                    | Métadonnée lisible, 13 px, couleur secondaire   |
| `TechnicalText`                  | Identifiant ou clé, 12 px, monospace secondaire |

Le contraste secondaire vient de `ink-secondary`, sans empiler des opacités. La graisse et la taille distinguent les niveaux avant la couleur. Réserver `accent` à l'action principale, `accent-selection` à une sélection discrète et `accent-soft` au contexte. `SelectionItem` atténue aussi son fond et sa bordure ; le radio reste l'indicateur fonctionnel de sélection.

## Tableaux

Fournir `columns` à `Table` : chaque colonne porte un `label`, un `variant` et, exceptionnellement, un `weight` relatif. Les types `identity` et `detail` reçoivent davantage de place que `number` ou `status`. Ne pas ajouter de largeur minimale arbitraire à un écran.

```tsx
<Table
  aria-label="Marchés"
  columns={[
    { label: "Sélection", variant: "identity" },
    { label: "Cote", variant: "number" },
    { label: "Évolution", variant: "detail" },
  ]}
>
  <TableBody>
    {markets.map((market) => (
      <TableRow key={market.id}>
        <TableCell label="Sélection" variant="identity">
          <TableCellContent
            primary={market.name}
            secondary={<TechnicalText>{market.id}</TechnicalText>}
          />
        </TableCell>
        <TableCell label="Cote" variant="number">
          {market.odds}
        </TableCell>
        <TableCell label="Évolution" variant="detail">
          <TableCellContent primary={market.change} secondary={market.updatedAt} />
        </TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

Les autres variantes sont `text`, `date`, `technical` et `action`. Répéter le libellé dans chaque `TableCell` est nécessaire : à largeur réduite, le composant présente les lignes comme des groupes de valeurs étiquetées, sans retirer de colonne. L'adaptation dépend de la largeur du conteneur, y compris lorsqu'un tableau occupe une partie seulement d'une grande page. Les tableaux comportant beaucoup de colonnes s'adaptent plus tôt. Le défilement résiduel reste fin et accessible au clavier.

`TableCellContent` sépare `primary` et `secondary` ; éviter de concaténer cote, commentaire, date et variation en une phrase compacte. `density="compact"` réduit l'espacement vertical pour des données simples. `StatusList items={[{ label, value, tone }]}` regroupe les sous-états textuels ; `tone` accepte `neutral`, `success`, `warning` ou `danger`. L'état global peut conserver son `Badge`.

## Formulaires et actions

`Input`, `Textarea` et `Radio` conservent leurs props natives. `Radio` fixe le type radio. Associer chaque champ à son label, et chaque groupe de radios à un nom commun propre au groupe.

```tsx
<label className="ui-field" htmlFor="grade">
  Grade
  <Select id="grade" name="grade" value={grade} onValueChange={setGrade}>
    <option value="">Tous</option>
    <option value="A">A</option>
    <option value="B">B</option>
  </Select>
</label>
```

`Select` rend son menu avec Radix et les tokens du thème. Son API utilise `onValueChange(value)` ; remplacer les anciens gestionnaires `onChange(event)` lors d'une migration. Les options restent des `<option>`, y compris la valeur vide ; `defaultValue`, `name`, `form`, `required` et `disabled` sont pris en charge. Le select natif interne sert à la compatibilité des formulaires, sans constituer le menu visible.

Utiliser `IconButton` avec un `aria-label` explicite et `active` pour un état toggle. `ToggleGroup` rassemble les actions liste/grille ; lui donner un nom accessible. Les boutons utilisent `primary`, `secondary`, `outline` ou `ghost`. Une action secondaire de formulaire conserve une largeur intrinsèque ; dans une grille, utiliser `justify-self-start` si nécessaire.

## Contenu, KPI et surfaces

`MetricGrid` rend une grille adaptative ; chaque `Metric` contient sa propre liste descriptive (`dl`) et reçoit `label`, `value` et éventuellement `detail`. Ne pas entourer `Metric` d'un autre `dl`. Son conteneur peut ainsi être une région nommée sans invalider la relation entre termes et valeurs. `emphasis="statistic"` accentue les valeurs de synthèse et réserve au moins une ligne par niveau. Une sous-grille aligne automatiquement labels, valeurs et détails sur les contenus les plus longs de chaque rangée, sans réserver de grandes zones vides. Les groupes de six valeurs se répartissent sur trois colonnes au maximum ; ceux de huit ou douze, sur quatre. Les contenus plus longs peuvent agrandir la métrique sans être coupés. Une valeur composée utilise `InlineValues items={[teamA, teamB]}` : les groupes passent à la ligne aux limites naturelles, et un suffixe numérique reste lié au nom. Le séparateur est personnalisable.

Le texte humain garde `word-break: normal` : les retours se font aux espaces. Les primitives utilisent `overflow-wrap: anywhere` comme dernier recours lorsqu'un mot entier dépasse la largeur disponible, sans tronquer le contenu. Ne pas utiliser `break-all`. Envelopper UUID, versions et clés dans `TechnicalText`, qui conserve la valeur complète en réduisant leur poids visuel. Dans une cellule entièrement technique, utiliser `variant="technical"`.

`Card` délimite un bloc autonome. `variant="flat"` permet de conserver sa sémantique sans ajouter une surface bordée. `CardHeader`, `CardTitle` et `CardContent` contrôlent sa structure et ses espacements ; `TitledCard` les assemble avec un titre et une icône facultative, sans surface décorative autour de l’icône. Pour une sous-section, préférer `Section` et son séparateur léger. Pour un aperçu ou une explication, utiliser `ContextPanel` avec un `tone` parmi `neutral`, `info`, `warning`, `success`, `danger`. Ajouter explicitement le rôle et le nom accessibles adaptés au contenu.

## Critères de validation

Les scrollbars verticales et horizontales utilisent les mêmes tokens de contraste dans les deux thèmes, une piste transparente et un survol renforcé. `scrollbar-gutter: stable` réserve uniquement la place du défilement de la page. La compensation de marge de Radix est neutralisée quand ce mécanisme natif est disponible, afin que les menus et dialogues ne déplacent pas le contenu. La navigation fixe et le panneau mobile deviennent défilants seulement lorsque leur contenu dépasse la hauteur disponible. Les tableaux s'adaptent à leur conteneur ; un défilement résiduel reste accessible au clavier.

Les contrôles mesurent au moins 44 px sur petit écran ou pointeur tactile. Les champs tactiles utilisent une police d'au moins 16 px pour éviter le zoom automatique. Les états invalides restent visibles au survol ; les options et toggles sélectionnés conservent leur indication pendant le focus. `RemoteDataBoundary` garde les enfants et le focus pendant une actualisation et signale celle-ci par une bande fine, sans recouvrir les actions. Les animations respectent la préférence de mouvement réduit.

Pour un chargement de page entière ou de session, utiliser `RemotePageLoadingState` : il réserve la fenêtre visible pendant l'attente, afin que le pied de page ne saute pas à l'arrivée des données. Un panneau autonome conserve sa structure et ses libellés avec des `RemoteSkeleton` dans les emplacements de valeurs. Leur hauteur peut utiliser `1lh` pour correspondre exactement à la typographie responsive ; les actions différées réservent la hauteur d'un contrôle. Les états chargés ou vides conservent leur hauteur naturelle.

Ces critères décrivent les vérifications à effectuer, pas un compte rendu de tests :

- Examiner chaque pattern en thèmes clair et sombre, sur grand écran, tablette et mobile, ainsi que dans un conteneur étroit.
- Essayer noms courts et longs, suffixes numériques, UUID complets, plusieurs métadonnées et ensembles d'états. Toute information doit rester consultable.
- Vérifier l'absence de défilement horizontal de la page, la lisibilité de la dernière colonne et les libellés des cellules en présentation étroite.
- Ouvrir les menus et parcourir champs, options, radios et toggles au clavier ; vérifier focus, sélection, fermeture et accès aux contrôles suivants.
- Contrôler que les actions, filtres, données envoyées, messages d'état et états distants conservent leur comportement.
- Exécuter le typage, les tests de composants et les parcours fonctionnels concernés ; vérifier aussi le rendu compilé, car l'ordre CSS peut différer du développement.

Une correction de densité, retour à la ligne ou accent doit d'abord être portée par la primitive ou ses tokens. Un écran choisit une variante et organise son contenu ; il ne redéfinit pas son propre système visuel.
