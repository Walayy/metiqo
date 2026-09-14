---
name: collecte-stake
description: Préparer et implémenter la collecte DOM de stake.bet avec Patchright, Chrome réel et profil persistant, strictement pour Game 1 avant la série.
---

# Stake.bet — Chrome persistant et DOM uniquement

## Rôle et limites

Lire `AGENTS.md` pour les échéances et règles communes. Ce module découvre les rencontres LoL et produit des observations immuables de marchés. Il ne décide ni des identités OE ni des probabilités.

**Choix arrêté : Patchright Python + véritable Google Chrome + profil persistant dédié + lecture du DOM rendu sur le domaine exact `stake.bet`.** Pas de Playwright classique comme collecteur de secours, Chromium fourni par défaut, Stake.com, API GraphQL/REST, interception des réponses JSON métier, WebSocket de cotes, fournisseur externe ou bookmaker supplémentaire. Le navigateur charge normalement les ressources nécessaires au site ; ces échanges ne sont pas une autorisation d'exploiter leur contenu comme source parallèle.

Le domaine est contrôlé sur l'URL effective de la page principale à chaque navigation et avant acquisition. HTTPS requis, `hostname == "stake.bet"`, sans identifiants dans l'URL. Une redirection vers `stake.com`, `www.stake.bet`, un autre miroir ou un domaine ressemblant est `wrong_domain`, pas une réussite. Les CDN utilisés par le site pour ses ressources ne changent pas ce contrôle d'origine des données. Ne pas assimiler une mention commerciale « Stake.com » dans le texte à l'URL effective.

## Configuration et profil

| Clé locale | Convention |
|---|---|
| `STAKE_BASE_URL` | `https://stake.bet` ; domaine non substituable. |
| `STAKE_CHROME_PROFILE_DIR` | Chemin absolu ; défaut `${METIQUO_HOME}/browser/stake`, hors dépôt. |
| `STAKE_NAVIGATION_TIMEOUT_SECONDS` | 45, valeur finie. |
| `STAKE_DOM_TIMEOUT_SECONDS` | 30, attente d'un état qualifié et non délai de sommeil systématique. |
| `STAKE_MAX_RUN_SECONDS` | 180 par passage de découverte ; couverture partielle explicitement signalée. |
| `STAKE_DETAIL_LOOKAHEAD_HOURS` | 48 ; traiter automatiquement les rencontres proches, garder les autres visibles comme à vérifier. |
| Fraîcheur et rafraîchissement | Constantes Stake de `AGENTS.md`, sans duplications locales. |

La documentation Patchright recommande `chromium.launch_persistent_context` avec `channel="chrome"`, `headless=False`, `no_viewport=True` et sans injection de User-Agent/en-têtes [S1]. Utiliser cette configuration avec le répertoire dédié. **`p.chromium` désigne ici l'interface d'automatisation ; `channel="chrome"` sélectionne le véritable Google Chrome.** Vérifier le navigateur effectivement lancé et sa version dans un diagnostic non sensible. Chrome manquant ou incompatible bloque le collecteur ; aucun fallback silencieux vers Chromium.

Installer Google Chrome une seule fois, par son installation normale ou la commande `patchright install chrome` documentée par Patchright [S1]. Ne pas installer à chaque collecte. L'utilisateur peut effectuer sa connexion habituelle dans la fenêtre dédiée ; conserver ce profil entre les exécutions et après redémarrage de l'application. Ne jamais automatiser les champs de mot de passe, copier le profil quotidien, synchroniser le profil dans un cloud, ni exporter son `storage_state` vers le dépôt. Le profil quotidien n'est pas un support d'automatisation à réutiliser [S2].

Un seul propriétaire du profil : verrou applicatif et détection du verrou Chrome. La commande de session manuelle suspend le collecteur et réutilise exactement le même répertoire. À la fin, fermer proprement le contexte puis reprendre après validation. Ne pas supprimer un verrou de navigateur vivant ni réinitialiser le profil pour faire disparaître une erreur. Après crash, diagnostic puis relance sûre ; pas de destruction automatique des cookies.

Les mises à jour normales de Chrome restent permises ; enregistrer la version pour diagnostiquer une incompatibilité et rejouer la recette du collecteur après changement. Ne pas promettre que n'importe quelle combinaison de versions fonctionne. Ni « indétectable » ni « zéro blocage » n'est un critère de réussite.

## Découverte, navigation et couverture

Partir de l'accueil du domaine exact, suivre les liens visibles vers les sports/esports et LoL. Résoudre le chemin réel pendant l'implémentation ; **aucun chemin profond ou sélecteur CSS de marché n'est certifié dans cette archive**. Conserver le chemin vérifié dans la configuration de l'adaptateur, avec sa date de qualification.

