---
name: collecte-oracle
description: "Qualifier la découverte du Drive Oracle’s Elixir, télécharger et valider les CSV publiés, puis gérer leurs corrections sans perdre la dernière version valide."
---

# Données Oracle’s Elixir

## Conclusion et preuves au 14 septembre 2026

**Chaîne actuelle non validée.** La page canonique de téléchargement n'a pas été lue intégralement. Un dossier candidat intitulé « OE Public Match Data » a été atteint par un lien public, mais son inventaire exploitable n'a pas été obtenu. **Aucun fichier annuel courant n'a été téléchargé, lu ou haché pendant cette préparation.** Aucun identifiant de fichier 2026, schéma actuel, nombre de parties ni date de dernière partie n'est donc certifié ici.

### Sources consultées et portée

Tous les accès et recherches de ce tableau datent du **14 septembre 2026**. Ne pas utiliser une ancienne publication pour attester un état actuel.

| Lien | Résultat et conclusion permise |
|---|---|
| [Page canonique de téléchargement](https://oracleselixir.com/tools/downloads) | Plusieurs tentatives sans corps exploitable ; un accès à la variante avec `/` final rapporte 403 dans l'outil documentaire. L'origine précise de ce refus n'est pas déterminée. Le lien Drive canonique actuel reste à extraire. |
| [Page de déploiement indexée portant le contenu Oracle’s Elixir](https://master.d36liwrx5rvjnc.amplifyapp.com/tools/downloads) | Le moteur en indexe une annonce de publication quotidienne. À l'ouverture, seul un message demandant JavaScript est obtenu. Ni son actualité ni son équivalence avec le site canonique ne sont démontrées. **Indice documentaire, pas constat d'une cadence actuelle.** |
| [Annonce originale de Tim Sevenhuysen, 24 novembre 2021](https://www.patreon.com/oracleselixir/posts/downloadable-59096881) | L'auteur annonce des changements de noms de colonnes et des ajouts, avec changelog Discord. Confirme le risque historique d'évolution du schéma, pas le schéma de 2026. |
| [README public du projet de mattspooner1](https://github.com/mattspooner1/lol-Esports-Project) | Le document pointe vers le dossier candidat ci-dessous. Il fait foi sur le lien utilisé par cet auteur, **pas** sur celui actuellement publié par Oracle’s Elixir. Ce projet n'est ni un fournisseur retenu ni une preuve de téléchargement réussi ici. |
| [Dossier candidat Google Drive](https://drive.google.com/drive/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH) | Le suivi du lien donne le titre « OE Public Match Data » et une redirection vers une vue mobile, sans liste de fichiers lisible. Les autres ouvertures et la vue `embeddedfolderview` échouent dans l'outil. Ne pas attribuer ces erreurs d'outil à un quota ou à un statut Drive non observé. |
| [HTTPX sur PyPI](https://pypi.org/project/httpx/), [documentation](https://www.python-httpx.org/) | 0.28.1, publiée le 6 décembre 2024 : dernière stable présentée lors de la consultation. Cette ancienneté ne prouve ni abandon ni disponibilité de la source cible. |
| [HTTPX : délais](https://www.python-httpx.org/advanced/timeouts/), [transport](https://www.python-httpx.org/advanced/transports/) | Délais connect/read/write/pool configurables. Les reprises du transport concernent les erreurs de connexion, pas une politique générale pour 429 ou 503 ; la politique applicative doit rester explicite. |
| [Beautiful Soup sur PyPI](https://pypi.org/project/beautifulsoup4/) | 4.15.0, publiée le 7 juin 2026. Un parseur HTML ciblé est disponible ; sa présence ne valide pas l'extraction du catalogue Drive. |
| [gdown : dépôt](https://github.com/wkentaro/gdown), [versions](https://github.com/wkentaro/gdown/releases), [PyPI](https://pypi.org/project/gdown/) | 6.2.0, publiée le 6 septembre 2026, Python ≥3.10. Les notes récentes corrigent notamment des téléchargements incomplets. Depuis 6.0, l'ancienne limite de 50 fichiers par dossier n'est plus une limite générale annoncée. |
| [gdown 6.2.0 : téléchargement](https://raw.githubusercontent.com/wkentaro/gdown/v6.2.0/gdown/download.py), [dossier](https://raw.githubusercontent.com/wkentaro/gdown/v6.2.0/gdown/download_folder.py) | Code versionné consulté : gestion de confirmations publiques et de dossiers. L'interface `download` inspectée n'expose pas les contrôles timeout/reprise/Retry-After nécessaires ici. Voir décision ci-dessous. |

### Recherche Google et essais locaux : limites explicites

Des recherches ont été effectuées avec le moteur intégré sur Oracle’s Elixir, le Drive, les outils et leurs problèmes récents, puis les sources originales ci-dessus ont été ouvertes. **Une recherche sur Google lui-même a été tentée mais n'a pas abouti** : URL de recherche `Oracle's Elixir Google Drive downloads 2026` et requête `stake.bet playwright scraping` inaccessibles par l'outil de consultation ; la tentative HTTPX vers Google échoue au DNS. Le moteur intégré ne peut pas être présenté comme Google. La vérification Google au sens strict reste à compléter lors de la qualification.

Même environnement temporaire que pour Stake : Linux 6.18.44 x86_64 / glibc 2.41, Python 3.13.5, HTTPX 0.28.1, Beautiful Soup 4.14.3, Playwright 1.57.0, Chromium système 144.0.7559.96. **gdown n'était pas installé** ; aucune installation nouvelle ou résolution complète de dépendances n'a été réussie.

| Essai réalisé | Observation |
|---|---|
| HTTPX GET vers la page canonique | `ConnectError`, `[Errno -3] Temporary failure in name resolution`. Le même défaut est observé sans prise en compte de l'environnement HTTPX (`trust_env=False`). |
| Résolution DNS de `oracleselixir.com`, `stake.bet` et `pypi.org` | Échec local : le téléchargement Python direct ne pouvait pas commencer. |
| Navigation Playwright, 14 septembre à 12:22:48.981308 UTC | `net::ERR_BLOCKED_BY_ADMINISTRATOR`, environ 0,01 s ; aucune réponse réseau capturée. |
| Téléchargement d'un CSV courant, lecture complète, second import | **Non exécutés**, faute de découverte et d'accès réseau utilisables. Aucun quota Drive réellement constaté pendant cet essai. |

## Méthode principale proposée, sous condition de preuve

Retenir **HTTPX 0.28.1 + Beautiful Soup 4.15.0**, bibliothèque standard `csv`, `hashlib`, `json`, `pathlib` et `datetime`. Un client HTTP dédié contrôle la découverte publique, les confirmations nécessaires et le téléchargement en flux. Beautiful Soup utilise `html.parser`, sans ajouter `lxml`.

Ce choix privilégie le contrôle des statuts, délais et contenus au lieu d'empiler des wrappers. Il exige toutefois que la page canonique et la liste publique soient effectivement découvrables par cette voie. **Ce prérequis n'est pas démontré.** Si le lien ou le catalogue dépend exclusivement d'une exécution JavaScript, consigner l'échec et réviser cette décision après un essai ciblé ; ne pas figer un faux parseur HTML ni substituer le dossier candidat à la découverte demandée.

**Pourquoi ne pas retenir gdown en fonctionnement normal ?** Son code gère plusieurs particularités Drive utiles, mais l'appel HTTP inspecté ne fournit pas de délai explicite et l'API ne permet pas d'appliquer proprement toute la politique réseau exigée. La version 6.1.1 du 4 septembre 2026 corrige les corps incomplets ; cela ne prouve pas l'absence de quotas. Avec `resume=True`, un fichier final déjà présent peut être ignoré, ce qui ne suffit pas pour détecter ses corrections. Un fork ou une interception de ses méthodes privées alourdirait cette V1. Pas d'import de cookies personnels ni de fonction de cookies navigateur : l'accès public autonome est le seul admissible.

Ne pas intégrer l'API Google Drive authentifiée, un compte de service ou une clé payante. Le dossier public doit rester accessible sans identité Google. Un fichier nécessitant une connexion rend cette voie non conforme au fonctionnement prévu.

## Découverte, cadence et corrections

À chaque cycle quotidien, partir de la **page canonique**, relever son lien de dossier public et comparer avec la dernière provenance validée. Un identifiant de dossier peut être mémorisé comme cache et preuve, pas comme vérité immuable. Un changement de domaine ou de propriétaire apparent n'est pas accepté aveuglément ; mettre en attente la nouvelle provenance et garder la dernière version locale.

Énumérer le catalogue complet avec sa pagination réelle, identifier les fichiers tabulaires candidats et conserver les identifiants Drive. Le nom du fichier est un indice, jamais la clé de version. Ne pas deviner l'année courante, ne pas sélectionner « le dernier nom alphabétique », ne pas s'arrêter aux 50 premiers éléments. Les doublons de millésime ou fichiers datés multiples doivent être résolus par la structure réellement publiée ; sans règle démontrée, rester en ambiguïté plutôt que choisir arbitrairement.

La V1 ne charge que les fichiers nécessaires aux **24 derniers mois**, mais découvre toutes les années du catalogue pour reconnaître automatiquement les nouveaux fichiers. Un changement d'année civile déclenche la découverte, pas la fabrication d'une URL. Les fichiers plus anciens conservés comme archives ne sont pas présentés comme surveillés en continu.

Cadence initiale : **un cycle toutes les 24 heures**, décalage aléatoire de 0 à 30 minutes ; une seule récupération à la fois. Il s'agit d'un réglage conservateur inspiré d'une annonce indexée quotidienne, **pas d'une fréquence actuelle mesurée**. À la première qualification, mesurer au moins une semaine de contrôles quotidiens et adapter l'heure à la publication observée. Distinguer période sans match, publication retardée et collecte en échec.

Pour tous les fichiers du périmètre actif, conserver identifiant, nom observé, URL de provenance, taille, métadonnées distantes réellement disponibles, `checked_at`, hash SHA-256 local et empreinte du schéma. Utiliser une requête conditionnelle seulement si le comportement d'ETag/Last-Modified a été validé ; sinon retélécharger au cycle quotidien. Un nom et une taille inchangés ne prouvent pas l'absence de correction. Prévoir une vérification intégrale hebdomadaire même avec un mécanisme conditionnel qualifié.

Même SHA-256 : pas de nouvelle version ni réimport, mais succès du contrôle enregistré. Hash différent : valider et comparer les jeux de données, puis créer une révision. Un fichier absent d'une réponse catalogue incomplète ne doit jamais provoquer une suppression locale.

## Téléchargement sûr

Paramètres spécifiques : une connexion active, **1 Gio maximum par fichier**, 15 minutes maximum par tentative de téléchargement, 30 minutes maximum pour un cycle. Les délais réseau intermédiaires et les reprises sont définis dans le [skill d'implémentation](../implementation-verification/SKILL.md). Ne pas démarrer une tentative qui dépasse le budget restant. Ces limites devront être confrontées aux tailles réelles, encore inconnues.

Enregistrer d'abord sous un nom interne aléatoire avec extension `.part`, jamais sous un chemin fourni par le serveur. Vérifier HTTPS et chaque redirection ; maximum cinq redirections et deux étapes de confirmation. Autoriser uniquement les hôtes Google précis observés et nécessaires, après validation de leur rôle ; ne pas accepter un suffixe de domaine approximatif, `accounts.google.com` comme téléchargement, des adresses privées ou une redirection quelconque.

Un HTML peut être une confirmation publique connue : interpréter seulement le formulaire attendu, ses champs et son action contrôlée, sans exécuter du JavaScript arbitraire. Un HTML de connexion, quota, erreur ou challenge n'est **jamais** un CSV. Une URL de confirmation expirée impose de recommencer depuis le lien public ; pas de jeton figé.

Vérifier statut, Content-Type, disposition annoncée, premiers octets et structure CSV. Ne pas exiger aveuglément `text/csv` si Drive renvoie un type générique valide ; inversement, un Content-Type CSV ne suffit pas. Vérifier la taille annoncée lorsqu'elle est comparable aux octets reçus et lire le flux jusqu'au bout. Une coupure au milieu d'une ligne, un document tronqué, un encodage non reconnu ou une limite dépassée invalident la nouvelle version. Une troncature alignée sur une ligne peut échapper au parseur : les contrôles de cohérence avec la version antérieure restent indispensables.

Pas de reprise partielle en V1 : supprimer le `.part` échoué et recommencer au cycle autorisé. Cela évite de fusionner deux versions corrigées au moyen d'un Range non validé. Ne promouvoir le nouveau contenu qu'après téléchargement et validation complets.

## Contrat d'import à confirmer sur le vrai schéma

Les noms ci-dessous sont **internes** : ils ne prétendent pas être les en-têtes du CSV actuel. La qualification doit établir le mapping versionné entre les colonnes réellement reçues et : `game_id`, date de partie et précision/fuseau, ligue, saison éventuelle, numéro de partie, identifiants et noms d'équipes, type de participant et résultat.

Lire tout le CSV avec le parseur standard, pas avec un découpage par virgules. Respecter guillemets, caractères accentués, retours à la ligne échappés et BOM UTF-8 éventuel. Ne pas remplacer silencieusement les erreurs d'encodage. Borner un champ à 1 Mio et un fichier à cinq millions de lignes, limites à qualifier avec les vrais fichiers.

Isoler les enregistrements d'équipes : **ne pas confondre les lignes de joueurs avec des parties supplémentaires**. Construire une seule partie canonique à partir de deux équipes différentes et de résultats complémentaires 0/1. Vérifier identifiant unique, date plausible, ligue connue, numéro de partie positif. Les remakes, forfaits et observations partielles doivent être reconnus par les champs effectivement documentés ; si leur statut n'est pas déterminable, les exclure de l'apprentissage et en compter le motif.

Une colonne facultative supplémentaire peut être conservée sans casser l'import. Une colonne requise absente, renommée sans mapping approuvé ou changeant de type met la révision en quarantaine. Les lignes hors LEC/LCK sont ignorées pour le modèle, pas considérées comme corrompues. Une partie incohérente appartenant au périmètre cible bloque la promotion du fichier concerné plutôt que de réduire silencieusement le dataset.

Comparer les clés et contenus avec la version précédente : nouveaux matchs, résultats corrigés, équipes/dates modifiées, doublons, disparitions. Les corrections de lignes existantes sont versionnées. Des suppressions de parties ou une chute inexpliquée de volume imposent une quarantaine jusqu'à preuve d'une publication complète/correction légitime ; ne pas importer automatiquement un fichier possiblement tronqué. Cette maintenance exceptionnelle n'est pas un mode d'import manuel normal.

Écrire les données normalisées sous une révision inactive ; basculer le pointeur actif et les métadonnées **dans une seule transaction** lorsque tous les fichiers requis sont cohérents. Un crash avant validation laisse l'ancienne révision utilisable. Rejouer deux fois la même entrée ne crée aucun doublon. Une correction entraîne la reconstruction déterministe du classement courant, mais ne modifie jamais une ancienne simulation.

Afficher séparément : dernière tentative, dernier contrôle réussi, dernier import ayant changé les données, dernière partie du dataset actif et dernière partie des ligues du périmètre. Un contrôle réussi avec contenu inchangé est bien un contrôle réussi, pas une nouvelle publication. Le modèle applique sa propre règle de fraîcheur au [skill modèle](../modele-simulations/SKILL.md).

## Validation restante

| Vérification ciblée | Preuve à ajouter ici avant qualification |
|---|---|
| Source canonique et catalogue | Lien Drive extrait de la vraie page, nom/ID du dossier, liste datée des fichiers du périmètre, preuve de pagination complète et découverte de nouvelle année sur fixture. |
| Fichier courant | Identifiant réellement publié, nom, date de contrôle, taille reçue, SHA-256, en-têtes, lignes brutes et parties canoniques, maximum des dates après lecture complète. **Toutes ces valeurs sont actuellement non mesurées.** |
| Fonctionnement autonome | Téléchargement sans compte/cookies personnels, second contrôle, réimport identique sans doublon, reprise après coupure sans altérer l'actif. |
| Corrections et schéma | Fixture de même ID/nom avec résultat corrigé ; colonnes supplémentaires, manquantes, doublons et suppression suspecte. Une fixture n'est pas une mise à jour Drive observée. |
| Publication réelle | Contrôles quotidiens datés sur sept jours et au moins un changement de hash réel ; sinon prolonger l'observation et garder « cadence non confirmée ». |
| Cas d'erreur | HTML 200, confirmation, quota, 403, 429/Retry-After, 503, fichier tronqué et crash avant promotion : jamais de CSV actif invalide. |

L'absence actuelle de fichier téléchargé est un blocage concret. Aucun hash, nombre de parties ou résultat d'import provenant d'un ancien projet ne doit être réutilisé comme preuve de cette nouvelle préparation.
