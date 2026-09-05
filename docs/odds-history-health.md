# Santé fournisseur et historique des cotes

Chaque appel à `OddsCaptureService.capture_event` écrit un contrôle de santé dans
`odds.provider_health`. Une capture réussie conserve son instant de succès. Un échec
ajoute un état `degraded` lorsqu'un historique valide existe déjà, ou `unavailable`
avant le premier succès. L'erreur est propagée à l'appelant, mais aucune observation
existante n'est modifiée ni supprimée.

`GET /api/v1/admin/data-sources` réunit la source historique Oracle's Elixir et les
fournisseurs présents dans `odds.providers`. Chaque fournisseur de cotes expose :

- `lastCaptureAt`, l'instant de la dernière observation enregistrée ;
- `ageSeconds`, son âge à l'instant du contrôle ;
- `failureCount`, le nombre de contrôles dégradés ou indisponibles ;
- `freshness`, calculée avec `ODDS_PROVIDER_MAX_AGE_SECONDS` puis
  `ODDS_MAX_AGE_SECONDS`.

Une source opérationnelle passe de `fresh` à `stale` lorsque son âge dépasse le SLA.
Après un échec, un historique encore disponible est signalé `degraded` et reste
lisible. Sans capture, la fraîcheur est `failed`.

## Lecture de l'historique

`GET /api/v1/events/{eventId}/odds-history` lit les observations PostgreSQL dans
l'ordre de capture. La réponse reconstruit les identités événement, marché et
sélection, la cote décimale, la probabilité implicite brute, les états, l'âge et la
provenance. Les métadonnées utilisent la dernière capture comme `asOf` et reflètent
la fraîcheur courante du fournisseur.

Tant que le mapping canonique n'est pas encore résolu, seules les observations dont
l'identifiant événement correspond à l'événement demandé apparaissent. Le ticket de
mapping suivant étend cette résolution sans changer le contrat de lecture.
