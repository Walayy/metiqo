# Revue manuelle des mappings

MAP-004 transforme chaque décision `review` produite par `event-match-v1` en une tâche
persistée. La tentative et les scores candidats restent immuables ; seule la ligne de revue
porte l'état courant `pending`, `approved` ou `rejected`.

## Parcours opérateur

`GET /api/v1/admin/mappings/pending` retourne l'identité provider brute, les candidats
canoniques, chaque composante du score et le nombre de snapshots concernés. Une approbation
doit envoyer `candidateEventId`, `reviewer` et `reason`. Un rejet envoie uniquement le relecteur
et le motif. Les deux actions exigent une clé `Idempotency-Key`.

Une approbation rend l'historique provider consultable via l'identifiant de l'événement
canonique choisi. L'orientation A/B enregistrée avec le candidat est appliquée à la lecture.
Les snapshots, signaux et scores historiques ne sont ni modifiés ni supprimés.

## Alias daté

`POST /api/v1/admin/aliases` crée un alias manuel vers une équipe, une compétition ou un
joueur canonique existant. L'enregistrement conserve le provider, le libellé brut et normalisé,
`validFrom`, l'approbateur et le motif. La contrainte temporelle PostgreSQL refuse deux plages
actives qui se chevauchent pour la même identité provider.

## Audit et idempotence

Chaque approbation, rejet et création d'alias ajoute une ligne à `odds.mapping_audits`. Le
journal contient l'acteur, le motif, l'empreinte de la clé d'idempotence et un aperçu d'impact :
snapshots concernés, cible canonique, inversion éventuelle et zéro signal historique réécrit.
Un trigger interdit toute modification ou suppression d'une ligne d'audit.

Le rejeu exact d'une requête retourne la même ressource sans nouvelle écriture. La réutilisation
de la même clé avec une autre action ou une autre charge utile retourne un conflit.
