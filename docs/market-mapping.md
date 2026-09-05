# Mapping canonique des marchés

MAP-005 sépare le libellé affiché par un provider de la structure utilisable par un plugin de
marché. Le texte brut est conservé pour l'audit, mais il ne participe jamais à la décision.

## Signature exigée

Un marché n'est résolu que si sa référence de règlement existe, est active et correspond
exactement aux dimensions suivantes :

- type canonique et période de série ou de game ;
- présence ou absence d'une ligne et unité ;
- nombre et ensemble exacts des issues, y compris `DRAW` ;
- politiques explicites pour remake, forfait et événement annulé.

La référence versionnée décrit également les issues canoniques autorisées. Un marché binaire et
un marché à trois issues utilisent donc deux références distinctes. `MATCH_WINNER` refuse toute
ligne ; les futurs marchés à ligne devront posséder leur propre règle avant activation.

## Fermeture par défaut

Une référence absente, inconnue ou inactive, un type non pris en charge ou la moindre divergence
structurelle produit le statut `unknown`. `require_mapped()` refuse alors de fournir une structure
canonique : le marché ne peut atteindre ni prédiction ni pricing.

Chaque tentative ajoute une ligne à `odds.market_mapping_attempts`. Pour un marché inconnu, la
ligne conserve le descripteur provider complet en JSON, le libellé séparé et le motif de refus,
sans inventer de type, de période ou de règle canonique. Les règles et les tentatives sont
append-only et protégées contre les mises à jour et suppressions.
