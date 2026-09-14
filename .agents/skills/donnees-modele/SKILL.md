---
name: donnees-modele
description: Définir les identités, versions de données, probabilités Game 1 sans fuite temporelle, explications et simulations immuables de Metiquo.
---

# Données, matching, estimation et simulations

## 1. Contrats de données

Lire `AGENTS.md` pour les formules, la politique de fraîcheur et l'organisation. Une **rencontre Stake est une série**, une **partie OE est une map**, une **sélection est une équipe dans un marché**, une **observation est une lecture datée**, une **prédiction est une estimation indépendante**, une **simulation est une décision fictive figée**. Ne jamais employer un identifiant unique « match » pour tous ces objets.

Une seule base SQLite. Prévoir les ensembles relationnels suivants, sans créer de moteur générique :

| Ensemble | Responsabilité |
|---|---|
| Exécutions et fichiers/versionnements OE | État des synchronisations, catalogue, hashes, manifestes actifs, compteurs et dates. |
| Compétitions, équipes, alias de chaque type | Identités canoniques, provenance, périodes de validité et décisions de correspondance. |
| Parties OE normalisées | `source_game_id`, compétition, instant de partie, index dans la série, deux équipes, résultats, version source, qualité et disponibilité connue. |
| Rencontres Stake | Identifiant/URL externe stable, équipes/compétition brutes et résolues, historique des horaires, indicateur de début déjà observé. |
| Observations de marché | Couple de sélections cohérent, Game 1 explicite, cotes, état positif ou négatif, instant de lecture et versions d'extraction. |
| Versions de modèle et prédictions | Paramètres, protocole temporel, métriques, manifestes, cutoff des features et probabilités. |
| Simulations et révisions de résultat | Snapshot initial immutable, mise fictive, résultat et corrections justifiées. |

Une table ou un petit groupe de tables par ensemble selon les contraintes réellement utiles. Indexer temps, compétition, identifiants externes, clé de marché et références de versions. SQL paramétré, clés étrangères, contraintes d'unicité et valeurs énumérées. Pas d'identité d'équipe basée seulement sur un nom affiché.

Les fichiers bruts valides sont immuables et référencés par SHA-256. Une correction reconstruit le sous-ensemble normalisé concerné et le manifeste actif dans une transaction ; elle ne doit pas laisser l'ancienne et la nouvelle valeur simultanément actives. Conserver la provenance nécessaire aux prédictions/simulations existantes. Une donnée remplacée n'est pas supprimée d'un snapshot ancien.

### Qualification du schéma Oracle's Elixir

À l'intégration, certifier les champs et leur sens sur les vrais CSV, notamment `gameid`, `game`, `date`, `league`, `position`, `teamname`, `teamid` et `result`. Ne pas traiter une présence de colonne comme preuve de sa sémantique. Documenter dans le parseur versionné : unité de `gamelength` si utilisée pour qualifier la fin d'une partie, fuseau de `date`, valeurs d'équipe dans `position`, signification de `datacompleteness` et gestion des formats historiques.

Une observation d'apprentissage correspond à **une Game 1 complète**, avec deux équipes distinctes et résultats complémentaires 0/1. Les deux lignes d'équipe sont regroupées ; les lignes joueur ne sont ni additionnées aux lignes équipe ni comptées comme 10 matchs. Filtrer sur `game == 1` uniquement après certification qu'il s'agit du numéro de partie dans la série. Index absent/ambigu : exclure cette partie, ne jamais déduire Game 1 du premier enregistrement disponible. Une Game 2 isolée ne devient pas Game 1.

Un BO1 est admissible à l'apprentissage seulement si son index Game 1 est établi. Cela n'autorise pas à convertir un marché Series Winner Stake en Game 1. Remakes, forfeits, résultats administratifs, doubles enregistrements et résultats contradictoires doivent être identifiés et exclus tant que leur sémantique n'est pas qualifiée. Ne pas fusionner automatiquement deux séries des mêmes équipes jouées le même jour.

