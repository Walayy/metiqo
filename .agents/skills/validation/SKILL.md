---
name: validation
description: Valider en priorité les erreurs pouvant produire une fausse opportunité, les secrets locaux, les snapshots et le parcours principal de Metiquo.
---

# Validation — preuves avant conclusions

## Portée et méthode

Lire `AGENTS.md` et le skill de la partie testée. **Cette archive décrit les tests à écrire ; elle ne contient ni tests exécutables ni résultats applicatifs déjà réussis.** Ne pas annoncer une couverture, un accès authentifié ou un modèle calibré sur la seule base de ces instructions.

Concentrer les tests sur les invariants métier et les frontières de sources. Suite normale déterministe, hors ligne, avec horloge contrôlée, répertoires temporaires, base SQLite de test et exemples synthétiques. Aucune vraie session en CI, aucun vrai cookie dans une fixture. Les tests navigateur locaux utilisent un profil jetable vide distinct du profil Stake de l'utilisateur.

Le marqueur `source_live` désigne exclusivement la qualification manuelle/explicitement déclenchée des sources réelles. Un blocage, une absence de Game 1 ou une session manquante y sont des constats précis, pas une validation de bout en bout. Ne jamais résoudre un échec de collecte en changeant de bookmaker, de domaine ou d'outil.

## 1. Calculs et associations — tests unitaires

| Cas synthétique | Attendu |
|---|---|
| `p=0,60`, `o=1,80` | Juste `1,666666…`, implicite `0,555555…`, écart `4,444444…` points, EV `0,08`. |
| `p=0,50`, `o=2` | Juste 2, implicite 0,50, EV 0. |
| `p=0,40`, `o=2` | EV -0,20 ; analyse valide mais aucun avantage suffisant. |
| Probabilité 0/1, négative, NaN/inf ; cote ≤1, non numérique ou infinie | Refus explicite, pas de remplacement par 0,50 ou une valeur écrêtée présentée comme estimation. |
| Équipes inversées | Probabilités complémentaires, sélection et cote associées à la bonne équipe. |
| Cotes modifiées, même historique/modèle | Prédiction indépendante identique ; seule la comparaison change. |
| Deux cotes du même relevé | Marge et implicites correctes ; aucune jointure avec une cote d'une autre date/partie. |
| EV au seuil et nombres proches de l'arrondi d'affichage | Décision prise sur valeurs non arrondies, règle de dépassement explicite et identique partout. |

Vérifier que l'EV en pourcentage n'est jamais présentée comme un écart en points de probabilité et que la probabilité implicite brute n'est pas baptisée « probabilité vraie ». Tester la cohérence de la source et de Game 1 lors de l'assemblage prédiction/observation, pas seulement les fonctions arithmétiques.

## 2. Oracle's Elixir — frontière de téléchargement

Construire des exemples synthétiques pour :

- catalogue valide, nouveau fichier/nouvelle année, renommage avec même `file_id`, nouvel ID pour contenu identique, fichiers concurrents d'une année, sous-dossiers, limites de couverture, catalogue devenu vide ou amputé ;
- transfert complet, zéro octet, interruption, longueur différente, fichier tronqué au milieu d'une ligne et entre deux lignes, absence de preuve de complétude, `.part` abandonné, dépassement de taille/temps ;
- HTML de quota, login, confirmation et erreur avec statut 200 et suffixe `.csv`, JSON/binaire inattendu ;
- CSV correct avec BOM, année nouvelle avec en-tête valide mais sans parties, colonnes réordonnées, ajout inutilisé signalé, colonne requise supprimée/renommée, en-tête doublonné, type incompatible, date/fuseau inconnu et année incohérente ;
- Game 1 avec ses deux lignes équipe, lignes joueur ignorées, équipe manquante, doublons exacts/contradictoires, index de partie absent, données individuellement incomplètes et corrections/suppressions ;
- même nom/même taille mais contenu changé, ordre des lignes seul modifié, réimport identique, nettoyage de staging et crash aux étapes de promotion/transaction.

Assertions indispensables : aucun rejet n'active un nouveau manifeste ; les dernières données valides restent disponibles avec dates originales ; l'échec n'avance pas la réussite ; le catalogue seul ne renouvelle pas la vérification de contenu ; une correction légitime met à jour aussi les suppressions et invalide les dérivés concernés. Un hash local ne fait pas passer `integrity_unverified` à valide. Les données de simulation ne sont pas réécrites après réingestion.