Explorer les compétitions et sections pertinentes de façon dynamique. Gérer dépliage, onglets, pagination, « charger davantage », listes virtualisées et affichage différé par leurs états DOM. Conserver un indicateur de couverture et les sections traitées. Un budget de passage atteint signifie « découverte partielle », pas « aucune autre rencontre ». Reprendre au prochain passage, en évitant que les petites compétitions soient systématiquement repoussées derrière les grandes.

La routine unique Stake assure la découverte périodique et, séquentiellement, les détails des rencontres proches ; priorité à celle que l'utilisateur consulte. Lorsqu'une rencontre lointaine est ouverte, la lire à la demande. Coalescer les demandes simultanées ; ne pas créer un navigateur ou une boucle par onglet de Metiquo. Une carte non encore inspectée affiche « marché à vérifier », pas « marché absent ». Le TTL de cote peut être bien plus court que l'intervalle du catalogue : une liste de rencontres connue n'implique pas des cotes actuellement utilisables.

Un événement déjà commencé reste marqué `started_seen=true` pour son identité, même si le DOM repasse par un état incomplet. Un horaire reporté peut être mis à jour uniquement sur une nouvelle observation explicite de la même rencontre toujours non commencée. Conserver les révisions d'horaire et invalider les analyses qui en dépendent.

## Contrat d'observation

Chaque observation qualifiée contient :

| Groupe | Informations |
|---|---|
| Traçabilité | `observation_id`, `collection_run_id`, version d'extracteur et de mapping, `observed_at_utc`, heure d'enregistrement distincte. |
| Rencontre | Sport LoL, compétition brute, équipes brutes, identifiant visible si présent, URL canonique exacte, date/heure prévue UTC, valeur temporelle affichée et contexte de fuseau vérifié. |
| Marché | Libellé exact, éventuel identifiant DOM, contexte de section, `market_key=GAME_1_WINNER`, `game_number=1`, phase de série, état `open/suspended/closed/absent/unknown`. |
| Sélections | Identité/libellé de chaque équipe, éventuel identifiant de sélection, cote décimale brute et normalisée, disponibilité observée. |
| Preuves minimales | Libellés visibles et états ayant qualifié Game 1 et le pré-match ; jamais HTML de page complet, cookie, compte ou ticket de pari. |

Sans identifiant explicite, utiliser une URL canonique stable comme clé externe. Ne supprimer que les paramètres de suivi démontrés inutiles, pas un paramètre qui identifie la rencontre. Si aucune URL stable et non sensible n'est disponible, bloquer l'association ; le couple de noms seul n'est pas une clé. Conserver les horaires, noms et compétition même avec un identifiant : ils servent à détecter les incohérences.

Les textes sont des données non fiables : longueur bornée, échappement, aucune instruction exécutée. L'extracteur rend des objets structurés validés, pas des fragments HTML présentés directement dans Metiquo.

## Qualification exacte du marché

Créer un registre central de correspondances **certifiées sur le DOM réel**, avec libellé brut, langue, contexte de section, numéro de partie, nombre de sélections et preuve attendue de phase/état. Ce registre est distinct des sélecteurs techniques mais reste dans le même module, sans moteur générique.

| Contexte observé | Traitement |
|---|---|
| Libellé explicite de type « Game 1 Winner » / « Map 1 Winner », ou « Winner » sous une section Game 1 explicitement identifiée | Candidat à qualifier ; accepté seulement après certification du contexte complet. |
| « Match Winner », « Series Winner », « Winner » sans portée prouvée | Rejet ; pas de déduction à partir de la cote ou du format BO1/BO3/BO5. |
| Game 2, Map 3, handicap, total, first blood, pari combiné ou promotion | Hors périmètre. |
| Game 1 visible dans une série live, commencée ou proche de son début au-delà de la marge de sécurité | Rejet. |
| Marché suspendu, fermé, retiré, sélection désactivée ou état contradictoire | Pas de cote exploitable. |

Les exemples de libellés ci-dessus ne constituent pas une liste de valeurs actuellement observées sur Stake. Ne pas activer un mapping sans fixture synthétique correspondante et vérification manuelle du marché réel. Une nouvelle langue ou un nouveau libellé reste inconnu jusqu'à qualification ; aucune correspondance approximative à « winner ».

Une preuve positive de pré-série est requise : section pré-match qualifiée, horaire futur interprétable et états concordants de l'événement. L'absence du mot « Live » ne suffit pas. Un score de série, une partie déjà jouée ou un indicateur de démarrage l'emporte sur une heure prévue future. La première Game 1 ne se déduit ni du premier bouton de cote ni de l'ordre des marchés.