Un `teamid` absent peut être résolu par un alias historique contrôlé ; il n'est pas inventé à partir d'un slug. Si aucune identité n'est prouvée, groupe exclu avec motif. Une compétition découverte sans matchs admissibles reste visible avec couverture insuffisante. Compter et exposer exclusions et anomalies ; ne pas masquer une ligue pour améliorer artificiellement les scores.

## 2. Matching contrôlé, sans calendrier OE inventé

Normaliser Unicode, casse et espaces, avec une politique stable pour la ponctuation. Conserver le nom original. **Ne pas supprimer les distinctions Academy, Challengers, Youth, B, C ou les suffixes pouvant distinguer deux équipes.** Les logos ne constituent jamais une preuve d'identité.

Les alias stockent au minimum source, libellé normalisé, entité canonique, compétition/contexte éventuel, période `valid_from/valid_to`, origine de la preuve, date de validation et statut actif. Prévenir les collisions d'alias sur des périodes recouvrantes. Renommage d'organisation et continuité sportive ne sont pas synonymes ; ne pas transférer aveuglément le passé d'une ancienne équipe à une nouvelle structure ou à son équipe réserve.

Procédure : résoudre la compétition, construire les candidats des deux équipes par identifiant ou alias confirmé, puis vérifier compatibilité du contexte, de l'adversaire et de la date avec les informations **réellement disponibles**. Une correspondance nominale exacte peut proposer une association, mais sa normalisation ne rend pas unique une identité qui ne l'est pas. Un candidat unique après contrôles cohérents peut être accepté avec preuve enregistrée. Plusieurs candidats, périodes incompatibles ou contradiction d'adversaire = `ambiguous_identity` et blocage.

OE peut ne contenir **aucun calendrier futur**. Le modèle cherche alors l'historique des équipes, pas une ligne OE correspondant déjà à la rencontre Stake à venir. L'absence normale d'une rencontre future chez OE ne justifie ni une date inventée ni un blocage systématique de toutes les rencontres. L'adversaire/date ne désambiguïsent que lorsqu'une information source le permet ; ils ne constituent pas une preuve fictive.

Une proximité de chaînes peut tout au plus proposer des candidats à l'utilisateur, jamais confirmer automatiquement. En V1, privilégier noms exacts et alias contrôlés sans dépendance fuzzy supplémentaire. Une petite section des paramètres permet de valider une association précise après inspection ; pas de bouton « forcer cette analyse » contournant tous les contrôles. Une décision manuelle trace la preuve et sa portée temporelle, puis relance la résolution. Une modification d'alias invalide les nouvelles analyses dépendantes, pas les simulations enregistrées.

Les alias de compétition suivent le même principe. Ne pas assimiler une ligue principale à son championnat Challengers, ni toutes les ERL à une seule ligue statistiquement homogène. N'imposer aucune liste figée de compétitions. Un segment nouvellement découvert ou renommé reste non qualifié tant que les preuves nécessaires manquent.

## 3. Modèle V1 arrêté

**Régression logistique avec régularisation L2, deux variables, scikit-learn.** Aucun LLM, réseau neuronal, ensemble de modèles ou feature de cote. Référence de comparaison : probabilités 50/50 et Elo brut. Ne pas choisir un autre modèle automatiquement pour remplir une page vide.

Les deux variables sont des différences entre A et B, construites uniquement sur les Game 1 historiques admissibles :

| Variable | Définition de départ |
|---|---|
| Écart de force | `(Elo_A - Elo_B) / 400`. Elo initial 1500, mise à jour `R_A += 20 × (y_A - E_A)` et opposée pour B, avec `E_A=1/(1+10^((R_B-R_A)/400))`. |
| Écart de forme | `forme_A - forme_B`, avec `forme=(victoires+2)/(n+4)` sur les 20 dernières Game 1 admissibles des 180 jours antérieurs. |

Ces nombres sont des **paramètres initiaux de projet**, pas des valeurs annoncées optimales. Avant chaque nouvelle partie admissible, ramener doucement chaque Elo vers 1500 selon `1500 + (R - 1500) × 2^(-jours_inactifs/180)` ; tracer la date d'état. Les deux Elo sont lus avant leur mise à jour simultanée. Pas d'apprentissage à partir d'une série future ni de mise à jour deux fois pour ses deux lignes équipe.

