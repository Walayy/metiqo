# Fixtures Oracle’s Elixir

Toutes les lignes CSV de ce dossier sont synthétiques et minimisées pour les tests Metiquo. Elles ne recopient aucune ligne de match ni donnée personnelle provenant d’Oracle’s Elixir. Leur usage de test est autorisé sous la licence du dépôt.

La couverture SFG §25.2 est la suivante :

- valide : `dq_valid.csv` ;
- colonne additive : `schema_additive.csv` ;
- colonne cœur manquante : `schema_missing_core.csv` ;
- ligne dupliquée : `duplicate.csv` ;
- game incomplète : `incomplete_game.csv` ;
- remake : `remake.csv` ;
- changement rétroactif : `retro_before.csv` et `retro_after.csv` ;
- fichier tronqué : `truncated.csv` ;
- page HTML de quota : `quota.html` ;
- BOM UTF-8 et séparateur point-virgule : `encoding_delimiter_surprise.csv.base64` ;
- archive gzip corrompue : `corrupted_archive.gzip.base64`.

Les deux fixtures binaires sont versionnées en Base64 pour rester inspectables et portables dans Git. Les tests les décodent avant validation.

`historical_observation.json` conserve l’empreinte et la taille réellement observées pour la fixture valide à la date indiquée. Cette observation est une preuve historique uniquement : le transport recalcule toujours le SHA-256 et la taille des octets courants, et ne l’utilise jamais comme empreinte attendue d’un nouveau téléchargement.
