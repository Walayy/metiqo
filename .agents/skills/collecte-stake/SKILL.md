---
name: collecte-stake
description: "Qualifier puis collecter exclusivement les cotes Stake.bet du vainqueur de la partie 1 avant la série, avec identité et fraîcheur démontrées."
---

# Collecte Stake.bet

## Conclusion au 14 septembre 2026

**NON VALIDÉE.** Une page de rencontre sur le domaine exact a été consultée par l'outil documentaire. Aucun corps de réponse réseau du marché cible, identifiant de marché/sélection, état de suspension ou relevé répété exploitable n'a été obtenu. La méthode principale **proposée** est Playwright, pas une solution déjà fonctionnelle. Aucun endpoint GraphQL, REST, WebSocket ni sélecteur CSS n'est inventé dans cette préparation.

### Registre des preuves

Les liens ci-dessous ont été consultés le **14 septembre 2026**. Une restitution textuelle par l'outil de recherche ne prouve ni le HTML initial reçu par HTTPX, ni le comportement du navigateur final.

| Source originale | Constat et limite |
|---|---|
| [Stake.bet, page LoL française](https://stake.bet/fr/sports/league-of-legends) | Présente Natus Vincere–Movistar KOI, LEC 2026 Summer Playoffs, le 18 septembre, avec « Vainqueur du match - Two options », 2,90 / 1,42. Ces nombres illustrent un marché **exclu** et ne sont pas des cotes fraîches utilisables. |
| [Rencontre sur Stake.bet](https://stake.bet/zh/sports/league-of-legends/international-1/lec-2026-summer-playoffs-t3/834160-natus-vincere-movistar-koi) | Le lien suivi aboutit à la locale `/zh`, sans quitter le domaine. Onglets Main et Map 1 à Map 5 visibles dans le texte ; seuls les marchés principaux sont restitués. `834160` est observé dans l'URL, pas confirmé comme identifiant d'API. L'heure 15:00 est affichée sans fuseau établi. |
| [Conditions publiées sur le domaine exact](https://stake.bet/policies/terms) | §14.3 cite notamment la France parmi les juridictions interdites ; §17.3 vise les logiciels automatisés analysant/capturant les informations, §17.4 les interventions sur la sécurité. Le titre du document mentionne Stake.com : cela ne change pas le domaine consulté et n'autorise aucune substitution. Faire clarifier l'application de ces conditions à la collecte envisagée. |
| [Playwright : documentation Python](https://playwright.dev/python/docs/intro), [réseau](https://playwright.dev/python/docs/network) | Possibilité documentée d'observer réponses et WebSockets du navigateur. Ce sont des capacités générales, pas une preuve de compatibilité Stake.bet. |
| [Playwright sur PyPI](https://pypi.org/project/playwright/), [notes de version](https://playwright.dev/python/docs/release-notes) | Version 1.62.0 publiée le 31 juillet 2026 ; notes 1.62 : Chromium 151.0.7922.34 et fin de prise en charge de Debian 11. Les essais locaux utilisent d'autres versions, précisées ci-dessous. |
| [Cloudflare : dépannage](https://developers.cloudflare.com/cloudflare-challenges/troubleshooting/), [détection de challenge](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/) | Cloudflare documente des incompatibilités avec l'automatisation. `cf-mitigated: challenge` identifie une page de challenge ; ce type de réponse est HTML. Cela ne démontre pas que les échecs locaux étaient des challenges. |

Des références à des ressources Oddin figurent sur la page de rencontre. Elles ne prouvent pas l'origine ou le protocole des cotes. Ne pas transformer un lien de widget en fournisseur de remplacement.

### Essais techniques réellement exécutés

Environnement temporaire : Linux x86_64, noyau 6.18.44, glibc 2.41, Python 3.13.5 ; HTTPX 0.28.1 ; Playwright 1.57.0 ; Chromium système 144.0.7559.96. Ce n'est pas l'environnement de déploiement ni le couple Playwright/Chromium proposé.

| Essai | Résultat observé | Interprétation |
|---|---|---|
| HTTPX GET sur la page LoL, le 14 septembre | `ConnectError`, `[Errno -3] Temporary failure in name resolution`, environ 5,01 s | Échec DNS local ; aucun statut HTTP du site. |
| Navigation Playwright sur cette page, le 14 septembre à 12:22:48.909813 UTC | `net::ERR_BLOCKED_BY_ADMINISTRATOR`, environ 0,02 s ; aucune réponse capturée | Restriction administrative du navigateur local, pas une preuve de 403, CAPTCHA ou Cloudflare. |
| Lecture documentaire des pages précitées | Texte de rencontre et marchés principaux obtenu | Utile pour le périmètre ; insuffisant pour la faisabilité opérationnelle. |

Le navigateur était headless, avec contexte temporaire fr-FR / Europe-Paris. L'inspection locale sous root a nécessité un lancement sans sandbox ; **ne pas reprendre cette configuration en production**. Aucun cookie personnel, connexion Stake ou contournement de la politique réseau n'a été utilisé. Aucun navigateur interactif distant connecté n'était disponible. Aucun test de stabilité de plusieurs heures n'a été effectué : il n'existe pas de premier relevé cible valide à répéter.

## Choix à confirmer avant implémentation

**Playwright 1.62.0 + Chromium fourni par cette version**, un navigateur et un contexte dédiés aux pages publiques Stake.bet. Motif : l'inspection des onglets, de leurs états et des échanges réseau doit pouvoir être faite dans le même environnement. La nécessité réelle du rendu JavaScript reste à prouver ; la lecture documentaire ne suffit pas pour l'affirmer.

Comparer une seule fois, pendant le diagnostic, le corps HTML obtenu par HTTPX avec les réponses et le DOM du navigateur. Si le HTML complet suffit effectivement, remplacer cette décision par HTTPX et retirer Playwright du collecteur ; documenter ce changement ici. Sinon sélectionner **un seul canal de vérité** dans Playwright : réponse structurée utilisée par la page, de préférence, ou DOM sémantique si lui seul permet une extraction complète. Ne pas conserver une cascade silencieuse de trois extracteurs.

Prérequis : environnement et territoire autorisés, DNS et TLS fonctionnels, système pris en charge, dépendances Chromium installées. Installer le navigateur correspondant à la bibliothèque, par `python -m playwright install --with-deps chromium` lorsque la plateforme le permet. Tester ensuite sous utilisateur non privilégié, sandbox active. Fixer locale et fuseau pour la reproductibilité, pas pour masquer la localisation réelle. Ne pas falsifier les propriétés du navigateur.

Session publique conservée seulement pendant la vie du processus. Ne pas importer le profil navigateur personnel. En cas d'expiration, autoriser une seule recréation d'un contexte public ; si une connexion, un CAPTCHA ou une intervention humaine devient nécessaire, arrêter la collecte autonome. Ne pas enregistrer de pari, remplir de bulletin ou appeler un endpoint d'écriture Stake.

## Contrat de donnée à démontrer

Le catalogue vise **toutes les compétitions LoL présentes sur Stake.bet**, sans priorité LEC/LCK ni exclusion des ligues régionales, académies, qualifications ou tournois internationaux/interrégionaux. Découvrir les compétitions réellement publiées, sans liste fermée ni URL de tournoi devinée. Une rencontre observée sans marché explicite du vainqueur de la partie 1 reste signalée comme non exploitable ; sa cote de série ne la remplace jamais. La présence et l'extraction vérifiées sur une compétition ne prouvent pas la couverture des autres ; les exemples LEC du registre restent des observations historiques limitées.

Une observation admissible comprend les champs suivants, issus d'un relevé cohérent :

| Groupe | Champs et règle |
|---|---|
| Origine | `source=stake.bet`, URL réelle de page, URL finale ; tout changement de bookmaker/domaine de page est bloquant. Les hôtes techniques ne sont autorisés que s'ils sont réellement appelés par cette page et documentés pendant l'inspection. |
| Rencontre | Identifiant stable, compétition/saison, deux équipes et identifiants source, date de série normalisée en UTC, format si exposé. Une heure sans fuseau démontré est bloquante. |
| Partie | Numéro **1** explicite ; identifiant de partie s'il existe, sinon clé `(event_id, map_number)` justifiée. Aucun calcul à partir du titre « match ». |
| Marché | Identifiant ou clé composite stable documentée, libellé original, type normalisé `map_winner`, deux sélections d'équipes seulement. L'équivalence sémantique doit être prouvée une fois sur une capture. |
| État | État de rencontre, de partie, de marché et de sélection, avec les valeurs source conservées. Le mapping vers `prematch/open/suspended/closed/live/unknown` est documenté à partir de valeurs observées. |
| Prix | Cote décimale finie strictement supérieure à 1 ; identifiant et équipe de chaque sélection ; aucune confusion avec handicap, vainqueur de série ou pari spécial. |
| Fraîcheur | `received_at_utc`, `observed_at_utc`, éventuel `source_updated_at`, âge du cache si présent, identifiant du relevé et empreinte du contenu utile. |

Ne pas inventer un timestamp serveur absent. Une simple relecture du DOM ou un recalcul d'analyse ne renouvelle pas `observed_at`. Une réponse complète récemment revalidée peut confirmer une cote inchangée ; un cache non revalidé conserve sa date/son âge effectifs. Un delta WebSocket ne renouvelle que les entités effectivement confirmées, pas tout le catalogue. Un heartbeat ne rafraîchit aucune cote.

Conserver les deux sélections dans la même observation atomique. Un marché incomplet n'est pas comparable. Dédupliquer le retraitement d'un même relevé par identifiant/empreinte, mais conserver les relevés réellement distincts même lorsque le prix ne bouge pas.

## Fréquences et état exploitable

Réglages initiaux de **prudence à qualifier**, pas limites officielles de Stake : catalogue de toutes les compétitions LoL toutes les **15 minutes** ; suivi de la partie 1 dans les **3 heures** précédant la série ; au maximum **quatre rencontres** suivies, choisies par début le plus proche, sans priorité de ligue. Les autres restent signalées « non suivies : capacité de collecte ». Ce plafond technique initial ne restreint pas le périmètre sportif et ne démontre pas un suivi exhaustif. Mesurer sa capacité sur les chevauchements réels entre compétitions avant de qualifier la couverture obtenue.

Un seul cycle de navigation actif. Viser un relevé complet par rencontre toutes les **60 secondes**, avec variation de ±10 %, sans provoquer une navigation par utilisateur. Répartir les rencontres dans le cycle. Ce rythme n'est acceptable que si les durées réellement observées le permettent sans chevauchement ; sinon réduire le nombre suivi, pas multiplier les navigateurs. Pour un flux déjà poussé par la page, ne pas créer de polling réseau supplémentaire ; valider la façon d'obtenir une confirmation complète récente.

Expiration locale : **120 secondes** maximum pour la cote ; état source le plus récent inconnu, suspendu, fermé ou live = blocage immédiat, même si le prix a moins de 120 secondes. Bloquer aussi à **deux minutes du début programmé** et dès qu'un début réel est connu, selon la première limite atteinte. Aucun mécanisme ne garantit de détecter instantanément un début anticipé : cette limite doit être indiquée et mesurée. En cas d'horloge locale non fiable, bloquer.

Un report ne remet pas automatiquement une partie live en avant-match. Exiger une correction source cohérente et une nouvelle observation complète. Une rencontre disparue du catalogue n'est ni annulée ni terminée par déduction : passer à état inconnu. La disparition d'un marché ne signifie pas cote nulle. La dernière valeur reste consultable comme historique, jamais comme nouveau relevé.

Délais, reprises, classification des erreurs et journalisation : appliquer exclusivement la politique du [skill d'implémentation](../implementation-verification/SKILL.md), avec arrêt immédiat des usages concernés en cas de refus d'accès.

## Validation restante — condition de passage

**Avant tout développement du collecteur final**, compléter ici un essai dans l'environnement réellement visé, après clarification des accès :

1. Consigner système, versions, navigateur, mode headless/headed, territoire effectif, locale, fuseau et conditions d'accès. Sur une rencontre réellement à venir, identifier HTML initial, rendu JavaScript, réponses XHR/fetch/WebSocket utiles et leurs limites. Conserver une preuve expurgée des secrets et le mapping de chaque champ.
2. Extraire **les deux cotes du vainqueur de la partie 1** et tous les champs obligatoires. Croiser avec l'affichage de cette même page, à la même heure. Vérifier l'inversion éventuelle de l'ordre des équipes et les noms longs. Une seule cote de série ou des onglets vides = échec.
3. Réaliser au moins **30 relevés planifiés espacés d'une minute** sur une fenêtre pertinente, puis observer au moins **deux journées de compétition** avec redémarrage autonome. Compter tous les créneaux, y compris les échecs et les marchés absents. Objectif initial : ≥95 % d'observations admissibles lorsque le marché cible est réellement ouvert, **zéro relevé erroné, zéro faux rafraîchissement, zéro intervention humaine**. Ce seuil n'est pas une garantie future.
4. Observer, si disponibles, une suspension/reprise et le passage au début de série. Tester les états non rencontrés sur fixtures identifiées comme synthétiques, sans les compter comme preuves de comportement du site. Un état réel essentiel non observé laisse la qualification partielle.
5. Consigner les compétitions réellement découvertes et celles dont le marché cible a été extrait, avec les absences, variantes de marché et limites de capacité. Vérifier les ligues régionales, académies et rencontres internationales lorsqu'elles sont présentes ; ne pas généraliser une preuve LEC/LCK à l'ensemble de LoL. Une compétition non observée reste de couverture non vérifiée, pas hors périmètre.

Statut à maintenir : accès autorisé **à clarifier** ; extraction cible **non réalisée** ; cadence durable **non testée** ; transitions de marché **non observées**. Tant que ces réserves bloquantes persistent, ne pas déclarer le besoin d'alimentation automatisée satisfait.
