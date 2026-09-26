# LoLTV : pages, données et limites

Analyse réalisée le **21 septembre 2026**. Ce document décrit les pages effectivement observées et le collecteur livré ; il ne garantit ni la couverture mondiale ni la disponibilité future du site.

## Parcours public

| Page                                                                                    | Rôle                        | Données exploitées                                                                                |
| --------------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------- |
| [Matchs](https://loltv.gg/matches)                                                      | Directs et calendrier futur | Identifiants de rencontre/équipes, tournoi, date avec offset, BO, statut, score, liens des fiches |
| [Résultats](https://loltv.gg/matches/results)                                           | Historique paginé           | Mêmes identités, séries terminées et scores                                                       |
| Pages `matches/all/N` et `matches/results/all/N`                                        | Pagination réellement liée  | Progression jusqu’à la borne de la fenêtre de Paris, sans parcourir l’ensemble des archives       |
| [G2–Movistar KOI](https://loltv.gg/match/2026-09-20-g2-esports-vs-tbd)                  | Série terminée              | Trois cartes ; la première contient dix joueurs, dix bans et les camps dans le HTML observé       |
| [Skillcamp–Arctic Pandas](https://loltv.gg/match/2026-09-21-skillcamp-vs-arctic-pandas) | Série observée en direct    | Sélecteur Game 1/2/3, compositions et K/D/A chargés dans le DOM                                   |

Le calendrier et les résultats utilisent le transport React Flight embarqué dans `self.__next_f.push`. Le parseur décode uniquement les chaînes JSON, sans exécuter de JavaScript. Les fragments peuvent couper un objet ; les enregistrements texte utilisent une longueur en octets UTF-8. L’identité provient de l’ID de rencontre, pas du slug : le slug de la finale contient encore `tbd` alors que les équipes sont publiées.

La fiche doit exposer le même `matchId` et les deux noms ou alias de la liste. Le score est lu dans son élément exact : la première expression `15:00` de l’en-tête est un horaire. Le JSON-LD `eventStatus` a été observé à « Scheduled » sur une série terminée ; il n’est pas utilisé comme statut.

Les profils d’équipes et leurs effectifs sont des informations d’identité. Ils ne prouvent pas à eux seuls la composition d’une ancienne carte. Le DOM doit montrer les dix participants ; leur rôle peut être complété par une correspondance unique avec le rôle publié de ce même joueur.

## Bans, camps et statistiques

Les objets embarqués `games[].teams[]` peuvent publier `bans[].champion_id`, `side`, `win`, `players`, les objectifs et l’or total. La première carte de G2–Movistar KOI contient ces informations. Les cartes suivantes du même échantillon ont des équipes de remplissage sans joueurs : leurs zéros ne sont pas des statistiques mesurées. Un camp de remplissage observé sur Skillcamp contredisait la carte ensuite affichée ; il reste donc inconnu tant que l’enregistrement n’est pas complet.

Le sélecteur de carte change l’URL vers `?game=N`. Pendant « Connecting… », les anciennes compositions peuvent rester visibles. Le lecteur attend la sélection, la disparition du chargement, dix joueurs et deux lectures stables des noms/champions avant de publier. Il n’utilise pas la position gauche/droite comme camp.

Le DOM expose les champions via les noms des images, les niveaux, K/D/A, CS et les tours avec un libellé accessible. Les valeurs d’or affichées à côté des joueurs sont des **différences** : elles ne remplissent jamais le champ d’or total. Les objectifs représentés uniquement par une icône non libellée ne sont pas interprétés arbitrairement. Aucun ban n’était affiché dans le DOM live inspecté ; la source HTML ou un historique Oracle complet peut les fournir, sinon ils restent absents.

Le réseau naturel observé comprend un flux sur `feed.loltv.gg/feed/<game-id>`, des ressources Next.js, images du CDN et ressources tierces. Le composant public `Game` utilise `getFeedSession(matchId)` pour ouvrir une consultation anonyme, puis un `fetch` avec cookies ; le site actualise son flux live toutes les cinq secondes. Un accès sans session a répondu 401. Le parcours normal (action Next.js publiée dans le script lié, cookies anonymes du même client, GET du flux) a ensuite répondu 200 depuis Docker. Le collecteur découvre l’identifiant d’action, le met en cache par URL de script et conserve les cookies seulement en mémoire. Il espace les lectures selon son propre budget ; il ne reproduit pas le polling toutes les cinq secondes.

Le flux publie l’ID de carte, le statut, l’horodatage, les équipes BLUE/RED, les dix joueurs avec leur tag d’équipe, les objectifs et l’or réellement acquis. Les cinq tags doivent correspondre au code exact d’une équipe de la fiche ; un seul joueur contradictoire ou une ambiguïté empêche la fusion. Les zéros de remplissage de la fiche ne complètent jamais les objectifs absents du flux. Le résultat final attend un vainqueur explicite dans le HTML. L’échantillon Skillcamp–Arctic Pandas, carte 3, donne Skillcamp BLUE et Arctic RED ; le HTML de remplissage annonçait l’inverse. Le flux observé ne contient pas de bans. Les bans HTML et ceux d’Oracle restent donc des compléments distincts, sans garantie de présence pour chaque rencontre.

## Publication et rapprochement

Le calcul de durée suit l’horloge des événements du flux. Le composant public `Game` soustrait les pauses avec `clock_end` avant d’afficher le temps de la trame ; l’ancien collecteur abandonnait toute durée dès qu’un événement `PAUSE` existait. Le parseur applique maintenant les corrections cumulées de la source, y compris ses entrées qui se chevauchent, privilégie `clock_end` sur l’événement de fin (un décalage d’une seconde existe dans les relevés) et utilise une fin explicite lorsque `clock_end` manque. Une pause ouverte borne le temps au dernier jeu observé ; une reprise sans début identifiable laisse la durée inconnue. Aucun calcul ne dépend de l’heure de consultation. Lorsque la carte utilise le flux, cette durée prime également sur le HTML incomplet, dont le temps peut inclure les pauses. Une relecture des seules métadonnées ne peut pas écraser ce temps corrigé ; la provenance interne `durationSource=loltv-event-clock` le distingue.

Vérification du 21 septembre : Pyramid–LODIS, carte 2 (`59de34363894e471c173fb9f`), trame de `19:14:39.960Z` : première horloge `1790015930000`, dernière `1790018079000`, pause de 94 secondes, soit **2 055 secondes / 34:15**. La fiche LoLTV affiche également **34:15**. Le flux complet est conservé dans l’artefact `5a647edf24787afeddec1c3c5a535eb3e1edbe248acf087a868843bc5810068e.json.gz` ; le script consulté a l’empreinte d’artefact `b44745d3736e568e536a7eea5b4a73069bce95efdc8e4b6c006a5eb22208b85f`. Le calcul n’ajoute aucune requête source.

La première carte de Pyramid–LODIS contient trois corrections de pause (45, 11 et 14 secondes), dont deux se chevauchent. Le site les cumule : **36:28**, confirmé dans le navigateur. Réunir arbitrairement les intervalles aurait donné **36:39**, différent de la valeur affichée par LoLTV. Les tests conservent ces deux cas réels.

Le calendrier publie chaque lot immédiatement ; les fiches ajoutent leurs données progressivement. Les documents compressés, empreintes et dates de récupération sont conservés. Le cache d’une carte terminée évite de la rouvrir inutilement, mais ne génère pas de nouvelle observation. Les détails antérieurs compatibles restent disponibles quand un nouveau calendrier ne contient que le score.

La vérification de latence du 21 septembre a mesuré 90–93 secondes entre lectures de plusieurs cartes live, avec des maxima de 108–117 secondes : une échéance de 60 secondes pouvait manquer le tick cron suivant. Une réponse sans horodatage pouvait également reporter le direct de quinze minutes. Le collecteur vise désormais trente secondes, réveillées indépendamment de l’arrondi à la minute pour le cron continu ; il réutilise les sessions anonymes par rencontre, priorise la carte en cours et réserve aux erreurs live une attente de 60–120 secondes. Le budget de 120 requêtes par dix minutes, les pauses de 2–4 secondes et l’arrêt après refus sont conservés. La cadence s’adapte au nombre de directs. La fraîcheur effective dépend aussi du relevé LoLTV ; les métriques distinguent date source et date de lecture.

Un autre retard observé vient de la source : le flux de Team Aqua–CITA, carte 2, renvoyait encore à 18:51 UTC un état `COMPLETED` horodaté 18:28:22 UTC, alors que les métadonnées utilisées indiquaient encore une carte commencée. Le collecteur conserve ce dernier relevé, attend le résultat explicite et recherche la carte suivante par les métadonnées, sans redater le flux ni continuer à le télécharger toutes les trente secondes. Sans carte active identifiée, le cache des métadonnées est limité à une minute.

Les IDs LoLTV et alias explicitement observés sont rapprochés du catalogue LoL Esports. Les qualificatifs d’équipes secondaires restent discriminants. Une fusion de rencontres exige les mêmes équipes, la même compétition et une heure proche (six heures au maximum), avec rejet des ambiguïtés. Deux IDs LoLTV distincts ne peuvent pas être associés au même ancien match. L’ordre des équipes du match interne reste stable, avec inversion explicite du score si nécessaire.

Oracle ne remplace un historique qu’avec une série complète et un format indépendamment sourcé. Les dates avec fuseau vérifié permettent la recherche temporelle. Sans fuseau, dix champions/rôles/KDA exacts, équipes, vainqueur et numéro de carte déjà observés constituent une preuve indépendante ; une correspondance multiple est rejetée. Ce mécanisme peut laisser des rencontres non rapprochées : aucun « matching parfait » n’est affirmé sans preuve pour chaque identité.

## Disponibilité réellement vérifiée

Le 24 septembre 2026, les pages paginées `/matches/results/all/2` et
`/matches/all/2` ont répondu HTTP 200 avec un en-tête `Age` d'environ 34 et
35 jours, tandis que les premières pages avaient moins de quinze minutes.
Leurs dates d'août ne prouvaient donc pas que la fenêtre de septembre était
couverte. Le collecteur conserve la preuve HTTP mais refuse une liste dont
`Age` dépasse 24 heures et garde les rencontres déjà acquises. Depuis le
26 septembre, les reprises de pages périmées ou sans détail identifié s'espacent
progressivement : 15 minutes, 30 minutes, une heure, jusqu'à six heures avec les
réglages par défaut. Une lecture validée réinitialise ce délai. Les refus et
`Retry-After` restent prioritaires. Les demandes HTML utilisent
`Cache-Control: max-age=0` pour demander une revalidation normale ; une réponse
toujours périmée reste rejetée, sans URL alternative ni changement d'identité.

## Incident du 26 septembre 2026

Diagnostic en lecture sur le VPS, à partir des exécutions PostgreSQL et des
artefacts HTTP enregistrés. À 00:45:02 Paris, `/matches/results` répondait 200
mais contenait `WALKOVER` pour Solary–Saigon Warriors, avec un score publié
1:0 et un BO1. Le statut non reconnu rejetait toute la liste, bien que ce
passage ait publié 24 autres observations. À 00:45:36, le flux de la carte
`f118b3b749f57f6c5fd42bb2` répondait 200 avec `state=UNSTARTED`,
`timestamp=null`, `teams=[]` et `events=[]`. Le contrôle d'horodatage le
classait en erreur. Les pages paginées périmées et la fiche ZSK–Saigon Warriors
sans objet `matchId/games` expliquaient d'autres incidents ; le worker restait sain.

Le parseur reconnaît `WALKOVER` comme un statut de rencontre distinct
`walkover`, affiché **Forfait** avec son score administratif et un filtre dédié.
Les cartes ne sont pas inventées à partir du score ou du BO. Un complément
Oracle ne remplace pas ce statut, même s'il est plus récent ; aucun règlement
Stake ni vainqueur sportif n'est déduit du forfait. Les snapshots antérieurs
restent historiques. Un autre statut inconnu est écarté individuellement et
signalé ; les autres rencontres valides de la liste restent publiables.

Le flux vide ci-dessus est reconnu uniquement si l'identité de carte, le type
`feed`, l'état `UNSTARTED` et tous les champs vides concordent. Aucun relevé ni
horodatage n'est créé. Les métadonnées live sont alors revalidées à la cadence
du calendrier, au lieu de rester en cache quinze minutes. Un état commencé
sans horodatage ou une identité différente reste une erreur. Une carte
indisponible ne bloque pas l'acquisition des autres cartes.

Un passage avec des observations publiées est **Terminée**, avec
`complete=false` après incident ou interruption. Un passage en erreur sans
publication reste **Échec** ; un passage vide sans erreur reste normal.
Les causes structurées, chemins source sans query string, âge de cache et
identifiants validés sont consultables dans l'historique et les événements du
journal Admin, avec raisons issues d'un catalogue local. Aucun message brut
de fournisseur, cookie ni exception complète n'est transmis au lecteur.
La migration `0021` corrige seulement les passages historiques ayant à la fois
un compteur positif et un snapshot LoLTV enregistré entre leur début et leur
fin. Les anciens diagnostics d'ingestion et d'exécution sont conservés ; les
journaux historiques ne sont pas réécrits. Les passages sans preuve restent
inchangés, y compris ceux ayant seulement relu un état identique.

Ces corrections ne prouvent pas une couverture complète de J−7/J+7 lorsque
LoLTV continue de servir une pagination ancienne ou des statistiques absentes.

Les captures de listes publiques sont déclarées dans
`archive/manifest.json`, avec leur période, date de récupération et empreintes.
Le worker charge toute capture dont la période croise la fenêtre courante ; les
dates J−7/J+7 sont calculées chaque jour à Paris, sans année codée en dur. La
capture actuellement conservée a été récupérée le 21 septembre 2026 à
17:57:21 UTC ; son document (`results-2026-09-21.html.gz`) a pour SHA-256
`48f3a2fedfd2b837bf49a5883efbaef867d3cf7ca7e31e50395f95c62a53c7b5` et contient
30 rencontres des 17–20 septembre, absentes de la base de production au
24 septembre. Les archives servent uniquement à mettre en file des fiches
absentes. Le worker relit chaque fiche, vérifie son identité et exige son score
final actuel avant publication. Une fiche dont le cache précède sa capture est
rejetée ; une réponse refusée arrête la source selon la politique habituelle.
Les archives ne publient ni rencontre ni nouveau relevé à elles seules.

En fonctionnement continu, les journées de novembre suivent le même calcul
glissant et la même collecte que les autres dates. Le paquet contient pour le
moment une seule capture de septembre : un démarrage neuf en novembre ne peut
pas s'appuyer dessus. Si LoLTV sert alors une pagination périmée, il faudra une
capture vérifiée couvrant ces dates ou des données déjà acquises ; le worker
conserve les rencontres valides et n'annonce pas une couverture absente.

Les requêtes HTML ont répondu 200 sur les listes et les fiches. Un cycle HTML a découvert 87 rencontres dans J−7/J+7. Le premier essai Chromium a répondu **403** : arrêt immédiat et délai conservé, puis respecté avant les essais suivants. L’analyse du chargement normal a identifié la consultation anonyme ci-dessus, validée depuis Docker. Le mode par défaut utilise HTTPX ; le mode DOM reste optionnel et désactivé.

Les tests hors réseau valident les parseurs, la découverte de session, la confidentialité des cookies, les gardes de publication et les contrats. La validation réelle est datée et ne garantit pas la disponibilité future de LoLTV. Aucune rotation d’IP, de navigateur ou d’identité, aucun effacement de protection et aucun contournement de challenge ne sont utilisés.
