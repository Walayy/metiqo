# Opportunités réelles

Les routes réelles `/api/v1/opportunities`, `/api/v1/opportunities/{signalId}` et
`/api/v1/opportunities/{signalId}/explanation` projettent directement les preuves append-only de
`signals.signals`. Elles utilisent exactement le même contrat `Opportunity` que le catalogue
mock.

## Liste et filtres

La liste normale ne contient que les grades publiables `STRONG_VALUE`, `VALUE` et `WATCH`. Son
tri par défaut est l'EV prudente décroissante, puis l'instant de calcul décroissant et
l'identifiant stable. `NO_EDGE` et `BLOCKED` ne sont donc pas comptés comme opportunités. Ils
restent consultables lorsqu'un écran diagnostic demande explicitement l'un de ces grades ; une
abstention intervenue avant tout calcul n'est pas transformée artificiellement en `Value` et
reste hors de ce DTO.

Les filtres partagés avec le mock couvrent compétition, équipe, type de marché, grade, edge
minimal, EV minimale, confiance minimale, fraîcheur et fenêtre de début. `offset` et `limit`
s'appliquent après les filtres, et `page.total` compte la collection filtrée avant pagination.

## Composition du DTO

Chaque objet rassemble :

- l'événement canonique de la prédiction et le marché du snapshot ;
- le snapshot exact, sa cote, sa provenance, sa probabilité implicite et la probabilité no-vig ;
- la prédiction, son intervalle, son cutoff, sa confiance, sa couverture et sa distance au
  domaine d'entraînement ;
- la politique, la cote juste, l'edge, l'EV, l'EV prudente et le grade conservés par le signal ;
- la confiance de mapping, la fraîcheur, le statut du modèle et les abstentions ;
- des métadonnées `dataMode=real`, `asOf` égal à la capture et `computedAt` égal au calcul.

La migration `20260908_0034` ajoute les deux diagnostics ML à chaque nouvelle prédiction. Le
trigger d'insertion les rend obligatoires sans inventer de valeur pour les lignes historiques :
un ancien signal incomplet n'est pas exposé avant recalcul. La référence d'explication inclut
l'empreinte du signal ; l'explication d'une décision bloquée restitue ses codes structurés,
tandis qu'une décision publiable cite la politique, la prédiction et le snapshot exacts.
