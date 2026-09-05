# Fraîcheur et admissibilité des marchés

`MarketAdmissibilityGate` s'exécute avant tout calcul de signal. Une décision bloquée
reste une abstention structurée ; elle ne peut pas devenir publiable par défaut.

## Politique de fraîcheur

`ODDS_MAX_AGE_SECONDS` définit le SLA global. Trois dictionnaires JSON facultatifs
peuvent le surcharger :

- `ODDS_PROVIDER_MAX_AGE_SECONDS` par code fournisseur ;
- `ODDS_MARKET_MAX_AGE_SECONDS` par type de marché ;
- `ODDS_PHASE_MAX_AGE_SECONDS` par phase.

La résolution applique la priorité fournisseur, puis marché, puis phase, puis valeur
globale. Chaque durée doit être strictement positive. Une cote reste fraîche à la
borne exacte et devient stale dès qu'elle la dépasse.

## Blocages

Une décision est refusée si la capture est stale ou future, si les snapshots mélangent
plusieurs événements ou marchés, si l'événement pré-match a commencé, si le marché
n'est pas `open`, si la sélection demandée manque ou si les issues requises par le
retrait de marge sont incomplètes. Une capture marquée informative ne produit jamais
de signal validé.

Une stratégie future explicitement compatible avec un marché partiel pourra désactiver
le contrôle de complétude. Ce choix est explicite dans la requête ; il n'est jamais
déduit silencieusement.

La phase `live` reste hors du MVP et retourne toujours
`LIVE_BETTING_OUT_OF_SCOPE`, même si une durée de fraîcheur lui est configurée.
