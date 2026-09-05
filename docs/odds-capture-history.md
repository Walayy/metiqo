# Capture et historique des cotes

`OddsCaptureService` transforme une capture `OddsProvider` en une transaction
PostgreSQL unique. Il relie successivement le fournisseur, l'événement, le marché et
la sélection avant d'ajouter les snapshots dans `odds.snapshots`.

Les identités externes sont stables par fournisseur. Un identifiant de marché déjà au
format UUID est conservé ; sinon, Metiquo en dérive un de façon déterministe. Les
adaptateurs manuels et les futurs adaptateurs partagent le même utilitaire.

## Historisation

Chaque observation conserve la cote, les états fournisseur/événement/marché, la
ligne, le libellé de sélection, l'instant de capture, la fiabilité temporelle, la
référence du payload et sa provenance. Son empreinte SHA-256 canonique rend le rejeu
exact idempotent.

Une confirmation doit posséder son propre identifiant immuable et son instant de
capture. Elle est ajoutée même si la cote est identique. Un changement de cote,
d'état, de ligne ou de libellé produit lui aussi une nouvelle observation. Les
triggers append-only du schéma interdisent ensuite toute modification ou suppression
de l'historique.

Metiquo conserve actuellement chaque confirmation physique. La déduplication d'un
intervalle identique reste optionnelle et n'est pas appliquée, afin de ne perdre
aucune borne temporelle observée.

## Transaction et erreurs

La capture entière est validée avant ouverture de la transaction. Un fournisseur,
événement, marché ou sélection incohérent fait échouer l'opération sans publication
partielle. Un payload doit fournir une référence non vide et peut fournir son SHA-256
exact. Une capture future ou vide est refusée.
