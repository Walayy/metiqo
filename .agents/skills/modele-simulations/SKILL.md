---
name: modele-simulations
description: "Définir, qualifier et expliquer une probabilité indépendante de victoire en partie 1 ; comparer les cotes et conserver des simulations reproductibles."
---

# Modèle, analyse et simulations

## Limite de cette préparation

Le modèle ci-dessous est une **spécification à tester**, sans entraînement réel ni performance mesurée dans cet environnement. Les seuils proposés sont des décisions de prudence, pas des résultats expérimentaux. Un avantage mathématique positif ne démontre pas une rentabilité réelle.

Cible : victoire de l'équipe A dans la **première partie**, avant la série, contre B, dans **toute compétition LoL**, sans priorité LEC/LCK : ligues majeures ou régionales, académies, qualifications et tournois internationaux/interrégionaux. Entraîner et évaluer sur cette même cible avec les données Oracle’s Elixir réellement disponibles. L'inclusion d'une compétition dans le périmètre ne prouve ni sa couverture ni la qualification du modèle pour celle-ci. Ne pas utiliser les résultats des parties suivantes pour enrichir silencieusement la cible de la V1.

## Identité et données admissibles

L'identité vient des identifiants sportifs vérifiés, non des logos ou de la similarité d'une chaîne. Table d'alias versionnée : source, identifiant source, ligue, équipe canonique, période de validité et preuve du rapprochement. Les renommages documentés conservent une continuité seulement si justifiée. Une académie et son équipe première restent distinctes.

Automatiser les égalités normalisées non ambiguës sur alias déjà vérifiés. Une recherche approximative peut produire une suggestion technique, **jamais une correspondance active**. Nouvelle identité ou ambiguïté = analyse indisponible jusqu'à correction exceptionnelle du mapping. Pas d'écran de rapprochement compliqué en V1 ; fournir le diagnostic dans l'état des données. Le fonctionnement courant des équipes déjà qualifiées reste automatique.

Exiger les deux équipes, une compétition identifiée, la partie 1 explicitement identifiée, des données validées et des dates comparables. Aucune liste fermée de ligues n'est admise. Les académies sont admissibles sous leur propre identité, jamais assimilées à l'équipe première. Écarter doublons, matchs partiels, forfaits/remakes non interprétables et données hors cible selon le contrat d'import. Une partie canonique correspond à une observation statistique, pas à deux équipes comptées comme deux matchs.

La V1 ne connaît pas le roster futur, le choix de côté, les champions, le veto ni les annonces récentes. Ne pas prétendre les avoir analysés. Les changements d'effectif non observés constituent une limite affichée, même lorsque le volume historique est suffisant.

## Un seul modèle de classement

Choix de conception à qualifier pour ce périmètre élargi : classement de type **Elo avec retour progressif vers la moyenne**, commun par identité d'équipe à travers les compétitions. Une équipe conserve son classement lorsqu'elle passe d'une ligue à un tournoi international ; une académie conserve son classement distinct. L'ancienne séparation des classements LEC/LCK ne convient pas à cette cible et ne doit pas être reconduite. Implémentation limitée à des fonctions pures de bibliothèque standard ; ni réseau neuronal, ni LLM, ni API de prédiction. Les identifiants, résultats et dates d'Oracle’s Elixir sont les seules données sportives utilisées.

Ce classement commun est une proposition, pas une preuve de comparabilité entre régions ou niveaux. Les seules liaisons entre groupes d'équipes viennent des premières parties admissibles réellement observées avant la prédiction ; aucun bonus de région ou niveau n'est inventé. Sans lien historique admissible entre les groupes des deux adversaires, l'estimation de leur confrontation est indisponible. La validité des comparaisons internationales et entre niveaux reste à évaluer explicitement ; un classement initial identique à 1 500 ne suffit pas à la démontrer.

Pour chaque équipe, initialiser le classement R à 1 500. Avant une partie, après Δ jours sans observation, appliquer :

`R_effectif = 1500 + (R - 1500) × 2^(-Δ / H)`

Pour A contre B :

