# Performance des lectures API

QA-001 mesure les routes réelles via ASGI, avec PostgreSQL dans Docker et les DTO
de production. Le scénario exclut le réseau externe, HTTPS et le rendu navigateur.
Les p95 sont inférieurs à 300 ms sur la machine de référence. La portée de cette
mesure est le volume synthétique décrit ici ; une augmentation importante du
volume ou un changement de matériel demande une nouvelle mesure.

## Reproduction

`make benchmark-reads` utilise `TEST_DATABASE_URL` pour créer une nouvelle base
`metiquo_perf_<uuid>`, applique les migrations, construit les fixtures puis supprime
cette base et ses objets temporaires, même en cas d'échec. Le compte PostgreSQL
doit pouvoir créer une base. La base désignée dans l'URL sert à la connexion
d'administration et n'est pas réinitialisée.

Le programme conserve un rapport et les plans `EXPLAIN (ANALYZE, BUFFERS, FORMAT
JSON)` dans `data/performance/<horodatage-uuid>`. Il retourne 1 si une route ne
répond pas 200, si son p95 atteint 300 ms ou si les sources changent pendant la
mesure. Cinq requêtes d'échauffement précèdent les 100 mesures de chaque route ;
le quantile utilise le rang supérieur. Les plans sont exécutés après les mesures.
Lancer le benchmark sans autre suite de tests ou construction d'images en parallèle.

## Machine et scénario du 7 septembre 2026

- Windows, processeur AMD 5600X, 6 cœurs et 12 threads, 32 Gio de RAM.
- Docker Linux : 12 CPU disponibles et environ 15,6 Gio de RAM ; PostgreSQL 18.4.
- Python 3.13.14 ; les versions exactes et les empreintes sont dans le rapport.
- 1 002 séries, 1 001 modèles, 1 100 signaux, 100 entrées paper, 1 002 runs
  d'ingestion, 1 000 anomalies, 1 001 jobs et 150 fournisseurs.
- Les données sont des fixtures de capacité. Les clones conservent les références
  requises pour les lectures ; ils ne prouvent ni la qualité des modèles ni une
  performance financière. Les rapports financiers sont calculés avant les mesures,
  puis lus depuis leur stockage immuable.

Les [mesures brutes](evidence/qa-001/report.json) et les
[plans SQL](evidence/qa-001/plans.json) sont archivés. Le rapport identifie le commit
de base OPS-010 et l'empreinte des sources QA-001 modifiées effectivement mesurées.

| Route, page de 20 sauf indication     | p50 (ms) | p95 (ms) | Requêtes SQL |
| ------------------------------------- | -------: | -------: | -----------: |
| Événements                            |    40,32 |    45,95 |           15 |
| Opportunités                          |    70,84 |   126,74 |            3 |
| Modèles                               |    16,56 |    18,08 |            4 |
| Backtests                             |    17,31 |    18,78 |            4 |
| Paper bets                            |    21,29 |    26,93 |            4 |
| Métriques paper, rapport déjà calculé |    28,84 |    36,28 |            2 |
| Sources                               |    49,85 |    54,38 |           24 |
| Ingestions                            |    38,09 |    47,90 |           16 |
| Anomalies                             |    41,66 |    46,45 |           15 |
| Jobs                                  |    40,67 |    46,65 |           15 |
| Audit                                 |    65,21 |    70,70 |           15 |
| État système                          |    27,29 |    33,56 |           17 |

Les comptes incluent la liaison du contexte d'audit SQL et, lorsque la route les
expose, les lectures de santé. Ils restent constants sur toutes les répétitions.
Les tests comparent aussi un fournisseur à cinquante et un signal à cinquante et
un : le nombre de requêtes reste identique.

## Lectures et plans

Les événements historiques sont projetés par une union SQL des séries et des
games hors série. Les signaux joignent cette projection dans leur propre requête.
Les filtres et limites s'appliquent avant la construction des DTO ; `%` et `_`
sont traités comme des caractères littéraux dans la recherche utilisateur.
Le total est conservé lorsqu'un offset dépasse la dernière page. Les comptes et
la page partagent une transaction de lecture répétable.

Les historiques d'ingestion, les anomalies, les modèles, les backtests et la file
de mapping sont paginés dans PostgreSQL. La file charge uniquement les événements
de ses candidats. L'historique de cotes renvoie les captures les plus récentes
en premier ; le graphe remet sa tranche reçue dans l'ordre chronologique.
Les changements de schéma utilisent les empreintes et la fenêtre SQL de l'historique.
Une période de modèle réduite à un instant ou terminée après son enregistrement
reste sans projection de backtest ; ses dates ne sont pas modifiées pour en créer une.

Le plan le plus coûteux observé concerne la page d'audit : 27,14 ms d'exécution SQL.
La page des opportunités prend 4,61 ms côté PostgreSQL. Les plans utilisent
notamment `ix_ops_audit_target`, `pk_ingestion_runs`, `pk_ml_model_versions` et
`uq_ml_model_versions_champion_scope`. Les petits ensembles utilisent des scans
séquentiels et des tris bornés. Ces mesures ne justifient pas de nouvel index ;
la migration reste inchangée. Les coûts réseau et de sérialisation font partie du
temps HTTP mesuré, au-delà du temps SQL indiqué par le plan.
