---
name: collecte-oracle
description: Préparer et implémenter la découverte, le téléchargement et la validation Oracle's Elixir avec gdown 6.2.0 et cookies Google locaux.
---

# Oracle's Elixir — un seul collecteur

## Rôle et interface retenue

Lire `AGENTS.md` pour les invariants et échéances communes. Ce module produit un catalogue traçable et des versions locales validées des CSV OE. Il ne fournit ni cotes ni correspondances Stake.

**Choix définitif : gdown 6.2.0 + cookies de la session Google de l'utilisateur.** Lire la page de téléchargement OE avec `httpx`, en extraire son lien Drive, puis utiliser gdown pour découvrir et télécharger. Aucun Drive API/OAuth, miroir GitHub/Kaggle, navigateur alternatif ou transport de téléchargement parallèle.

La version publiée 6.2.0 documente `--cookies FILE` et `--json` ; le JSON décrit des entrées `url` et `path`, pas une révision complète de fichier [OE1]. L'intégration applicative utilise ses fonctions Python publiques : `download_folder` avec `skip_download=True`, `use_cookies=True`, `cookies_file` explicite, puis `download` avec `output` contrôlé, `resume=False`, `quiet=True`, `use_cookies=True`, `cookies_file` et callback `progress`. Le catalogue Python expose `id`, `path`, `local_path` [OE2]. Ne pas attribuer à ces retours des champs `md5Checksum`, `modifiedTime` ou `version` qu'ils ne fournissent pas.

Exécuter le travail gdown dans un sous-processus local annulable, sans shell, avec paramètres construits par l'application. Le résultat rendu au parent est un petit objet validé, pas une copie du stderr. `gdown` n'expose pas de paramètre public `timeout` dans cette interface [OE3] : imposer une échéance globale depuis le parent, plutôt qu'inventer un argument. Cette frontière reste locale à ce module, sans framework de workers.

## Configuration et session

| Clé locale | Valeur ou convention |
|---|---|
| `OE_DOWNLOADS_PAGE_URL` | `https://oracleselixir.com/tools/downloads` ; point d'entrée, pas un identifiant de fichier annuel. |
| `GOOGLE_COOKIES_PATH` | Chemin absolu explicite ; défaut `${METIQUO_HOME}/secrets/google-cookies.txt`. |
| `OE_OPERATION_TIMEOUT_SECONDS` | 900 par découverte/téléchargement, durée maximale configurable. |
| `OE_MAX_FILE_BYTES` | 1 073 741 824 par fichier ; plafond de sécurité ajustable avec justification. |
| `OE_MAX_CATALOG_FILES` / `OE_MAX_CATALOG_DEPTH` | 2 000 fichiers / 8 niveaux ; dépassement = catalogue non qualifié, jamais tronqué discrètement. |
| Échéances | Utiliser exclusivement les constantes OE de `AGENTS.md`. |

Les plafonds de temps, volume et profondeur sont des contrôles Metiquo, pas des arguments natifs supposés de gdown : échéance d'annulation pendant l'opération, contrôle de la profondeur et du nombre sur le catalogue retourné, arrêt du transfert via le callback de progression pour la taille. Ne pas inventer des options publiques absentes.

Le chemin cookies est configuré, non deviné. Prévoir un export **local, manuel et explicite** au format Netscape des cookies Google de l'utilisateur lors de l'installation ; ne demander ni mot de passe ni partage de cookie dans la conversation, l'interface web, Git ou un service tiers. L'application ne lit pas automatiquement tous les profils personnels. Les futures instructions d'installation doivent expliquer l'export local permis par le navigateur réellement utilisé, sans promettre une extraction automatique universelle.

La documentation signale notamment les contraintes de lecture automatique des cookies Chrome récents sous Windows et prévoit l'utilisation d'un fichier Netscape exporté [OE1]. Cela ne modifie pas le choix de Chrome pour Stake : les deux sessions sont distinctes.

Avant gdown : vérifier fichier présent, non vide, lisible **et inscriptible**, permissions, format Netscape, domaines Google attendus, absence de chemin dans Git et cookies non tous manifestement expirés. Respecter les cookies de session ; ne pas traiter automatiquement une expiration exportée égale à zéro comme un cookie inutilisable. gdown peut réécrire le fichier pendant la résolution [OE3] : un verrou exclusif protège export, lecture et écriture. Ne jamais se rabattre sur un téléchargement anonyme parce que le fichier configuré est absent ou invalide.

