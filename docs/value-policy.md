# Politiques de seuils de value

VAL-003 remplace une configuration de seuils anonyme par une politique immuable et versionnée.
Chaque `Value` exposée dans un signal contient désormais `policyVersion` afin que la décision puisse
être reproduite après un changement de configuration.

## Seuils et résolution

Une version contient `min_edge`, `min_ev`, `min_conservative_ev`, `max_odds_age_seconds` et
`min_mapping_confidence`. Les valeurs globales peuvent être remplacées par trois niveaux de
surcharge, appliqués dans cet ordre :

1. type de marché ;
2. compétition ;
3. bucket de cote ou de risque.

Le niveau le plus tardif gagne uniquement pour les champs qu'il renseigne. Le résultat conserve la
version et la liste ordonnée des scopes appliqués. Une clé bucket vide ou dupliquée après
normalisation est refusée.

## Protection du test final

Chaque version conserve `tuned_through` et `final_test_starts_at`. Le premier instant doit précéder
strictement le second, dans le domaine Python comme dans PostgreSQL. Une politique réglée sur une
observation de la fenêtre de test finale ne peut donc pas être enregistrée.

## Persistance et audit

`signals.value_policies` conserve les seuils, surcharges, bornes temporelles et une empreinte
SHA-256 canonique. Une même version et un même contenu sont idempotents ; redéfinir une version est
interdit. Après la version initiale, chaque nouvelle version doit référencer sa précédente.

`signals.value_policy_audits` ajoute une entrée `policy.created` ou `policy.revised` avec acteur,
motif, version précédente et document complet. Les deux tables sont protégées par des triggers
append-only contre toute mise à jour ou suppression.