Lire les deux équipes et leurs deux sélections dans **le même conteneur de marché**, avec une acquisition DOM cohérente. Utiliser si nécessaire une lecture groupée limitée aux éléments visibles ; vérifier qu'aucune mutation structurante n'a changé la paire pendant l'acquisition. Ne jamais associer deux cotes provenant de pages ou instants incompatibles. Une seule sélection, des doublons ou une égalité de noms non résolue rendent le relevé non qualifié.

## Attentes et détection de casse DOM

Centraliser les locators par rôle : navigation LoL, carte rencontre, horaire, section Game 1, sélections, état du marché, état de session et écran vide. Préférer rôles accessibles, libellés et attributs stables attachés aux composants concernés [S3]. Éviter indices globaux, `nth-child`, classes générées et recherche de nombres sur toute la page.

Attendre le conteneur prêt, l'absence du chargement pertinent et un état terminal observable : données, vide explicite, blocage ou erreur. Pas de `sleep` destiné à deviner la disponibilité, ni d'attente `networkidle` comme preuve unique sur un site dynamique. Utiliser les timeouts comme bornes d'échec.

`observed_at` désigne l'instant où les données ont réellement été lues, pas le démarrage du cycle. Relire une cote identique après une navigation/actualisation réussie et un DOM prêt peut créer une nouvelle observation identique. En revanche, recopier un objet en mémoire ou relire une vieille page restée bloquée/déconnectée ne prouve pas un nouveau relevé. Contrôler les états d'erreur et de reconnexion ; dans le doute, conserver l'ancienne observation sans renouveler son âge. `observed_at` n'est pas une date de dernière modification garantie par Stake.

Une cardinalité inattendue, un parent de marché absent, un conteneur remplacé, un horaire impossible, un chargement permanent ou un libellé inconnu déclenche `dom_changed`/`extraction_uncertain`. Vérifier le sport pour éviter un autre jeu. Cotes finies strictement supérieures à 1, format décimal démontré, deux équipes distinctes, date avec fuseau vérifié et identité stable sont obligatoires. Ne pas convertir des cotes américaines/fractionnaires en supposant leur format.

## États, fraîcheur et indisponibilité

- **Aucune rencontre disponible** : liste LoL totalement chargée, périmètre exploré et état vide explicite ; exécution saine.
- **Marché absent** : rencontre et structure des marchés complètement chargées, Game 1 non proposé ; distinct d'un libellé inconnu ou d'un onglet non exploré.
- **Suspendu/fermé/retiré** : état négatif observé ; invalide immédiatement les précédentes cotes ouvertes de cette rencontre.
- **Collecte impossible** : session, 403/429, challenge, réseau, mauvais domaine, navigateur ou structure incompatible ; ne jamais renvoyer une liste vide de succès.

La requête « cote actuelle » considère la **dernière observation d'état**, y compris négative. Elle ne doit pas chercher uniquement la dernière ligne `open` et ignorer une suspension plus récente. À la lecture et à la simulation, appliquer TTL, état actuel connu, source disponible et marge avant série de `AGENTS.md`. Une erreur d'horloge ou une observation anormalement future bloque ; après veille/reprise, requalifier avant de réactiver un bouton.

N'interpréter un statut HTTP que s'il est observé. Un challenge peut être rendu avec HTTP 200 : contrôler aussi le DOM. Les métadonnées réseau peuvent aider au diagnostic d'erreur, mais aucun payload de cotes n'en est extrait. Les logs suivent la liste blanche de `AGENTS.md` ; aucune capture authentifiée, vidéo, HAR ou trace brute ne sort du profil local.

## Points d'extension et recette

Les seules extensions prévues sont le registre de locators, le mapping de marché, les limites/attentes et le classement des erreurs dans cet adaptateur. Renforcer ces points après observation d'un échec réel, sans nouveau collecteur préventif.

À qualifier sur l'environnement utilisateur : vrai Chrome et répertoire effectivement utilisés, session conservée sur deux lancements, navigation exacte `stake.bet`, liste LoL et compétitions secondaires, Game 1 clairement distinct de la série, horaires/fuseau, cotes ouvertes et transitions suspendu/fermé, publication d'une observation réellement nouvelle. Les fixtures hors ligne démontrent la logique, pas l'accès réel au site. Tests détaillés : skill validation.

### Références primaires

Consultées le 14 septembre 2026.

[S1] Patchright Python, configuration Chrome et installation : `https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python`.
[S2] Playwright, contrat du contexte persistant et profil dédié, référence utilisée par Patchright : `https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context`.
[S3] Playwright, locators : `https://playwright.dev/python/docs/locators`.