Un fichier bien formé ne prouve pas une session authentifiée valide. « Cookies chargés » et « accès source validé » sont des états distincts. Une page de connexion, un refus ou une demande de session déclenche `session_required` ; l'utilisateur renouvelle localement le fichier puis relance. Ne jamais afficher le contenu ni les noms sensibles des cookies.

## Découverte dynamique et identité des fichiers

1. Lire la page OE configurée avec TLS vérifié et limites de taille/temps. Résoudre les liens relatifs. Retenir le ou les dossiers Drive explicitement associés aux téléchargements LoL. Valider hôte et syntaxe des URL ; ne pas suivre un lien arbitraire reçu dans un texte.
2. Si aucun lien n'est exploitable, si plusieurs destinations sont incompatibles ou si une connexion remplace la page : `discovery_failed`. Conserver la dernière destination connue pour diagnostic, sans prétendre avoir redécouvert la source. Aucun dossier figé dans le code ne remplace silencieusement ce contrôle.
3. Explorer les dossiers par gdown, inventorier chaque `file_id` et chemin relatif, dédupliquer les identifiants. Le `local_path` proposé par gdown n'est jamais une destination de confiance : les noms reçus ne pilotent pas directement le système de fichiers. Vérifier les limites de profondeur/nombre pendant l'adaptation ; un arrêt à la limite est un échec de couverture.
4. Repérer les CSV de données de parties LoL par famille de nom, extension et emplacement ; extraire une année candidate quand elle existe, puis la confronter aux colonnes/dates effectivement lues. Ne pas coder un nom daté exact, une borne maximale d'année ou une liste de ligues.
5. Enregistrer les années réellement couvertes par chaque contenu. Tout nouvel identifiant pertinent, nouvelle année ou nouveau fichier d'une année connue déclenche une validation. La découverte doit aussi fonctionner au changement d'année sans mise à jour de code.
6. Si deux fichiers prétendent être la même source annuelle : accepter leur identité de contenu lorsqu'elle est prouvée ; sinon exiger une règle de priorité justifiée par la publication OE. Ni « dernier nom alphabétique » ni fusion arbitraire des doublons. Un CSV multi-années ou un découpage nouveau impose de vérifier la couverture et les chevauchements.

Le catalogue vide initial n'est pas un succès. Un catalogue soudainement vide, diminué ou amputé de fichiers connus est `catalog_uncertain` tant que sa complétude n'est pas établie ; ne supprimer aucune donnée locale sur cette seule observation. Vérifier les dossiers imbriqués et les vues partielles. Si gdown renvoie une vue incomplète dans l'environnement réel, signaler la limite ; ne pas annoncer une exhaustivité non prouvée ni installer une autre stratégie en parallèle.

## Changements, fréquence et métadonnées

Distinguer **découvert**, **vérifié**, **téléchargé**, **contenu modifié** et **ingéré**. Conserver au minimum :

| Objet | Métadonnées utiles, non sensibles |
|---|---|
| Catalogue | URL source publique, dossier parent, `file_id`, nom/chemin observé, années candidates puis confirmées, première/dernière apparition, état de couverture. |
| Version reçue | `file_id`, taille locale, taille totale annoncée lorsqu'exploitable, SHA-256 des octets, empreinte sémantique, empreinte de schéma, dates de réception/validation, résultat des contrôles. |
| Contenu | Colonnes, nombre de lignes et de parties, minimum/maximum des dates, maximum global et par compétition, compteurs d'exclusion, année(s) effective(s), version du parseur. |
| Changements | Ajouts, suppressions, corrections par clé métier ; ancien/nouveau hash ; portée affectée ; manifeste de versions actif. |
| Synchronisation | Début/fin, dernière réussite complète, dernière revalidation de contenu, dernière ingestion modifiée, erreur codifiée, prochaine échéance. |

Les métadonnées distantes réellement observables sont optionnelles avec provenance et valeur nulle si absentes. Une date du nom, l'heure de téléchargement, un mtime local ou une taille identique ne prouvent pas l'absence de correction. Le hash local prouve une identité d'octets **entre deux acquisitions**, pas l'état actuel de Drive sans nouvelle vérification.