Pour garantir la symétrie A/B : orientation canonique indépendante du côté bleu/rouge et de l'ordre Stake ; features antisymétriques ; normalisation par échelle ajustée sur l'entraînement seulement, sans centrage ; `fit_intercept=False`. Probabilité `p_A=sigmoid(β·x)`, `p_B=1-p_A`. Inverser les équipes doit inverser les probabilités. Régularisation initiale `C=1`, pas de recherche massive d'hyperparamètres. Tout changement explicite de paramètres exige une nouvelle validation chronologique avant utilisation.

Exclure en V1 côté bleu/rouge du match à venir, draft, champions/bans, composition supposée, patch supposé et statistiques de la partie cible. Ils ne sont pas fournis comme données pré-série garanties par le contrat actuel. Les statistiques individuelles et les confrontations directes ne deviennent pas des explications du modèle si elles ne sont pas dans ses variables. Les changements de roster non connus avant match restent une limite annoncée, pas une analyse inventée.

Les cotes Stake n'entrent ni dans les features, ni dans les cibles, ni dans la calibration, ni dans la sélection des exemples d'apprentissage. Le module d'estimation doit pouvoir fonctionner sans accès aux tables de cotes. Les cotes sont jointes **après** le calcul indépendant.

## 4. Temporalité et disponibilité de l'information

Conserver pour chaque calcul `decision_at`, `feature_cutoff`, `dataset_manifest`, `model_version`, versions des alias et des règles. Les agrégats sont construits par replay chronologique, avant mise à jour du résultat cible. Tous les calculs de normalisation, choix de paramètres et contrôles de qualité appris sont ajustés exclusivement sur le passé autorisé. Les pipelines aident à éviter une préparation ajustée sur les données d'évaluation [D1].

Distinguer deux protocoles :

**Historique reconstruit.** Les exports annuels récupérés aujourd'hui n'indiquent pas nécessairement quand chaque correction a été publiée. Utiliser les dates d'événements antérieures au point de prédiction ; faute de disponibilité de publication historique démontrable, exclure par prudence les parties du jour UTC et de la veille UTC pour les features rétrospectives. Cette marge n'est pas une preuve de date de publication. Marquer le rapport « historique reconstruit à partir de versions acquises ultérieurement ; corrections rétrospectives possibles ». Ne jamais appeler cela un replay strictement point-in-time ou une performance de pari réelle.

**Suivi prospectif.** Les versions réellement acquises par Metiquo fournissent `first_seen_at`/`content_verified_at`. Une prédiction ne lit que des enregistrements de parties terminées, accessibles dans un manifeste déjà validé avant `decision_at`, et datant d'avant la rencontre. Ne pas appliquer à une décision passée une correction découverte ensuite. Le snapshot de features et de modèle rend cette règle vérifiable.

Le protocole de replay doit être identique pour les deux équipes. Une partie dont l'heure est imprécise se traite avec une exclusion conservatrice du groupe temporel, jamais un ordre arbitraire par identifiant. Regrouper les lignes d'une même partie avant le découpage ; ne pas séparer ses deux équipes entre entraînement et test. Ne pas augmenter artificiellement les effectifs en comptant des représentations symétriques comme des matchs indépendants.

## 5. Évaluation, calibration et critères d'admission

Premier découpage : 60 % des Game 1 admissibles les plus anciennes pour entraînement, 20 % suivantes pour validation, 20 % les plus récentes pour test final. Déplacer les frontières au bord des jours UTC/groupes de série pour empêcher leur partage ; enregistrer les **dates exactes**, IDs et hashes, pas seulement les pourcentages. Les seuils minimaux ci-dessous peuvent rendre un découpage impossible : dans ce cas, `model_unqualified`, sans découpage aléatoire de secours.

