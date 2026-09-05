# Calcul de value

VAL-002 compare une probabilité modèle à une cote bookmaker déjà normalisée par VAL-001. Le
résultat reste un calcul numérique : les seuils, grades et décisions de publication appartiennent
aux tickets suivants.

Pour une probabilité centrale `p`, sa borne basse `p_low`, la probabilité bookmaker no-vig
`p_book` et la cote offerte `O`, `value-pricing-v1` applique :

```text
fair_odds = 1 / p
edge = p - p_book
EV = p * O - 1
EV_conservative = p_low * O - 1
```

La borne basse doit appartenir à `[0, p]`. Tous les calculs utilisent `Decimal` avec une précision
locale fixe et la version de politique est conservée dans le résultat.

## Limites numériques

Pour `p = 0`, la cote juste mathématique est non bornée : `fair_odds` vaut donc `None` et
`fair_odds_unbounded` vaut `true`, sans produire de valeur infinie sérialisable. L'EV et l'EV
prudente valent alors `-1` lorsque la borne basse vaut également zéro.

Pour `p = 1`, la cote juste vaut exactement `1`. Edge et EV restent calculés par les mêmes formules.
Une cote juste absente pourra ainsi devenir une abstention explicite plutôt qu'un nombre arbitraire
dans le futur gate de publication.
