# Persistance immuable des signaux

`signals.signals` conserve une décision de pricing comme une preuve, et non comme un état
courant à corriger. Une ligne référence le snapshot de cote, la prédiction pré-match, la
tentative de résolution d'événement et la version de politique effectivement utilisées. Elle
enregistre également l'instant de calcul, la sélection canonique, la cote offerte, les trois
bornes du modèle, les métriques de value, la fraîcheur, la confiance de mapping, le grade et
les motifs d'abstention.

## Invariants à l'insertion

Le repository recharge les sources PostgreSQL avant toute écriture. Il refuse notamment :

- une sélection ou une cote qui ne correspond pas au snapshot ;
- un mapping qui ne relie pas l'événement fournisseur à l'événement de la prédiction ;
- une inversion A/B qui n'a pas été appliquée à la sélection ;
- une confiance différente du score de la tentative, ou un âge différent de l'écart entre
  `captured_at` et `computed_at` ;
- une probabilité centrale ou basse différente de la prédiction immuable ;
- une politique absente, une value admise issue d'une prédiction désactivée, ou un signal
  calculé après le début de l'événement.

Les mêmes relations sont contrôlées par un trigger PostgreSQL. Cette seconde frontière empêche
une écriture SQL directe de contourner les preuves applicatives. Une résolution automatique ou
une revue explicitement approuvée est acceptée ; le score et l'orientation du candidat retenu
restent ceux de la tentative référencée.

## Idempotence et reproduction

Les primitives persistées sont sérialisées canoniquement puis condensées dans un SHA-256. Cet
empreinte unique produit aussi l'UUID déterministe du signal : rejouer exactement la même
publication retourne la ligne existante. Un changement de cote, de décision ou d'instant crée
un nouveau signal.

`PostgresSignalRepository.reproduce()` recharge les références immuables, recalcule la
probabilité implicite, la cote juste, l'edge, l'EV et l'EV prudente, puis vérifie l'âge, la
confiance et l'empreinte du contenu. Les grades `VALUE`, `STRONG_VALUE` et `WATCH` n'acceptent
aucun motif ; `NO_EDGE` et `BLOCKED` exigent au moins une raison structurée. Une abstention sans
calcul ne peut être que `BLOCKED`.

## Absence de réécriture

Un trigger rejette tout `UPDATE` et tout `DELETE`, y compris après publication du résultat de
l'événement. Il n'existe pas de mutation métier ni de voie administrative silencieuse. Une
correction doit publier une nouvelle ligne avec ses nouvelles preuves ; l'ancienne reste
consultable pour les paper bets et les audits historiques. Les prédictions référencées sont
déjà soumises à la même règle append-only dans `ml.prematch_predictions`.