Le test final n'est ouvert qu'après gel du modèle et des règles. Ne pas corriger la méthode en consultant ce test, puis le présenter à nouveau comme inédit. Les features des périodes ultérieures peuvent intégrer les résultats déjà devenus disponibles de périodes antérieures, mais les coefficients du modèle évalué restent gelés. Ne pas utiliser la validation croisée aléatoire par défaut d'un calibrateur. La V1 n'ajoute pas de recalibrateur : elle **mesure** la calibration de la régression ; si insuffisante, elle refuse sa qualification. Un correcteur futur devrait disposer de son propre segment chronologique, sans toucher au test final [D2].

Rapport local conservé avec le modèle : nombres de parties avant/après exclusions, périodes, compétitions, features, paramètres, manifeste, couverture et taux de refus ; Brier score et log-loss sur probabilités non arrondies ; courbe de calibration avec probabilités moyennes, fréquence observée et effectif par tranche ; accuracy secondaire ; scores des deux références sur exactement les mêmes cas. Brier/log-loss ne mesurent pas exclusivement la calibration, d'où le diagnostic par tranches [D2].

**Garde-fous initiaux explicites, à modifier sur validation seulement :**

| Contrôle | Seuil initial de qualification |
|---|---|
| Volume global | Au moins 500 Game 1 d'entraînement, 200 de validation et 200 de test, sans doublons. |
| Historique d'une équipe | Au moins 10 Game 1 admissibles sur 180 jours, dernière partie admissible au plus vieille de 90 jours. |
| Compétition analysée | Présente dans l'entraînement ; au moins 50 observations de validation et 50 de test pour qualifier son segment. Pas d'héritage silencieux des scores d'une autre ligue. |
| Comparaison aux références | Brier au plus `min(Brier_50/50, Brier_Elo)+0,005` et log-loss au plus `min(LL_50/50, LL_Elo)+0,01`, contrôlés sur validation puis test final, globalement et sur les segments qualifiés. |
| Calibration globale | Écart absolu moyen pondéré par tranches de largeur 0,10 au plus 0,05 ; afficher les effectifs et ne pas qualifier une tranche avec moins de 30 observations de test. |
| Portée d'une prédiction | Deux équipes admissibles, compétition qualifiée et probabilité dans une tranche suffisamment observée ; aucun contexte international/inter-ligues non représenté et évalué. |

Ces seuils sont des règles conservatrices d'admission, **pas un certificat statistique de rentabilité, une garantie individuelle ou une probabilité de confiance**. Un score global acceptable ne valide pas une nouvelle petite ligue. Conserver et afficher les segments refusés. Les valeurs extrêmes 0/1, NaN et infinis sont rejetées ; l'écrêtage numérique nécessaire au calcul de log-loss ne transforme pas une sortie invalide en prédiction exploitable.

Une fois un modèle qualifié, son artefact effectivement évalué devient actif ; ne pas le réentraîner sur entraînement+validation+test tout en conservant les anciennes métriques. Les nouveaux résultats OE mettent à jour Elo/forme, pas nécessairement les coefficients. Préparer un nouveau candidat uniquement lorsque des données réellement nouvelles permettent une évaluation ultérieure dédiée. Garder l'ancien modèle qualifié tant qu'il reste valide ; un candidat en attente n'est pas une nouvelle version certifiée. Une réévaluation sur un test déjà consulté est explicitement une réévaluation, pas un test inédit.

Une correction des données ayant servi à l'entraînement ou aux métriques invalide la qualification dépendante jusqu'à recalcul et contrôle tracés. Sans changement de méthode, restituer le rapport corrigé comme tel ; ne pas exploiter la correction pour retoucher le modèle en observant les résultats du test. Stocker les coefficients et métadonnées dans un format de données validé, par exemple JSON local ; pas de chargement de pickle fourni par un tiers.

## 6. Comparaison et explication

Calculer les formules exclusivement selon `AGENTS.md`. L'analyse assemble une prédiction indépendante et une observation Stake qualifiée de la **même Game 1**, dans le même ordre d'équipe résolu. Stocker les références de cette association ; jamais une jointure approximative au rendu.

Distinguer `analysis_blocked`, `analysis_valid_no_edge` et `analysis_valid_theoretical_edge`. Pour le dernier, tous les garde-fous doivent passer et EV doit dépasser le seuil du projet. Sans cela, afficher la raison dominante et permettre de voir les autres causes. Une forte EV ne compense jamais un défaut d'identité ou de fraîcheur.

