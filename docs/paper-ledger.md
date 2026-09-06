# Ledger de paper trading

`signals.paper_bets` conserve une décision fictive par signal. La cote d'entrée est celle du snapshot exact de ce signal, avec la prédiction, le modèle, la politique et les règles versionnées. Une évaluation P6 admise est requise. Une cote sans timestamp fiable, une décision après le début de l'événement ou une divergence de références est refusée par PostgreSQL.

Le montant et la devise sont explicites ; aucune mise réelle n'est exécutée. `PostgresPaperService` crée manuellement les entrées avec `PaperBankrollPolicy`. Les variables `PAPER_BANKROLL_*` et `PAPER_MAX_OPEN_EXPOSURE` configurent le capital initial fictif, sa devise et l'exposition ouverte maximale. Le capital initial ne peut plus changer après la première entrée ; changer un paramètre de configuration ne crédite donc pas le compte.

La création relit la décision P6 et réévalue ses preuves à l'instant de l'entrée dans la même transaction. Si la cote a changé, est périmée, si le modèle est retiré ou si une autre condition d'admission échoue, l'entrée est refusée. Une entrée réussie conserve le signal demandé et référence aussi cette nouvelle évaluation. Les deux signaux historiques restent immuables. Les grades `WATCH`, `NO_EDGE` et `BLOCKED` ne permettent aucune création automatique ni suggestion de mise.

Le disponible est `capital initial + P&L courant − mises ouvertes`. Une révision de règlement est comptée une seule fois, les positions `pending_review` restent exposées et les créations concurrentes se sérialisent par devise. Une seule entrée est autorisée par signal. Un replay de la clé avec le même montant et acteur retourne la réponse d'origine, même si l'événement a commencé depuis ; un autre payload ou une seconde clé pour le même signal provoque un conflit.

Après configuration du mode réel et de PostgreSQL, l'opération manuelle est disponible ainsi :

```console
uv run --frozen oe paper-create --signal <uuid> --stake 10 --currency EUR --idempotency-key entree-001 --actor operateur --json
```

Le montant reste entièrement saisi par l'opérateur. L'auto-paper et la suggestion Kelly ne sont pas activés. Les API et écrans réels arrivent dans PAP-009.

`signals.settlements` conserve les tentatives et corrections successives. L'absence de règlement représente `open`. Un résultat ambigu est `pending_review` sans P&L. Un règlement définitif exige un snapshot OE validé connu à l'instant du règlement ; le plugin doit encore valider son contenu et ses règles dans PAP-003 à PAP-005.

Chaque correction référence la révision précédente, un acteur, un motif et des preuves. Le verrou sur le pari sérialise les révisions. La décision initiale, les pertes et les anciens règlements restent présents : `UPDATE` et `DELETE` sont interdits sur les deux tables. La lecture courante utilise la dernière révision sans effacer les précédentes.

Le P&L vaut `stake × (entry_odds − 1)` pour un gain, `−stake` pour une perte et zéro pour un push ou un void, arrondi à huit décimales. Le trigger contrôle ce calcul. Les empreintes d'idempotence et de requête permettent aux services de distinguer un replay d'une clé réutilisée avec d'autres paramètres.

Les tests `tests/integration/test_paper_ledger.py` insèrent directement en SQL afin de prouver les contraintes indépendamment de la couche applicative. Ils couvrent une cote non horodatée, un prix forgé, une source en quarantaine, la chronologie, les montants non finis et une correction qui préserve la perte d'origine. Les données de ces tests sont synthétiques et ne constituent pas un historique financier réel.
