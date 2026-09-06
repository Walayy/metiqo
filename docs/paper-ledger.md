# Ledger de paper trading

`signals.paper_bets` conserve une décision fictive par signal. La cote d'entrée est celle du snapshot exact de ce signal, avec la prédiction, le modèle, la politique et les règles versionnées. Une évaluation P6 admise est requise. Une cote sans timestamp fiable, une décision après le début de l'événement ou une divergence de références est refusée par PostgreSQL.

Le montant et la devise sont explicites ; aucune mise réelle n'est exécutée. La configuration de bankroll et les contrôles à la création appartiennent à PAP-002.

`signals.settlements` conserve les tentatives et corrections successives. L'absence de règlement représente `open`. Un résultat ambigu est `pending_review` sans P&L. Un règlement définitif exige un snapshot OE validé connu à l'instant du règlement ; le plugin doit encore valider son contenu et ses règles dans PAP-003 à PAP-005.

Chaque correction référence la révision précédente, un acteur, un motif et des preuves. Le verrou sur le pari sérialise les révisions. La décision initiale, les pertes et les anciens règlements restent présents : `UPDATE` et `DELETE` sont interdits sur les deux tables. La lecture courante utilise la dernière révision sans effacer les précédentes.

Le P&L vaut `stake × (entry_odds − 1)` pour un gain, `−stake` pour une perte et zéro pour un push ou un void, arrondi à huit décimales. Le trigger contrôle ce calcul. Les empreintes d'idempotence et de requête permettent aux services de distinguer un replay d'une clé réutilisée avec d'autres paramètres.

Les tests `tests/integration/test_paper_ledger.py` insèrent directement en SQL afin de prouver les contraintes indépendamment de la couche applicative. Ils couvrent une cote non horodatée, un prix forgé, une source en quarantaine, la chronologie, les montants non finis et une correction qui préserve la perte d'origine. Les données de ces tests sont synthétiques et ne constituent pas un historique financier réel.