Explication déterministe, brève : écart Elo avant match, forme historique réellement utilisée avec `victoires/n`, période, signe des contributions `βj×xj` et limites. Les contributions sont dans l'espace du score logistique, pas des points de probabilité à additionner. Exemple de formulation avec valeurs réelles à injecter : « L'estimation repose sur l'écart de force historique et la forme récente en Game 1. La couverture de cette compétition est limitée à N observations évaluées. » Ne pas ajouter d'analyse de joueurs, de draft, de motivation ou d'actualité non présente dans le modèle.

L'indicateur de qualité décrit des éléments observables : effectif, récence, périmètre évalué et absence/présence d'un blocage. Ne pas afficher un pourcentage de « confiance » inventé. Le marché ne connaît pas nécessairement les mêmes informations que le modèle ; un écart de probabilités reste théorique.

## 7. Simulations et bilan

Une simulation peut être enregistrée à partir d'une analyse valide, y compris sans avantage positif, afin de permettre un suivi honnête des décisions. Une analyse bloquée ne peut pas créer une nouvelle simulation. Mise fictive strictement positive, unité fictive unique `u`, précision de deux décimales ; aucune recommandation de montant.

À l'enregistrement, le serveur recontrôle état, TTL, horaire et identités. Si la cote a changé depuis l'analyse affichée, présenter la nouvelle comparaison et demander une nouvelle validation ; ne pas remplacer le prix silencieusement. Le bouton conserve la saisie de mise. Clé d'idempotence pour les doubles clics et répétitions HTTP.

Snapshot immutable : événement et compétition, équipes/IDs, Game 1, sélection, observation et heure de cote, cote, `p_A/p_B`, probabilité de la sélection, cote juste, implicite, EV, mise fictive, features/cutoff, modèle, manifeste, alias, politique et date de décision. Une correction du résultat ne peut jamais modifier ces valeurs initiales.

Résultats saisis manuellement, explicitement pour **Game 1**, et non déduits du vainqueur de série :

| État | Retour brut fictif | Profit fictif |
|---|---:|---:|
| En attente | Non réalisé | Non réalisé |
| Gagné | `mise × cote` | `mise × (cote - 1)` |
| Perdu | `0` | `-mise` |
| Annulé/remboursé | `mise` | `0` |

Refuser un règlement anticipé incohérent ; lorsque le résultat réel ou le statut d'annulation n'est pas certain, garder en attente. Le résultat est une saisie manuelle, pas une preuve de règlement du bookmaker. Enregistrer date et provenance manuelle. Correction ultérieure : ancien/nouveau résultat, date et motif, sans suppression de la trace. Aucun règlement automatique n'est requis en V1.

Bilan : nombre de simulations par état, somme des mises gagnées/perdues, profit réalisé, rendement `profit / mises_gagnées_perdues`, taux de réussite parmi gagné/perdu, annulations séparées. Les attentes et annulations sont exclues du dénominateur du rendement ; dénominateur nul = « non disponible », pas 0 % prétendument observé. Arrondir seulement à l'affichage.

Le bilan de simulations mesure une sélection personnelle, pas la qualité globale du modèle. Pour évaluer les probabilités prospectives, conserver les prédictions éligibles, y compris sans simulation, puis relier uniquement des résultats Game 1 certains. Une métrique de modèle compte une seule décision canonique par événement (première prédiction éligible enregistrée), pas toutes les actualisations ni plusieurs tickets sur la même partie. Afficher la couverture de résultats et le nombre de cas manquants. Aucune courbe de gains historique avant les premiers vrais relevés de cotes.

### Références primaires

Consultées le 14 septembre 2026. Les paramètres Elo, fenêtres, seuils et procédures de Metiquo sont des décisions de projet, non des résultats empiriques annoncés.

[D1] scikit-learn, Common pitfalls and recommended practices : `https://scikit-learn.org/stable/common_pitfalls.html`.
[D2] scikit-learn, Probability calibration : `https://scikit-learn.org/stable/modules/calibration.html`.
