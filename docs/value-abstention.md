# Abstention de première classe

Une absence d’opportunité est un résultat métier normal. `ValueDecision` distingue deux sorties :

- une admission contient la `ValuePrice` calculée et aucune abstention ;
- une abstention contient au moins une `AbstentionReason` ordonnée et peut ne contenir aucune value si un contrôle amont a bloqué le calcul.

`ValueDecisionEngine` réunit les motifs structurés issus du modèle, des dépendances amont et du gate d’admission. Les doublons sont supprimés puis les motifs sont classés dans l’ordre public de `AbstentionReason`, indépendamment de l’ordre d’arrivée des systèmes sources.

Les codes ML qui arrêtent le calcul sont traduits explicitement. Par exemple, `LOW_DATA_COVERAGE` devient `INSUFFICIENT_HISTORY` et `ABSTENTION_REQUIRED`/`OUT_OF_DISTRIBUTION` deviennent une seule raison `OUT_OF_DISTRIBUTION`. Un code bloquant inconnu est refusé afin qu’aucune cause non versionnée ne fuite dans le contrat.

Une `Quality` publiable ne porte aucune raison. Inversement, une décision non publiable exige au moins une raison, sans doublon et dans l’ordre public. L’interface TypeScript couvre exhaustivement le vocabulaire généré et affiche des libellés français sur le dashboard comme sur la fiche signal.
