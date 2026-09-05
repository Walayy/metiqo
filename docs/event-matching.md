# Matching des événements fournisseur

`EventMatchingScorer` compare un événement fournisseur aux événements canoniques sans
rapprochement flou. La version initiale `event-match-v1` pondère les composantes ainsi :

- équipes : `0,60` ;
- heure de début : `0,20` ;
- compétition : `0,15` ;
- format : `0,05`.

Les équipes correspondent par égalité typographique exacte ou par alias fournisseur
approuvé et valide à l'heure de l'événement. L'ordre direct et l'ordre inversé sont
évalués ; une inversion retenue échange ensuite `TEAM_A` et `TEAM_B`. Un seul participant
reconnu vaut `0,50` sur la composante équipes. La compétition exige également une égalité
typographique exacte. Le format vaut `1` uniquement lorsque le `bestOf` fournisseur est
présent et identique.

La composante horaire vaut `1` jusqu'à cinq minutes d'écart, `0,75` jusqu'à trente
minutes, `0,25` jusqu'à deux heures, puis `0`.

## Décision fermée

- score supérieur ou égal à `0,95` : `auto_matched` ;
- score de `0,75` inclus à moins de `0,95` : `review` ;
- score inférieur à `0,75` : `rejected`.

Deux candidats séparés par `0,05` ou moins passent en revue, même si le premier dépasse
le seuil automatique. Les participants `TBD`, `Winner of`, `Loser of` et `To be
determined` sont rejetés avant scoring. Une décision en revue ou rejetée n'expose aucun
identifiant canonique et refuse tout remapping de sélection ; elle ne peut donc pas être
utilisée par une prédiction.

## Audit PostgreSQL

`PostgresEventMatchingService` exige que l'événement fournisseur ait d'abord été capturé.
Il charge les alias datés puis ajoute une ligne dans `odds.event_mapping_attempts` et une
ligne par candidat dans `odds.event_mapping_candidate_scores`. Statut, motif, version des
poids, score total, orientation et quatre composantes sont conservés. Les deux tables sont
append-only.

Une résolution automatique relie aussi la lecture
`GET /api/v1/events/{eventId}/odds-history` à l'identité fournisseur. L'API restitue alors
l'identifiant canonique et applique l'éventuelle inversion des sélections sans modifier
les observations brutes.