Politique initiale : catalogue quotidien ; fichier de l'année courante et fichier de l'année précédente pendant les 30 premiers jours de la nouvelle année = actifs. Tout fichier couvrant des parties récentes reste actif, même si son nom est inhabituel. Les autres sont audités par rotation, chacun au moins une fois par période d'archive. Au démarrage, télécharger progressivement tous les fichiers pertinents découverts, sans lancer de téléchargements concurrents.

Pour un fichier dû : une révision distante fiable, si effectivement disponible et qualifiée dans ce même adaptateur, peut éviter un transfert inchangé. **Le chemin de base ne présume pas cette capacité.** Sans preuve distante, refaire un téléchargement gdown borné puis comparer les hashes. Cette revalidation périodique est nécessaire pour détecter une correction à nom constant ; ce n'est pas une boucle de téléchargement à chaque ouverture de page. Nouveau fichier pertinent : validation immédiate. Deux demandes simultanées réutilisent le même travail en cours.

Une empreinte sémantique doit inclure les valeurs canoniques des enregistrements et le schéma, indépendamment d'un simple réordonnancement des lignes ou changement de fins de ligne. Si seuls des octets non sémantiques changent, conserver la trace sans réentraîner inutilement. Si les données utilisées changent, reconstruire les agrégats/Elo depuis la date affectée et invalider les nouvelles analyses dérivées ; les simulations historiques ne sont jamais réécrites.

Un CSV annuel complet ne contenant encore que son en-tête peut être classé `empty_dataset` après validation du schéma et de l'intégrité : année découverte, aucune partie disponible. Il n'invente pas une date de partie ni un échantillon d'apprentissage et ne remplace pas les données des autres années. Un fichier réellement vide, sans en-tête, est rejeté.

Mesurer les dates réelles de publications constatées. Ralentir les vérifications lorsque la source publie moins souvent ; ajuster explicitement s'il existe une cadence plus fréquente démontrée. Ne pas déclarer « publication quotidienne garantie » : cette préparation n'a pas pu vérifier la page OE.

## Téléchargement, validation et promotion

Le parent crée un répertoire de staging unique hors dépôt, sur le même volume que les données finales. Nom local issu d'un identifiant contrôlé, jamais du nom distant. gdown écrit vers cette destination de staging ; son propre `.part` est également non exploitable. Interdire la reprise V1 (`resume=False`) : un fichier distant mutable peut avoir changé entre deux fragments. Après échec, nettoyer les fragments puis recommencer un transfert neuf lorsqu'une reprise est permise.

Contrôles obligatoires avant promotion :

- Fin normale de gdown, absence d'erreur et respect des plafonds. Capture des compteurs `progress`, taille réelle non nulle et comparaison à la taille annoncée lorsqu'elle est exploitable. gdown 6.2.0 comporte un contrôle des téléchargements plus courts qu'une longueur comparable annoncée [OE3] ; ne pas désactiver ni masquer ses exceptions.
- Examiner les octets réellement reçus : refus HTML/doctype/page de connexion/quota/confirmation, JSON d'erreur, archive ou binaire inattendu, même si le nom finit en `.csv` et le statut était 200. Un type HTTP générique n'est pas en soi un échec ; le contenu doit réellement être du CSV attendu.
- Décodage explicite, gestion du BOM, parsing CSV complet et strict, en-tête non vide et non dupliqué, structure cohérente jusqu'à la dernière ligne. Pas de `on_bad_lines=skip`, pas d'encodage choisi au hasard pour faire passer les données.
- Comparer le schéma à un contrat versionné. Colonnes candidates à certifier sur les vrais fichiers : `gameid`, `league`, `date`, `game`, `position`, `teamname`, `result` ; `teamid`, `year`, `side`, `participantid`, `datacompleteness`, `url` selon présence et sémantique observées. Le skill données précise les règles métier. Ces noms ne constituent pas une preuve d'inspection du schéma actuel.
- Détecter suppression/renommage/type incompatible d'une colonne requise : blocage. Une colonne supplémentaire inutilisée est signalée comme extension compatible seulement après contrôle des colonnes requises ; elle n'entre jamais automatiquement dans le modèle. Conserver l'empreinte du nouveau schéma.
- Contrôler dates/années, clés, résultats, deux lignes équipe cohérentes par partie admissible et doublons. Ne pas imposer « exactement 12 lignes » à tous les jeux de données. Les lignes joueur ne deviennent pas des observations indépendantes du modèle.
- Comparer à la version précédente : disparition de lignes, dates qui reculent, résultats corrigés, nouvelle année. Une réduction ou correction peut être légitime, mais doit être expliquée et tracée, jamais confondue avec une simple réussite.

