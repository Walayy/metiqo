# Gate P6 — décision de value persistée

`PostgresValuePipeline` reçoit les UUID d'une cote, des deux tentatives de mapping,
d'une prédiction facultative et la version d'une politique. Il relit leurs preuves
PostgreSQL et choisit le résultat ; l'appelant ne transmet ni grade, ni probabilité,
ni état de fraîcheur.

Le parcours relie la capture manuelle ou licenciée, le mapping événement/marché,
la prédiction immuable, le retrait de marge, la value, les gardes et les lectures
API/UI réelles. La version `value-pipeline-v1` produit `VALUE` quand tous les gardes
passent, `NO_EDGE` pour un écart financier insuffisant et `BLOCKED` pour une cause
de qualité. Elle ne définit pas de seuil supplémentaire pour `STRONG_VALUE` ou
`WATCH` : leur émission nécessitera une politique de classement versionnée.

## Preuves et temporalité

La politique, le modèle, les capacités source et les mappings doivent être connus
au moment de la décision. Le cutoff des features ne peut pas dépasser la capture.
Les deux issues utilisées pour le retrait de marge doivent provenir du même marché,
du même document et du même instant de capture. Les sélections inversées sont
réorientées à partir du mapping enregistré. Une observation plus récente empêche
d'admettre une ancienne cote lors d'une nouvelle décision.

La fraîcheur OE est calculée depuis le catalogue, le snapshot courant et les
incidents. Le modèle doit encore être champion et toutes les capacités requises
doivent être activées. Le raccord actuel accepte un marché de game correspondant
à son numéro canonique, ou une série BO1 ; il bloque une application directe de la
probabilité de game à une série BO3/BO5.

`signals.value_evaluations` conserve toutes les décisions, y compris un mapping
ambigu sans prédiction associable. La preuve contient les snapshots cotés utilisés,
leurs empreintes, les capacités, la fraîcheur source, la politique résolue et la
version du moteur. Le signal et son évaluation sont publiés dans la même transaction.
Un rejeu exact conserve les UUID ; une nouvelle décision ajoute une ligne.

Les refus stale et suspended conservent leurs métriques en diagnostic dans l'API
et la fiche signal. Les refus avant calcul n'inventent aucun prix : ils restent
dans le journal d'évaluations et, pour les mappings ambigus, dans la file de revue.

## Commandes

Avec `APP_DATA_MODE=real`, un provider non mock et `DATABASE_URL` configurés :

```sh
make value-evaluate ODDS_SNAPSHOT=<uuid> EVENT_MAPPING=<uuid> MARKET_MAPPING=<uuid> POLICY=<version> PREDICTION=<uuid> JSON=1
make test-value
```

`PREDICTION` est facultatif pour conserver un refus en amont du modèle. La commande
retourne l'UUID d'évaluation, l'éventuel signal, le grade et les motifs. Une abstention
est un résultat métier réussi, donc un code de sortie zéro. Une référence invalide
est une erreur. `make test-value` exige une base PostgreSQL de test jetable via
`TEST_DATABASE_URL` ; ses fixtures remettent cette base à zéro.

## Référence numérique

L'exemple SFG à cotes `4,00 / 1,25`, probabilité `0,30` et borne basse `0,27` donne
`p_book = 5/21`, cote juste `10/3`, edge `13/210`, EV `0,20` et EV prudente `0,08`.
Les tests numériques existants couvrent cet exemple à la main.

La fixture du parcours complet utilise les cotes `1,10 / 8,00` et un outsider
de probabilité `0,40`, borne basse `0,154268`. Elle donne `p_book = 11/91`, cote juste
`2,50`, EV `2,20` et EV prudente `0,234144`. Ce scénario synthétique vérifie les
formules et le câblage ; il ne constitue ni un signal réel, ni une preuve de performance.
Une EV positive ne garantit aucun gain.
