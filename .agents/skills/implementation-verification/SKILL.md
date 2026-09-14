---
name: implementation-verification
description: "Implémenter le socle compact, appliquer une seule politique de fiabilité réseau et de stockage, puis vérifier les parcours et les invariants de Metiquo."
---

# Architecture, fiabilité et recette

## Socle et versions

Un dépôt, un paquet Python, un processus serveur, une base SQLite sur disque local. Aucune application n'est livrée avec cette préparation. La cible proposée est Linux x86_64, sur une distribution prise en charge par le Playwright retenu ; **l'installation complète et les performances restent à qualifier** dans l'environnement final.

Vérification documentaire du **14 septembre 2026** :

| Choix | Source originale, raison et réserve |
|---|---|
| Python 3.13.15 | [Versions officielles Python](https://www.python.org/doc/versions/) : version publiée le 5 août 2026. Branche retenue pour un socle commun éprouvable, sans exiger la dernière branche majeure. Les essais temporaires étaient sous 3.13.5. |
| FastAPI 0.141.1 | [Publication mainteneur sur PyPI](https://pypi.org/project/fastapi/), 29 juillet 2026. Un seul serveur pour pages, actions et collecteurs asynchrones. Installer le paquet minimal, pas tous ses extras. |
| Uvicorn 0.52.4 | [Historique officiel PyPI](https://pypi.org/project/uvicorn/), 19 août 2026. Serveur ASGI, **un worker**. La 0.53.0 est publiée le 14 septembre 2026 ; ne pas la confondre avec la version retenue ni adopter une sortie du jour sans test. |
| Jinja2 3.1.6 | [PyPI](https://pypi.org/project/Jinja2/), 5 mars 2025. Templates et composants serveur ; activer l'échappement HTML. CSS et JavaScript local limités aux interactions du parcours. |
| SQLite via `sqlite3` | [Documentation SQLite](https://www.sqlite.org/wal.html). Pas de serveur ni d'ORM. Choix V1 : journal de rollback **DELETE**, pas WAL ; le bénéfice de WAL ne justifie pas ici une configuration supplémentaire. La documentation signale un correctif de corruption WAL en 3.51.3 et certains rétroportages : ne pas activer WAL ultérieurement sans vérification. |
| pytest 9.1.1 | [Publication mainteneur](https://pypi.org/project/pytest/), 19 juin 2026. Fixtures et tests paramétrés, uniquement en développement. Le navigateur Playwright déjà prévu sert aussi au test de bout en bout, sans plugin supplémentaire obligatoire. |

Versions et conditions des collecteurs : [Stake](../collecte-stake/SKILL.md) et [Oracle](../collecte-oracle/SKILL.md). Ne pas répéter leur étude ni ajouter une seconde bibliothèque équivalente. Les dépendances transitives réellement résolues doivent être verrouillées avec leurs hashes lors de l'installation ; ne pas inventer un lockfile ou prétendre que la combinaison proposée a été testée.

Privilégier les bibliothèques standard pour CSV, calculs, dates, decimal, SQLite et planification. Pas de pandas pour ne lire que quelques colonnes utiles ; pas de scikit-learn pour les quelques formules du modèle ; pas de framework front pour trois vues serveur. Aucun Docker, broker, cache distribué, outil de scraping « universel » ou service d'authentification ajouté par défaut.

## Organisation et fonctionnement

Modules proposés, sans couches de façade : `collectors/stake`, `collectors/oracle`, `data`, `model`, `analysis`, `simulations`, `web`, `jobs`. `data` possède les accès SQL et migrations simples ; `model` reste pur et ne connaît pas Stake ; `analysis` joint une prédiction et une observation de prix ; `web` ne lance jamais directement une collecte longue. Le périmètre comprend toutes les compétitions LoL : aucun filtre LEC/LCK ni priorité de ligue codés en dur. Les champs de compétition couvrent ligues et tournois, régionaux ou internationaux ; conserver les identités distinctes des équipes premières et académies. La couverture des sources, la capacité de suivi et la qualification par compétition sont des états explicites, sans nouveau service ni fournisseur.

Le démarrage futur réalise les migrations nécessaires après sauvegarde, charge l'état local, puis planifie les deux sources lorsqu'elles sont autorisées et qualifiées. Un point d'entrée unique doit suffire ; pas de téléchargement CSV, commande d'entraînement et navigateur à lancer manuellement chaque jour. L'initialisation peut être en cours tandis que l'interface explique ce qui manque.

Planification dans le cycle de vie du serveur : une tâche Oracle et une tâche Stake, chacune avec verrou anti-chevauchement. Persister date prévue, compteur d'échecs et pause pour ne pas relancer une rafale au redémarrage. Après une interruption, une seule exécution de rattrapage, pas une exécution par créneau manqué. Les fréquences exactes appartiennent aux skills des sources.

Limiter les traitements bloquants (lecture CSV, reconstruction de classement) à un exécuteur de travail borné, hors boucle réseau du serveur. N'exécuter qu'une écriture SQLite à la fois. Une connexion appartient à son contexte/thread de travail ; ne pas partager arbitrairement un curseur entre tâches. Le navigateur ne consomme qu'un contexte et une navigation active : cela **ne signifie pas une seule sous-requête HTTP**, car la page charge elle-même des ressources.

## Modèle de stockage minimal

Les noms sont conceptuels ; pas besoin d'ajouter une table pour chaque état ou type de marché.

| Ensemble | Rôle concret |
|---|---|
| `source_runs` | Tentatives, succès, erreurs classifiées, compteurs, prochaines reprises ; ne contient pas de cookies. |
| `source_revisions` | Fichiers, hashes, schémas, provenances et révisions actives/inactives ; manifeste consultable. |
| `teams`, `team_aliases` | Identité canonique et correspondances source/ligue/période vérifiées. |
| `games` | Parties normalisées, rattachées à leur révision ; une ligne par partie canonique. |
| `fixtures` | Rencontres Stake observées, numéro de partie et état courant ; pas de catalogue multi-jeux. |
| `odds_observations` | Relevés immuables du marché partie 1, contenant les deux sélections et leurs états. |
| `model_runs` | Paramètres, classements, manifeste de données, bornes temporelles, périmètre de qualification et statut par compétition/contexte évalué. |
| `analyses` | Photographies de probabilités/explications et lien éventuel avec le relevé de cote ; prédiction prospective de référence identifiée. |
| `simulations` | Photographie enregistrée, mise et résultat déclaré, idempotence et historique compact des corrections. |

Contraintes : clés étrangères, unicité par identifiant de source/révision, complémentarité des deux résultats d'une partie, montants valides et états énumérés. Vérifier aussi les doublons de `game_id` entre fichiers annuels actifs. Une colonne JSON n'est admise que pour une photographie structurée réellement immuable ou un petit historique de correction, pas pour éviter tous les contrats de données.

SQLite : `foreign_keys=ON`, `journal_mode=DELETE`, `synchronous=FULL`, `busy_timeout=5000` ms ; transactions courtes. Enregistrer `sqlite3.sqlite_version` réellement embarquée et appliquer les mises à jour de sécurité de l'environnement. Ne pas confondre version de Python et version de SQLite.

Les fichiers bruts validés restent immuables, nommés par SHA-256, hors répertoire servi par le web. Ils peuvent être compressés sans perte avec `gzip` de la bibliothèque standard après validation ; le hash de référence reste celui des octets CSV décompressés et doit être revérifié à la lecture. Normaliser une nouvelle révision inactive par lots, vérifier la cohérence puis promouvoir l'ensemble requis dans une transaction. Synchroniser sur disque le fichier validé et son répertoire après renommage avant de commettre le pointeur de base. Un changement de pointeur ne doit pas présenter un mélange de versions partielles. Les anciens fichiers nécessaires aux modèles/simulations restent référencés.

Nettoyer automatiquement les fichiers `.part` abandonnés au redémarrage et les révisions inactives **non référencées**, après 30 jours. Conserver au minimum la version active, la dernière valide antérieure et toute version nécessaire à une photographie conservée. Prévoir un budget disque initial de 10 Gio à confirmer sur les vrais fichiers : avertissement à 80 %, suspension des nouveaux imports avant saturation ; aucune suppression d'une preuve référencée pour masquer le problème.

Sauvegarde locale quotidienne de la base avec l'API de sauvegarde SQLite, plus manifeste et fichiers immuables référencés ; sept sauvegardes tournantes. Une sauvegarde n'est considérée bonne qu'après contrôle d'intégrité et essai de restauration sur une copie. Ne pas copier à chaud un fichier de base isolé en espérant une cohérence automatique.

## Politique réseau commune

Les valeurs suivantes sont des réglages Metiquo à qualifier, **pas des quotas officiels** des sites.

| Paramètre | Valeur initiale |
|---|---|
| HTTPX | `connect=10 s`, `read=60 s` pour le téléchargement en flux, `write=10 s`, `pool=5 s` ; un client de source, `max_connections=1`, `max_keepalive_connections=1`, `follow_redirects=False` pour contrôler chaque redirection. |
| Requêtes de découverte HTTPX | Même connexion, délai de lecture réduit à 20 s ; corps HTML plafonné à 10 Mio. |
| TLS / environnement | Vérification des certificats active ; `trust_env=False` dans la configuration de référence, sans proxy implicite. Toute configuration réseau d'entreprise autorisée doit être déclarée et testée, pas contournée. |
| Playwright | Navigation 30 s, action 10 s, attente du payload attendu 20 s, cycle d'extraction d'une rencontre borné à 45 s. Libérer l'opération bloquée à l'expiration. |
| Reprises transitoires | Maximum **3 tentatives au total**, pas 3 reprises après la première. Temporisation Stake 2 puis 8 s ; Oracle 30 puis 120 s ; ajout aléatoire de 0 à 20 %. |
| Pause après épuisement | Stake 30 min ; Oracle 24 h. Après trois cycles échoués consécutifs : respectivement 6 h et 48 h. Une sonde seulement à la réouverture ; revenir au rythme normal après succès validé. |
| 429 sans indication de reprise | Au minimum 15 min pour Stake, 24 h pour Oracle ; jamais de retry immédiat. |
| Concurrence | Une collecte active par source ; maximum deux sources actives. Aucun clic UI ne multiplie ce budget. |

`Retry-After` peut contenir un nombre de secondes ou une date HTTP ; 503 peut simplement indiquer une indisponibilité temporaire. Ces sémantiques sont décrites par la [RFC 9110, §10.2.3 et §15.6.4](https://www.rfc-editor.org/rfc/rfc9110.html), consultée le **14 septembre 2026**. Respecter le plus tardif entre la temporisation locale, la pause de source et l'instant demandé par le serveur. Une date lointaine devient une tâche future persistée, pas une longue attente bloquante ; ne pas la plafonner en reprenant trop tôt. En cas de valeur invalide, journaliser le défaut et appliquer la pause prudente locale.

Ne pas empiler les reprises du transport HTTPX, celles du wrapper et celles du planificateur. Un seul compteur décide. Les redirections/confirmations normales sont comptées séparément et plafonnées dans le skill Oracle. Les rechargements automatiques ou reconnexions de la page Stake doivent aussi être mesurés : si la page insiste pendant un refus, arrêter le contexte pour respecter la pause.

### Classification et action

| Observation | Traitement attendu |
|---|---|
| DNS, connexion interrompue, timeout | Erreur réseau/environnement ; reprises bornées puis pause. Ne pas attribuer un échec DNS à Cloudflare. |
| Certificat TLS invalide | Erreur de sécurité/configuration ; aucun `verify=False`. Pas de donnée importée, diagnostic conservé. |
| 403 | Accès refusé. Pas de boucle de retries, rotation d'identité ou changement de domaine. Désactiver la collecte concernée jusqu'à clarification de l'accès/configuration autorisés. |
| 429 | Limitation de débit : `Retry-After` prioritaire, pause de la source et pas seulement de la sélection. |
| 500/502/503/504 sans autre preuve | Erreur serveur ou intermédiaire ; reprises transitoires bornées. Un en-tête `Server: cloudflare` ne prouve pas un challenge. |
| `cf-mitigated: challenge`, page CAPTCHA ou challenge reconnu | État challenge, conserver la preuve minimale non sensible, arrêter la collecte autonome ; un CAPTCHA humain régulier ne remplit pas l'objectif. Référence de détection dans le skill Stake. |
| 401 ou redirection connexion | Session/accès requis. Pour Stake : une recréation de contexte public au plus ; si connexion nécessaire, bloquer. Pour Drive : accès public non conforme, aucun login automatique. |
| HTML de quota Drive, même en 200 | Quota de téléchargement ; suspendre au moins 24 h ou davantage si la source le demande ; garder la dernière version valide. |
| 404 / marché disparu | Ressource absente ou état inconnu ; ne pas inventer un résultat. Redécouvrir au prochain cycle normal, sans fabriquer une URL de rechange. |
| 200 avec HTML inattendu, JSON/CSV invalide, schéma changé | Erreur de contenu/parsing, pas succès technique. Quarantaine sans modification du jeu de données actif. |
| `ERR_BLOCKED_BY_ADMINISTRATOR` | Politique de l'environnement, distincte du serveur. La préparation l'a réellement rencontrée ; ne pas la désactiver pour présenter un test réussi. |

Une erreur reconnue comme challenge n'est pas en même temps une erreur 503 ordinaire réessayée en boucle : la catégorie la plus spécifique prime. Ne jamais compter « transport réussi » comme « collecte validée ».

Journal structuré : date UTC, source, run/attempt, durée, hôte, chemin expurgé, statut HTTP si réellement reçu, catégorie et certitude de diagnostic, taille, hash de contenu utile, nombre d'éléments validés/rejetés et prochaine reprise. Exclure cookies, Authorization, paramètres signés, jetons de confirmation, données de profil et secrets. Retenir des erreurs détaillées localement pendant 30 jours, pas des pages de compte complètes. Un extrait de corps inconnu doit être borné et expurgé avant journalisation.

## Sécurité et simplicité d'usage

Écoute sur **127.0.0.1** par défaut. Aucun compte ni gestion multi-utilisateurs. L'accès distant ou depuis le LAN n'est autorisé qu'avec un contrôle d'accès réseau déjà établi et une terminaison HTTPS adaptée ; ne pas publier une application anonyme sur `0.0.0.0` pour la rendre accessible au téléphone. La conception responsive ne nécessite pas d'exposer le serveur pendant sa validation.

Limiter les hôtes acceptés et les origines des écritures ; pas de CORS permissif. Actions d'écriture JSON de même origine avec validation serveur, jeton anti-CSRF et contrôle Origin/Host. Les formulaires restent de vrais contrôles HTML, avec un petit gestionnaire JavaScript local pour envoyer le JSON et préserver les saisies. Pas de dépendance multipart, car aucun upload n'est prévu. Les GET ne créent ni simulation ni collecte. Borner les corps JSON d'action à 16 Kio, valider types et valeurs, et utiliser uniquement du SQL paramétré.

Échapper les données externes dans les templates ; aucun HTML/SVG externe inséré comme contenu sûr. CSP locale restrictive, absence d'`unsafe-eval`, scripts/styles hébergés localement ; prévoir le script de thème précoce sans autoriser tous les scripts inline. Pas d'URL arbitraire saisie par l'utilisateur : les seules destinations réseau sont celles découvertes et contrôlées pour les deux sources.

Utiliser un utilisateur système non privilégié, répertoire de données non public, permissions restrictives et arrêt propre du navigateur. Les horloges doivent être synchronisées ; enregistrer UTC en ISO 8601 avec offset. Ne jamais tirer un instant UTC d'un libellé affiché sans fuseau vérifié.

Budget de performance à mesurer sur la machine finale : navigation locale courante p95 <300 ms hors démarrage, aucun traitement réseau externe dans le chemin synchrone d'une page, CSS/JS initiaux compressés ≤80 Kio hors logos, pas de rendu de tout l'historique en une page. Pagination de 50 simulations suffit. Ces budgets ne sont pas des benchmarks obtenus pendant la préparation.

## Ordre de réalisation après préparation

**Étape 1 — Faisabilité uniquement.** Compléter les essais des sources, les conditions d'accès et le mapping du marché exact. Utiliser des vérifications temporaires, pas construire déjà l'application. Figer ensuite une méthode par source et ses fixtures expurgées. Si aucune méthode autonome satisfaisante n'est démontrée, documenter le blocage ici et dans le seul skill concerné ; ne pas remplacer les sources.

**Étape 2 — Noyau et données.** Implémenter stockage, validation/corrections/idempotence, fonctions du modèle, test chronologique et calculs de simulation. Une qualification statistique négative est un résultat valide ; une extraction cible fausse ne l'est pas.

**Étape 3 — Parcours complet.** Construire les trois vues avec les composants du skill interface ; relier les actions au noyau testé, puis valider fraîcheur en temps réel, reprise après interruption et conservation des photographies.

Pas d'outil de tickets, longue nomenclature de lots ou comité d'architecture. Mettre à jour la preuve concernée lorsqu'un jalon est réellement atteint.

## Recette compacte

Les fixtures synthétiques sont identifiées comme telles. Aucun test réseau ne s'exécute par défaut dans la suite unitaire ou à chaque commit ; les essais de fiabilité des sources sont un ensemble explicite, limité et autorisé.

| Priorité | Vérification | Critère de réussite |
|---|---|---|
| P0 | Contrats des sources | Identité exacte de partie/équipes, données requises extraites réellement, cadence, couverture par compétition et restrictions consignées. Les preuves documentaires seules ne passent pas ce test. |
| P0 | Toutes les compétitions LoL | Aucun filtre ni priorité LEC/LCK ; ligue régionale, académie distincte et tournoi international admissibles au périmètre. Une couverture absente/non vérifiée ou une limite de suivi reste visible ; aucune donnée ni qualification n'est fabriquée. |
| P0 | Calculs indépendants | Exemples numériques et complémentarité du skill modèle vérifiés ; les cotes ne modifient aucune probabilité. |
| P0 | Chronologie | Ajouter une partie future ou corriger plus tard un fichier ne change jamais une prédiction historique ; pas de sélection de paramètres sur le test final. |
| P0 | Import transactionnel | HTML 200, CSV tronqué, schéma incompatible, doublons inter-fichiers et crash avant promotion laissent l'actif intact ; second import identique sans doublon. |
| P0 | Fraîcheur / erreurs | Suspendu, live, inconnu, ancien cache et cote >120 s bloquent l'opportunité ; une relecture ne rajeunit aucune donnée. 403/429/503 et challenges restent distingués. |
| P0 | Reprises | Horloge et hasard contrôlés dans les tests ; respecter dates/secondes de Retry-After, budgets, pause persistée et redémarrage sans rafale. |
| P0 | Parcours | Rencontre → analyse → simulation → résultat → bilan fonctionne ; double clic idempotent ; changement de cote pendant la saisie sans validation silencieuse. |
| P1 | Accessibilité / thèmes | Toutes les vues et états de la recette UI passent aux formats prévus, clavier compris ; logos de secours, scrollbar et absence de flash de thème contrôlés. |
| P1 | Sécurité / restauration | Écriture inter-origine rejetée, échappement HTML/SVG, secrets absents des logs, accès local par défaut, restauration d'une sauvegarde vérifiée. |

Une recette complète peut afficher « aucune opportunité suffisamment fiable ». Elle ne peut pas déclarer le produit alimenté automatiquement lorsque les collecteurs sont encore en démonstration ou bloqués. Aucun test applicatif de ce tableau n'a été exécuté dans l'archive de préparation, qui ne contient pas d'application.
