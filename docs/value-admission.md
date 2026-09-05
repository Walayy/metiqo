# Garde-fous d'admission de la value

VAL-004 agrège les preuves déjà calculées sans relire implicitement une source ou un repository.
Le gate retourne toujours une décision métier complète ; il ne crée jamais une opportunité lorsque
la liste des raisons est non vide.

Les contrôles suivent l'ordre public et stable suivant : capacité activée, qualité source, modèle
champion, mapping événement, règles marché, marché ouvert, événement non commencé, cutoff de
prédiction, âge de cote, confiance du mapping, edge, EV puis EV prudente.

Chaque contrôle produit un `AdmissionCheck`. Toutes les défaillances sont évaluées afin de rendre le
diagnostic complet, puis les raisons identiques sont regroupées sans doublon en conservant leur
premier ordre.
Un seul contrôle en échec suffit à fixer `admitted=false`.

Les seuils proviennent exclusivement de la `ResolvedValuePolicy` de VAL-003. Un âge à la borne est
accepté et la seconde suivante est refusée. Un marché suspendu ou fermé, une évaluation au début de
l'événement, un cutoff égal ou postérieur au début, une source non fraîche, un modèle non champion
ou une capacité désactivée ne peuvent jamais atteindre la création d'opportunité.

`CONSERVATIVE_EV_NEGATIVE` distingue une borne prudente réellement négative. Lorsqu'elle reste
positive mais sous un seuil plus strict, `CONSERVATIVE_EV_TOO_SMALL` conserve le motif exact ;
`EXPECTED_VALUE_TOO_SMALL` fait de même pour l'EV centrale.
