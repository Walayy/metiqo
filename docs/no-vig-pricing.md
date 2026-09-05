# Probabilités implicites et no-vig

VAL-001 introduit la première brique du moteur de value sans la raccorder encore à une décision de
signal. Tous les calculs utilisent `Decimal` et refusent les `float`.

## Méthode proportionnelle MVP

Pour chaque cote décimale validée `O`, `implied_probability()` calcule la probabilité brute
`q = 1 / O`. La stratégie `proportional-v1` calcule ensuite l'overround comme la somme des
probabilités brutes et retourne `q / overround` pour chaque issue.

Le résultat conserve la version de stratégie, l'overround, les cotes d'origine et les deux
probabilités de chaque issue. La somme no-vig doit être égale à `1` dans la tolérance numérique
`1E-24` ; toute stratégie future est validée à cette même frontière.

## Domaine fermé

`NoVigMarket` exige le domaine canonique attendu et une cote unique par issue. Les domaines reconnus
sont équipe A/équipe B, équipe A/nul/équipe B et over/under ; mélanger des issues qui ne forment pas
un ensemble mutuellement exclusif et exhaustif est interdit. Une issue inattendue, une cote non finie
ou inférieure à `1`, un doublon ou un domaine de moins de deux issues est refusé avant calcul.

La stratégie proportionnelle exige que toutes les issues mutuellement exclusives et exhaustives
soient observées. Un marché incomplet lève `IncompleteMarketError`. L'interface de stratégie permet
une méthode future compatible avec les marchés partiels, mais cette capacité doit être déclarée
explicitement et son résultat doit toujours fournir une probabilité valide par cote et sommer à
`1`.