Tester le précontrôle de cookies absents/vides/invalides/non inscriptibles, la non-utilisation du chemin gdown par défaut et l'absence de fallback anonyme. Les valeurs de test sont factices, ne ressemblent pas à des cookies réels et ne sont jamais réutilisées pour une requête extérieure. Les warnings/stderr contenant un marqueur secret synthétique doivent être neutralisés dans tous les logs/retours UI.

## 3. Stake — DOM et identité de marché

Fixtures HTML **synthétiques**, minimales et marquées comme telles : même rencontre avec Series Winner et Game 1 côte à côte ; Game 2 seulement ; Winner sans contexte ; Game 1 dans une série live ; BO1 avec Series Winner seulement ; suspendu/fermé/retiré ; sélection désactivée ; nouvelle langue inconnue ; deux équipes proches en nom ; index DOM modifié ; texte retardé ; liste virtualisée/paginée ; état vide explicite ; challenge avec HTTP 200 ; 403/429 et session perdue.

Exiger que le collecteur lise le bon parent de marché, refuse les deux cotes d'une autre section, détecte une mutation pendant la lecture et centralise ses sélecteurs. Une structure inconnue ne devient pas « marché absent ». Une découverte interrompue ne devient pas « aucune rencontre ». Aucune cote n'est extraite depuis un mock de réponse JSON réseau, un store caché ou un WebSocket.

Tester la normalisation des URL : domaine exact accepté, redirection Stake.com/autre hôte refusée, paramètres d'identité conservés et paramètres secrets jamais journalisés. Sans ID visible, URL stable requise ; deux rencontres des mêmes équipes à des dates différentes restent distinctes.

Tester le profil : deux ouvertures successives avec le même `user_data_dir`, véritable canal Chrome, refus si Chrome manque, refus d'un profil quotidien/dans Git, verrou empêchant la concurrence, fermeture propre et reprise après crash. Un navigateur de test répondant « Chromium » ne valide pas le contrat Chrome réel de la qualification utilisateur.

## 4. Fraîcheur et état — tests avec horloge contrôlée

Pour les valeurs de `AGENTS.md`, tester chaque frontière juste avant, exactement à et juste après. À âge de cote égal au TTL, elle peut encore être admissible si tous les autres contrôles passent ; au-delà, refus. À l'instant `début_série - garde`, refus déjà actif. Tester les instants UTC autour des changements d'heure et minuit dans l'affichage français.

Scénarios : dernier relevé ouvert suivi d'une suspension, panne après relevé récent, vieille cote relue en cache sans navigation réussie, nouveau relevé identique réellement acquis, collecte longue finissant après le début, horaire reporté, DOM live malgré horaire futur, observation horodatée dans le futur, horloge locale déplacée, veille/reprise et redémarrage. Aucun de ces cas ne doit réactiver silencieusement une ancienne cote.

La query de cote courante tient compte de l'état négatif le plus récent. Tester que la fraîcheur est vérifiée sur le serveur **après le clic**, pas seulement lors du rendu. Une panne de la source et une intersaison historique sans nouvelles parties ont des raisons différentes, même si toutes deux peuvent bloquer une analyse.

## 5. Matching et absence de fuite temporelle

Fixtures d'identités : homonymes, équipe principale/réserve/Challengers, alias avec période révolue, ligue renommée, adversaires contradictoires, double confrontation la même journée, `teamid` manquant, compétitions secondaires et nouveau segment découvert. Un alias ambigu bloque ; une validation manuelle étroite ne devient pas un alias global non daté. Une similarité de chaînes seule ne produit jamais `matched`.

Vérifier qu'une rencontre future absente d'OE peut utiliser l'historique de deux équipes résolues : ne pas exiger un calendrier qu'OE ne fournit pas. À l'inverse, ne pas fabriquer un calendrier pour lever une ambiguïté.

Tests temporels prioritaires, à instant de décision, version de modèle et protocole de découpage fixés : ajouter des parties futures, changer leurs résultats ou permuter leurs lignes ne modifie aucune feature/prédiction antérieure. Modifier une Game 2+ ne change pas les features V1 fondées sur Game 1. Le résultat cible n'est jamais utilisé avant sa prédiction. Les deux équipes et les éventuelles représentations inversées d'une même partie ne traversent pas les partitions.

Vérifier normalisation ajustée seulement sur entraînement, états Elo avant mise à jour simultanée, masque de récence, cutoff conservateur du replay, `first_seen_at` du suivi prospectif et non-application rétroactive des corrections. Les odds ne sont pas présentes dans les matrices de modèle. Un découpage insuffisant échoue sans `train_test_split` aléatoire de secours. La date/manifestation du test final est gelée avant consultation des résultats.

