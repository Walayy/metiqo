# Frontière de flux de cotes licencié

`LicensedOddsFeedProvider` est une base abstraite. Metiquo ne livre actuellement
aucun fournisseur licencié concret, aucun transport présumé et aucune valeur
d'authentification.

## Configuration disponible

La configuration commune contient seulement :

- `provider_code`, l'identité logique stable du fournisseur ;
- `agreement_reference`, la référence interne du contrat ou de l'autorisation ;
- `rights_confirmed`, une confirmation explicite bloquante des droits d'usage.

Cette configuration est facultative tant qu'aucun adaptateur concret n'est installé.
Le produit conserve donc son fonctionnement normal en mode mock ou import manuel.

## Implémentation future

Un futur adaptateur ne pourra être ajouté qu'après validation du contrat et devra :

1. hériter de `LicensedOddsFeedProvider` et satisfaire le contrat `OddsProvider` ;
2. définir son transport à partir de la documentation officielle du fournisseur ;
3. charger toute authentification depuis le gestionnaire de secrets serveur, sans
   l'exposer dans les logs, les DTO ou la configuration commune ;
4. normaliser les événements, marchés, sélections et captures, avec une référence de
   provenance traçable ;
5. passer la suite de contrat réutilisable et des tests d'intégration enregistrés ;
6. documenter les droits de collecte, conservation et redistribution applicables.

Le choix `ODDS_PROVIDER` ne sera étendu qu'au moment où un adaptateur autorisé et testé
sera réellement livré. Il n'existe donc aucune activation implicite de cette frontière.
