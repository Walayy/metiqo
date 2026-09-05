# Gate des cotes résolues

MAP-006 ferme la phase P5 avec un parcours unique qui réutilise les services de capture,
de matching d'événement et de mapping de marché. Le gate ne calcule aucun prix : il remet
seulement un `ResolvedOddsContext` aux futurs services de pricing lorsque toutes les preuves
persistées sont présentes.

## Parcours autorisé

1. Le provider mock ou l'import manuel produit un événement, ses marchés et ses snapshots.
2. `OddsCaptureService` conserve les observations horodatées dans l'historique append-only.
3. `PostgresEventMatchingService` résout l'événement fournisseur vers un événement canonique.
4. Chaque marché capturé est projeté vers sa signature structurelle complète puis résolu par
   `PostgresMarketMappingService`.
5. `PostgresResolvedOddsGate` relit l'historique persistant et vérifie qu'il contient une
   observation horodatée, fiable et non informative avant d'autoriser le pricing.

Le marché provider doit désormais exposer explicitement l'unité et les politiques de remake,
forfait et annulation. Ces valeurs font partie du contrat commun, y compris pour l'import manuel,
et empêchent toute déduction à partir d'un simple libellé commercial.

## Fermeture par défaut

`require_pricing_ready()` refuse le passage avec des motifs stables lorsqu'un événement n'est pas
résolu, qu'au moins un marché est inconnu, que l'historique est vide ou que tous ses timestamps
sont non fiables. Une décision de revue ne publie donc jamais un identifiant canonique exploitable
par le pricing. Le rejeu d'un document identique relit les mêmes snapshots sans les mettre à jour
ni en créer de nouveaux.

La file de mapping de l'interface reste raccordée aux routes réelles : une revue peut être
approuvée ou rejetée et son audit est conservé, mais seule une nouvelle évaluation entièrement
résolue pourra franchir ce gate.
