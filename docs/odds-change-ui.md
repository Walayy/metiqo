# Changement de cote dans l'interface

Le dashboard actualise les opportunités et leurs historiques toutes les 30 secondes. La santé
des sources, moins sensible à la seconde, est vérifiée toutes les 60 secondes. React Query
conserve la réponse précédente pendant chaque refetch : le tableau ou les cartes restent montés,
et l'indicateur de chargement n'efface jamais les lignes consultables.

## Deux prix, deux responsabilités

La cote principale d'une ligne et de sa fiche provient toujours du snapshot lié au `signalId`.
Une observation plus récente du même marché et de la même sélection est affichée séparément sous
le libellé **Cote mise à jour**. Elle ne remplace ni la cote, ni les probabilités, ni l'edge, ni
l'EV du signal existant.

Le rapprochement d'historique exige le même `marketId` et la même `selection`. Une cote d'un autre
marché de l'événement ne peut donc pas déclencher un faux changement. La fiche détail charge le
signal et son explication comme des ressources immuables par identifiant ; seul l'historique coté
est actualisé périodiquement. Si le pipeline recalcule après une nouvelle cote, la persistance append-only de
`VAL-006` et la projection de `VAL-007` font apparaître un nouveau signal dans la liste.

## Audit visuel

La table d'historique marque explicitement le **Snapshot du signal** et la **Dernière cote**. Une
fiche déjà ouverte reste donc reproductible, tandis que l'utilisateur voit qu'une décision plus
récente peut exister. Les tests Playwright couvrent le scénario mock de baisse de `4,20` à `3,60`,
la conservation du nœud de ligne pendant un polling bloqué et la présence simultanée des deux
repères dans la fiche.