**Limite à ne pas masquer :** un CSV coupé exactement entre deux enregistrements peut encore être syntaxiquement valide. Sans longueur exploitable, checksum distant ou autre preuve indépendante de complétude, le parsing seul ne suffit pas. Classer `integrity_unverified`, garder la dernière version valide et ne pas promouvoir automatiquement. Ne pas fabriquer une taille attendue. La recette sur Drive doit établir quels signaux de taille sont réellement exploitables avec gdown ; un SHA-256 calculé sur un fichier tronqué n'est pas une preuve de complétude.

Une incompatibilité globale de schéma/transport rejette le fichier entier. Une partie individuellement incomplète ou sans identité est exclue en tant que **groupe complet**, avec motif et compteurs ; une anomalie susceptible d'affecter la couverture d'une compétition la rend non qualifiée tant qu'elle n'est pas résolue. Aucune exclusion silencieuse pour améliorer les performances du modèle.

Promotion : valider le CSV entier, préparer le différentiel, déplacer atomiquement le fichier validé vers un nom immutable lié à son hash, puis effectuer la transaction SQL qui enregistre la version et active son manifeste. Un crash entre déplacement et transaction laisse au pire un fichier orphelin non référencé ; il ne rend jamais actif un fichier absent. Une transaction échouée conserve l'ancien manifeste. Le remplacement d'un fichier annuel doit répercuter aussi ses corrections/suppressions, pas seulement ajouter ses nouvelles lignes. Réingérer le même contenu est idempotent.

## Échec, fraîcheur et reprise

Utiliser les échéances de `AGENTS.md` et afficher séparément dernière tentative, dernière réussite, dernière vérification de contenu et partie la plus récente réellement disponible. Calculer le maximum des dates sur les parties valides effectivement reçues, jamais sur le nom du fichier, l'année annoncée ou une date future incohérente. Distinguer ce maximum du maximum des seules Game 1 admissibles utilisées par le modèle. Afficher aussi la date par compétition/équipe dans l'analyse : une partie récente d'une autre ligue ne prouve pas la fraîcheur du segment analysé. Une longue intersaison n'est pas une panne réseau ; le modèle peut néanmoins refuser un historique trop ancien.

Après panne ou validation partielle, conserver les versions déjà valides et leurs dates. Les fichiers en réussite partielle gardent leur traçabilité individuelle ; ne pas avancer la réussite **globale** d'une synchronisation dont des fichiers requis ont échoué. Bloquer l'exploitabilité du périmètre affecté et signaler clairement l'état dégradé.

Erreur réseau/5xx : au maximum deux nouvelles tentatives espacées de 1 puis 5 minutes. 429/quota : respecter `Retry-After` s'il est observable ; sinon prochaine tentative au plus tôt au prochain cycle quotidien. Session/403/challenge : pause nécessitant une vérification manuelle, sans boucle. En l'absence de statut HTTP exposé, conserver `blocked_or_unavailable` plutôt qu'inventer « 429 ». Reprendre seulement après contrôle explicite, avec staging neuf. Jamais d'ancien CSV renommé comme nouveau téléchargement.

## Éléments à qualifier pendant l'implémentation

Vérifier le lien réellement publié par OE, la complétude du catalogue gdown, les années et variantes disponibles, le schéma et la sémantique de `game`, la timezone de `date`, la taille réellement vérifiable, le fonctionnement des cookies locaux et une correction à identifiant constant. Tests détaillés : skill validation, section Oracle. Un échec de ces contrôles ne rouvre pas le choix du collecteur.

### Références primaires

Consultées le 14 septembre 2026.

[OE1] Publication et documentation gdown 6.2.0 : `https://pypi.org/project/gdown/6.2.0/`.
[OE2] Code source versionné, découverte : `https://raw.githubusercontent.com/wkentaro/gdown/v6.2.0/gdown/download_folder.py`.
[OE3] Code source versionné, téléchargement/cookies/intégrité : `https://raw.githubusercontent.com/wkentaro/gdown/v6.2.0/gdown/download.py`.