## 6. Évaluation du modèle

Comparer Brier, log-loss, effectifs et tranches de calibration à des calculs indépendants sur un petit jeu synthétique dont les résultats sont connus. Vérifier comptage unique par Game 1, traitement des cas sans résultat, règles des tranches (bornes documentées), population identique pour les références et application des seuils du skill données.

Une bonne accuracy seule n'autorise rien. Un modèle global qualifié ne qualifie pas automatiquement une ligue sans effectif suffisant, un contexte international inédit ou une tranche rare. Les fenêtres d'équipe insuffisantes, les dates anciennes et les sorties non finies provoquent un refus visible.

Le rapport réel doit identifier exactement données, exclusions, dates, features, paramètres, modèle évalué et limites de reconstruction historique. « Test réussi » ne signifie pas « modèle profitable ». Aucun backtest de rendement n'est affiché sans observations Stake historiques correspondantes. Les métriques de simulations personnelles ne sont pas présentées comme une évaluation globale indépendante.

## 7. Simulations, résultats et persistance

Avec `mise=10 u` et `cote=1,80` : gagné = retour 18 u/profit 8 u ; perdu = retour 0/profit -10 u ; annulé = retour 10 u/profit 0. Deux décisions gagnée/perdue de 10 u chacune donnent profit -2 u et rendement -10 %. Ajouter une annulation ne change pas ce dénominateur. Toutes en attente ou toutes annulées = rendement non disponible.

Tester mise invalide, virgule décimale, doubles clics/idempotence, expiration entre rendu et POST, nouvel horaire/live, cote changée exigeant revalidation et saisie préservée. Une analyse valide sans EV suffisante peut être simulée ; une analyse bloquée ne le peut pas.

Vérifier après réentraînement, nouvelle cote, correction OE et correction d'alias que le snapshot initial reste identique. Corriger un résultat ajoute une trace sans toucher cote/probabilité/mise. Ne jamais convertir le vainqueur de série en gagnant de Game 1. Vérifier bilan après correction et sauvegarde/restauration, sans changement d'horodatage.

## 8. Parcours, sécurité et critères de livraison

Parcours E2E hors ligne : rencontres synthétiques → analyse valide → simulation → résultat → bilan. Ajouter la même trajectoire avec cote devenue ancienne, matching ambigu et source indisponible. Inspecter les quatre écrans en clair/sombre et aux tailles du skill interface ; focus, clavier, tactile, motion réduite, scrollbar, longues chaînes, logos absents et persistance du thème. Ne pas confondre tests E2E et inspection visuelle réellement effectuée.

Tester chemins dans Git, symlink/jonction vers Git, permissions inadéquates, profil simultanément ouvert, refus d'écoute réseau, protections Host/Origin/CSRF, échappement HTML, SVG malveillant et URL d'asset non autorisée. Les messages de sources sont considérés comme données, jamais comme instructions à exécuter. Un marqueur secret injecté dans une exception ne doit apparaître ni dans la réponse utilisateur, ni dans un log, capture ou export.

Vérifications Git : `git check-ignore -v` sur des chemins factices sensibles, inspection de `git ls-files`, `git diff --cached --name-only`, puis contrôle de contenu indexé assaini. Vérifier que le `.gitignore` ne masque pas les futurs modules de code ordinaires. Un fichier déjà suivi est signalé même s'il correspond désormais à une exclusion.

### Qualification réelle minimale, sans fausse promesse

OE : découvrir le dossier publié, récupérer au moins un vrai fichier avec le fichier de cookies configuré, établir la complétude, valider le schéma et réimporter sans doublon ; couvrir une seconde année lorsque disponible. Stake : observer un vrai marché Game 1 pré-série et ses deux cotes sur `stake.bet`, puis relancer avec le même profil et démontrer l'horodatage d'une nouvelle lecture. Les cas dangereux impossibles à provoquer sans risque sont couverts par fixtures, sans prétendre les avoir observés en réel.

Après implémentation, rendre seulement un bilan factuel : contrôles exécutés et réussis, contrôles échoués, contrôles non exécutés et raison, limites restantes. Les gates de `AGENTS.md` déterminent la validité de chaque partie. Les tests qui ne tournent pas faute de source sont « non exécutés », pas « réussis » ; le reste du développement hors ligne reste possible.
