# Métriques du ledger observé

`make paper-report CURRENCY=EUR JSON=1` calcule hors requête web un rapport matérialisé, conservé dans `signals.financial_reports`. Le service relit dans une transaction cohérente les décisions paper, leurs cotes d'entrée observées, les derniers règlements connus et les proxies de clôture. Une devise constitue un rapport séparé. Une provenance de cote absente, informative, non horodatée ou enregistrée après l'entrée interdit le calcul.

Les fixtures synthétiques vérifient les formules et le parcours technique. Elles ne constituent ni une performance réelle ni un backtest financier à partir des seules données Oracle's Elixir. Sans décisions issues de captures observées, aucun ROI numérique n'est publié.

La méthode `paper-finance-v1` utilise les conventions suivantes :

- Le turnover comprend toutes les mises ; le turnover réglé exclut les décisions ouvertes, en revue et les voids. Le ROI et le yield sont le P&L net divisé par ce turnover réglé, sans annualisation.
- Le hit rate porte sur gains et pertes et s'accompagne de la cote moyenne et du nombre de décisions. Les pushes et voids ne sont pas des gains.
- Le CLV moyen utilise seulement les proxies disponibles, selon `entry_odds / closing_odds − 1`, avec son propre échantillon. `PAPER_CLOSING_MAX_AGE_SECONDS` fixe la fenêtre de clôture, 90 secondes par défaut.
- Le drawdown est la baisse maximale absolue de la courbe de P&L réglé depuis son sommet, en devise du rapport. La volatilité est l'écart-type d'échantillon des rendements par pari, sans annualisation.
- L'EV annoncée est pondérée par les mises réglées hors void. Son écart au rendement réalisé reste visible, même négatif.
- L'intervalle empirique à 95 % du yield tire avec remise les jours UTC d'entrée par blocs, 2 000 tirages avec graine 42. Moins de deux jours donne une estimation indisponible ; la volatilité exige deux paris et la corrélation trois jours appariés avec variance non nulle.
- Les segments par marché, compétition, modèle, tranche de cote et grade affichent leurs effectifs. L'exposition ouverte est aussi regroupée par événement. La corrélation compare les rendements quotidiens des compétitions sur leurs jours communs ; elle ne prétend pas mesurer une indépendance causale.

Les valeurs absentes sont nulles avec motif et taille d'échantillon. Le nombre de signaux est le nombre physique de signaux enregistrés, y compris les réévaluations d'entrée ; ce compte ne représente pas des événements indépendants.

Un rapport conserve les références et empreintes de ses entrées, règlements et clôtures, ainsi que sa méthode. Les mêmes preuves retournent le même rapport. Les tables refusent `UPDATE` et `DELETE`. Une correction de règlement produit un nouveau rapport courant ; les anciennes révisions et les anciens rapports demeurent accessibles. La courbe courante utilise les derniers règlements corrigés ; ce n'est pas la chronologie des ajustements de trésorerie.

La migration `20260908_0038` fige également `selected_team_id` dans les nouveaux signaux. La probabilité vient de cette identité dans la prédiction, indépendamment de l'ordre A/B du modèle et du fournisseur. Le ledger fige les équipes canoniques correspondantes pour le règlement. Les signaux antérieurs sans cette preuve restent conservés, mais ne sont ni reproduits comme vérifiés ni proposés comme opportunités ; aucune identité historique n'est inventée par migration.
