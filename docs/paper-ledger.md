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

Le moteur `GameWinnerSettlementEngine` interprète les résultats game winner. Il exige une source validée et connue à l'instant du calcul, la bonne game ou une série BO1, des règles enregistrées et deux résultats d'équipes complémentaires. Chaque exception remake, forfait ou annulation applique `settle`, `void` ou `review` selon sa règle ; des drapeaux contradictoires restent en revue. La décision conserve les empreintes du résultat, de la règle et du moteur et produit la même empreinte lors d'un replay. Le chargement réel des preuves OE et la persistance automatique des règlements sont raccordés par PAP-005.

`SeriesWinnerSettlementEngine` vérifie le score terminal des BO1, BO3 et BO5. Les formats pairs BO2 et BO4 exigent toutes les games et un marché explicite à trois issues avec nul. Le vainqueur canonique doit correspondre au score ; aucune issue n'est déduite d'un résultat core marqué non résolu. Un score impossible, non terminal, un format modifié ou une série écourtée restent en revue. Une annulation peut produire un void uniquement avec la règle référencée correspondante et une preuve source validée.

Le job `PostgresPaperSettlementService` charge les résultats, les snapshots et les règles directement depuis PostgreSQL. La création paper fige désormais les équipes, le format et l'horaire attendus dans `eventProof`. Une décision ancienne sans cette preuve reste en revue. Le job vérifie la fraîcheur OE, la cohérence des équipes et des sources, l'arrivée de la preuve après la fin de la game, puis attend `PAPER_SETTLEMENT_DELAY_SECONDS` après la fin ou le traitement du résultat, selon l'instant le plus tardif. Les empreintes des lignes et la révision canonique sont conservées avec le règlement.

```console
make paper-settle JSON=1
uv run --frozen oe paper-settle --paper-bet <uuid> --json
```

Le lot traite jusqu'à 100 décisions ouvertes ou en revue. Les erreurs de connexion, deadlocks et échecs de sérialisation sont repris jusqu'à `PAPER_SETTLEMENT_MAX_ATTEMPTS`, trois par défaut et cinq au maximum ; les autres erreurs ne sont pas rejouées. Le rapport expose les identifiants en échec et la CLI renvoie un code non nul si le lot en contient. Un replay identique ne duplique pas le règlement. Les créations et règlements utilisent le même verrou de bankroll par devise.

Un règlement définitif reste figé lors des passages automatiques. Une correction nécessite `--paper-bet`, `--correction-reason`, un acteur identifiable et, pour un replay explicite, `--idempotency-key`. Elle recalcule le résultat OE et ajoute une révision ; aucun montant ni statut gagnant ne peut être fourni manuellement à la commande. Le parcours intégré couvre une série BO1 issue du modèle game winner ; le gate P6 continue de refuser de transformer sa probabilité de game en probabilité BO3.