`p_brut(A) = 1 / (1 + 10^((R_B_effectif - R_A_effectif) / 400))`

Après un résultat y valant 1 si A gagne et 0 sinon :

`R_A_nouveau = R_A_effectif + K × (y - p_brut)`

`R_B_nouveau = R_B_effectif - K × (y - p_brut)`

L'échelle 400 et le niveau 1 500 sont ici des conventions du modèle, pas des valeurs estimées pour LoL. Le retour vers la moyenne réduit l'assurance tirée de résultats éloignés ; il ne mesure pas les remplacements de joueurs.

Calibration de la probabilité, avec température T ≥1 :

`p(A) = 1 / (1 + exp(-log(p_brut / (1 - p_brut)) / T))`

`p(B) = 1 - p(A)`

Employer une forme numérique stable. Ne pas arrondir les classements à chaque mise à jour. T n'est appliqué qu'à la probabilité présentée, pas à la mise à jour Elo. Une hausse de T rapproche les probabilités de 50 %, sans changer l'ordre des équipes.

Grille volontairement petite : K ∈ {16, 32, 48}, H ∈ {60, 120, 240 jours}, T ∈ {1 ; 1,25 ; 1,5 ; 2}, soit 36 configurations. Choisir sur la validation temporelle uniquement, d'abord selon la log-loss, puis Brier ; en cas d'égalité à 0,001 près, retenir la plus prudente : T plus grand, puis K plus faible, puis H plus grand. Ne jamais sélectionner K/H/T selon l'EV, les cotes, le ROI simulé ou les résultats du test final.

Les probabilités ne dépendent pas de la cote affichée. Modifier ou retirer toutes les cotes doit laisser le même classement et la même probabilité à données/modèle/date identiques. Ajouter seulement une statistique si un futur périmètre la justifie avec une nouvelle évaluation ; elle n'entre pas implicitement dans cette version.

## Chronologie et qualification

Les [principes de validation croisée](https://scikit-learn.org/stable/modules/cross_validation.html) et de [calibration probabiliste](https://scikit-learn.org/stable/modules/calibration.html), documentation officielle consultée le **14 septembre 2026**, servent de repères méthodologiques. **scikit-learn n'est pas une dépendance retenue.** Le protocole et les seuils suivants sont des choix propres à Metiquo.

Fixer une date de coupure D avant de regarder les performances, au plus tard à la dernière journée sportive disponible et à aujourd'hui moins deux jours. Utiliser 24 mois : douze mois d'entraînement à partir des classements initiaux, six mois de validation, puis six mois de test final jamais utilisé pour choisir les paramètres. Consigner les dates exactes, pas seulement « 80/20 ». Définir avant le test les compétitions du périmètre de qualification et les regroupements éventuels d'éditions justifiés par une continuité vérifiée ; ne pas choisir un regroupement après lecture des scores. Minimum de qualification : 300 parties d'entraînement, 100 de validation, 200 de test au total ; au moins 75 parties de test par compétition pour laquelle le statut qualifié est revendiqué. La couverture réelle de ces volumes reste à mesurer. Un manque de données donne **modèle expérimental pour la compétition concernée**, pas une validation allégée silencieusement ni son exclusion du catalogue.

Dans les blocs de validation et de test, prédire avant d'intégrer le résultat ; les classements peuvent évoluer seulement après le délai de disponibilité prévu. Les hyperparamètres sont gelés pendant le test final. Ne pas mélanger aléatoirement les parties. Les observations d'une même série ne traversent pas les partitions ; la cible partie 1 limite déjà ce problème.

Faute d'heure historique de publication démontrée, regrouper les prédictions par journée UTC et n'utiliser que des résultats dont l'horodatage sportif précède d'au moins **48 heures** l'instant de coupure du lot. Si seule une date de partie est fiable, prendre sa fin de journée UTC comme borne conservatrice ; une journée sportive non encore admissible est exclue entièrement. Appliquer cette même règle en rétrospectif et dans la V1 prospective. Calculer les prédictions d'un même lot avant les mises à jour correspondantes ; appliquer le retour vers la moyenne une seule fois par équipe et sommer les deltas calculés sur les classements du lot. Ce délai est une hypothèse de prudence, pas la mesure de la cadence Oracle. Un changement à 24/72 h exige une évaluation de sensibilité consignée, pas le choix du meilleur score après coup.

**Différencier date du match et disponibilité de la donnée.** Un CSV téléchargé aujourd'hui peut corriger un résultat ancien. En rétrospectif, sa version n'est pas forcément celle disponible à l'époque : nommer l'évaluation « test chronologique rétrospectif sur données corrigées ». Elle ne suffit pas à prouver une stratégie exécutable en temps réel. En suivi prospectif, utiliser strictement les versions dont `ingested_at ≤ predicted_at`, et conserver leurs hashes. Ne jamais reconstruire une ancienne décision avec un fichier corrigé ultérieurement.

Calculer une prédiction par partie, avec orientation A/B stable, et conserver : fenêtre, paramètres, version de l'algorithme, manifeste des fichiers, instant de calcul, dernière date sportive utilisée, deux classements effectifs, volumes historiques et motifs d'abstention. Retirer les cotes du module de prédiction, y compris de sa configuration.

### Mesures et seuils de qualification

Calculer sur le test final la moyenne de `(p-y)²` (**Brier**) et de `-[y ln(p)+(1-y) ln(1-p)]` (**log-loss**). Utiliser une protection numérique minuscule uniquement pour le logarithme ; ne pas modifier les probabilités stockées. Référence indépendante simple : p=0,5 donne Brier=0,25 et log-loss≈0,693147.

Présenter le nombre de parties, la période, la couverture avant/après abstention et les résultats par compétition. Distinguer aussi les confrontations internationales/interrégionales et entre niveaux lorsque ces contextes sont identifiables dans les données vérifiées ; une performance agrégée sur de grandes ligues ne qualifie pas les autres compétitions. Pour la calibration, répartir les prédictions en cinq groupes de taille proche, afficher probabilité moyenne, fréquence de victoire et effectif ; calculer l'écart absolu moyen pondéré. Ne pas confondre cet écart avec l'erreur d'une rencontre particulière.

Conditions initiales pour le statut **qualifié** : Brier et log-loss meilleurs que la référence 50/50, au global sur le périmètre de qualification prédéfini et dans chaque compétition pour laquelle ce statut est revendiqué ; écart de calibration pondéré ≤0,08 au global ; volumes minimaux précédents respectés. Ajouter une estimation de l'incertitude de la différence de log-loss : 2 000 rééchantillonnages par semaines UTC entières, graine enregistrée, au moins 12 semaines de test, intervalle percentile à 95 %. Exiger une borne supérieure négative au global. L'intervalle est approximatif et concerne la performance moyenne, pas « les chances à 95 % » du match. Conserver le statut par compétition : aucun transfert automatique de qualification à une nouvelle ligue, à une académie ou à un tournoi international. Les compétitions non qualifiées restent visibles avec une estimation expérimentale lorsqu'elle est calculable, sinon un motif d'indisponibilité.

Ces exigences peuvent conduire à **aucun modèle qualifié**. Ne pas abaisser les seuils parce qu'aucune opportunité n'apparaît. Un test consulté ne redevient pas inédit après modification ; réserver une période future non utilisée à la requalification. Reconstituer quotidiennement les classements après un vrai changement des données, avec paramètres gelés ; ne pas lancer une nouvelle recherche de paramètres tous les jours. Réexaminer la qualification lorsqu'elle date de plus de 90 jours ou que le périmètre/algorithme change.

Sans historique de cotes effectivement capturées avant les matchs, ne pas publier un ROI rétrospectif bookmaker. Aucun gain réel ni supériorité sur Stake n'est démontré par un Brier meilleur que 50/50.

## Analyse et règles d'abstention

Probabilité calculable : chaque équipe dispose d'au moins **15 premières parties validées dans les 180 derniers jours**, dont une au cours des 45 derniers jours ; compétition et identité résolues, groupes d'adversaires reliés selon la règle du classement commun ; dernier contrôle complet réussi d'Oracle’s Elixir datant de **36 h au plus**. Les premières parties d'une même équipe peuvent provenir de plusieurs compétitions sous son identité vérifiée ; les résultats de son académie ne lui sont jamais attribués. Ces bornes initiales sont des choix de prudence. Une nouvelle équipe peut être incluse dans le classement d'entraînement sans devenir immédiatement analysable.

La date du dernier match de la ligue est affichée distinctement : une pause de calendrier n'est pas un défaut de synchronisation. Une révision en quarantaine pour incohérence critique bloque les nouvelles opportunités du périmètre affecté jusqu'à résolution. Après promotion de nouvelles données, tant que le modèle courant n'a pas été reconstruit avec leur manifeste, afficher « mise à jour du modèle » et bloquer les nouvelles opportunités ; l'ancien résultat reste consultable comme ancien. Un défaut réseau temporaire n'efface pas l'historique valide.

Pour une cote décimale d et une probabilité p portant sur la même sélection :

| Indicateur | Définition |
|---|---|
| Seuil de rentabilité de la cote | q = 1/d. Ce n'est pas une probabilité indépendante ni une probabilité « sans marge ». |
| Cote juste du modèle | 1/p. |
| Écart en points de probabilité | 100 × (p−q), exprimé en **points de pourcentage**. |
| Avantage théorique / EV | 100 × (p×d−1), exprimé en **% de la mise**, non en taux de réussite. |
| Espérance fictive sur mise m | m × (p×d−1), sous hypothèse de gain/perte binaire sans annulation. |

L'information de marge du marché à deux issues peut être calculée par `1/d_A + 1/d_B − 1`. Une normalisation de ces deux inverses peut être affichée en détail comme approximation bookmaker, mais ne change jamais p. Elle ne remplace pas `1/d` pour le seuil de rentabilité de la cote achetée.

**Opportunité potentielle** seulement si toutes les conditions sont satisfaites : modèle qualifié et encore valide pour la compétition et le contexte de la rencontre, historique suffisant, source et marché frais selon le skill Stake, identification exacte, p compris entre 0,10 et 0,90, EV ≥5 %, et `(p−0,03)×d−1 > 0`. Cette dernière baisse de trois points est un **test de sensibilité arbitraire**, pas une borne de confiance. Afficher ce libellé exact dans le détail. Ne pas transformer ces marges en promesse de sécurité.

Sinon, choisir un état explicite : **analyse indisponible** (donnée/identité/état insuffisant), **estimation expérimentale** (modèle non qualifié), **aucun avantage suffisant**, ou **cote périmée**. Un modèle peut préférer l'équipe A sans trouver sa cote intéressante. Les deux sélections sont évaluées ; ne pas orienter arbitrairement le calcul vers le favori.

L'explication est un gabarit alimenté par les valeurs réellement employées : « Le classement fondé sur les résultats et les adversaires, avec moins de poids pour l'ancienneté, favorise A. Estimation : … ; pour cette cote, le seuil est … . Données utilisées jusqu'au … ; compositions futures non vérifiées. » Ajouter un petit aperçu des premières parties récentes et du nombre d'observations, sans prétendre que le simple taux de victoire est la formule du modèle. Aucun commentaire inventé sur draft, forme mentale ou joueurs.

## Simulations et suivi

Depuis une analyse exactement identifiée et une cote encore fraîche, proposer une mise en **unités fictives**, 10 par défaut, modifiable, strictement positive et plafonnée à 100 000. Aucune recommandation de mise, aucun Kelly, aucune progression pour récupérer une perte. L'analyse et les boutons rappellent qu'il ne s'agit pas d'un pari placé.

Il est permis d'enregistrer une simulation sur une analyse complète sans avantage suffisant, ou avec un modèle expérimental : conserver clairement ce statut d'origine. Une donnée ambiguë, une cote périmée ou une partie déjà commencée empêchent tout nouvel enregistrement. Ne pas mélanger le bilan expérimental avec une affirmation de performance du modèle qualifié.

À l'enregistrement, le serveur revérifie fraîcheur, état et identité. Si la cote ou le modèle a changé depuis l'ouverture du formulaire, demander une nouvelle confirmation des valeurs affichées, sans changer silencieusement la simulation. Préserver la mise saisie. Une clé d'idempotence empêche deux créations sur double clic ou répétition réseau.

Photographie immuable : rencontre, ligue, deux équipes, partie, marché, sélection, URL, prix et heure du relevé, p non arrondi, cote juste/EV calculables, statut d'analyse, paramètres/version et manifeste du modèle, mise, instant d'enregistrement. Conserver cette photographie même si un alias, une cote ou un fichier source est corrigé. Les arrondis d'interface ne servent pas de base aux calculs.

Résultat renseigné manuellement : en attente, gagné, perdu ou annulé/remboursé. Ce résultat est déclaré par l'utilisateur, pas vérifié auprès du bookmaker. Une correction exige confirmation et conserve ancien état, nouvel état et date dans un petit journal associé. Une clôture de série ne permet pas de déduire le résultat de la partie 1.

Avec une mise m : gagné → profit net `m×(d−1)` ; perdu → `−m` ; annulé → `0` ; en attente → profit non réalisé. Stocker les mises en centièmes d'unité et calculer avec `Decimal` ; arrondir au centième uniquement au règlement selon ROUND_HALF_UP.

Bilan : simulations en attente, gagnées/perdues/annulées, mises réglées non annulées, profit net réalisé, rendement `profit / mises réglées non annulées`. Si le dénominateur vaut zéro : « non calculable ». Le taux de réussite exclut attentes et annulations. Les mises engagées en attente sont affichées séparément, pas ajoutées au rendement réalisé.

Le bilan des seules simulations est **sélectionné par l'utilisateur** : il ne mesure pas à lui seul la qualité globale du modèle. Conserver aussi les prédictions prospectives des rencontres admissibles, y compris sans simulation, pour un suivi indépendant du choix de miser. Pour ce suivi, utiliser une seule prédiction de référence par rencontre : la première complète dans la fenêtre de suivi avant la série ; ne pas choisir a posteriori la meilleure. Une rencontre sans résultat disponible reste en attente et n'est pas notée comme une erreur.

## Vérifications ciblées

| Cas | Résultat attendu |
|---|---|
| p=0,55 ; d=2,00 ; m=10 | q=50 % ; cote juste≈1,81818 ; écart=5 points ; EV=10 % ; espérance=1 unité ; gain réglé=+10, perte=−10, annulation=0. |
| Classements égaux | p(A)=p(B)=0,5 ; échanger les équipes donne les probabilités complémentaires. |
| Deux prix différents pour les mêmes données | Même p ; seule la comparaison économique change. |
| Même CSV importé deux fois | Même classement, mêmes nombres de matchs ; aucun apprentissage doublé. |
| Résultat futur ajouté, ordre d'entrée mélangé | Les prédictions antérieures restent identiques ; tri déterministe avant toute mise à jour. |
| Correction tardive d'une partie ancienne | Nouveau modèle courant versionné ; ancienne simulation et prédiction inchangées. |
| Marché de série, académie confondue avec l'équipe première, partie 2 ou état live | Analyse cible refusée, même si les noms semblent correspondre. |
| Compétition hors LEC/LCK, académie correctement identifiée ou tournoi international | Aucune exclusion de périmètre ; appliquer les mêmes contrôles de données, comparabilité, fraîcheur et qualification. |
| Adversaires issus de groupes sans lien historique admissible | Estimation indisponible ; aucune comparaison artificielle de classements indépendants. |
| Nouvelle compétition absente du périmètre de qualification | Aucun transfert du statut qualifié ; estimation expérimentale si calculable, sinon diagnostic d'indisponibilité. |
| Données sans volume suffisant ou qualification absente | Aucun badge d'opportunité ; état et motif lisibles. |
| Double clic, résultat corrigé, aucune mise réglée | Une seule simulation ; trace de correction ; rendement non calculable sans division par zéro. |

Tous les chiffres d'exemple sont synthétiques. Les tests de modèle et les métriques réelles restent à exécuter après validation de l'import.
