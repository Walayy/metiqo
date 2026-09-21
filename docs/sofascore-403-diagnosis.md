# SofaScore : origine des 403 et collecte sans appels API directs

Dernière actualisation : [refus de 15:46:40 après huit journées](sofascore-403-2026-09-21-1546.md), navigateur personnel également bloqué, absence d'appels API JSON directs et défaut d'enregistrement reproduit puis corrigé hors réseau.

Actualisation après redémarrage : [analyse du nouveau refus de 13:22:54](sofascore-403-2026-09-21-1322.md), avec chronologie des 34 navigations tentées, distinction des appels du site et du worker, et reproduction locale de la désactivation du cache HTTP.

Audit du 21 septembre 2026. Sources locales : historique Git, fichiers du workspace,
code installé dans le conteneur worker, tables `ingestion_runs`, `match_snapshots`
et `collector_state`. Recherche publique effectuée le même jour. Aucune nouvelle
sonde vers SofaScore ni relance manuelle de collecte pendant cette analyse.

## Ce qui est établi

Le collecteur audité n'était pas exclusivement un scraper de pages. Il utilisait :

1. Patchright/Chromium pour ouvrir les journées et les matchs, lire le DOM et le
   JSON SSR `__NEXT_DATA__` embarqué dans le document HTML.
2. Une session HTTP indépendante `curl_cffi.requests.Session(impersonate="chrome")`
   pour appeler `https://api.sofascore.com/api/v1/` lorsque les cartes rendues
   n'exposaient pas les noms de champions ou les bans.
3. Dans les changements de reprise du 21 septembre, une lecture des réponses JSON
   chargées par le site avant de tenter le complément HTTP.
4. Des téléchargements de logos observés sur `img.sofascore.com`, distincts des
   endpoints JSON de données sportives.

Les endpoints directs étaient `event/{id}/esports-games`,
`esports-game/{id}/lineups` et `esports-game/{id}/bans`. En l'absence de données
réutilisables et de refus, une série de cinq cartes pouvait donc provoquer jusqu'à
**11 requêtes JSON complémentaires**, en plus des requêtes normales de la page.
Ce maximum décrit le code, pas un volume mesuré dans les journaux.

Cette voie est présente dans le commit `8b4a185` daté du 21 septembre à 10:13:27
heure de Paris, absente de `038af53`. Elle était également présente dans le
conteneur en cours d'exécution au début de l'audit : ce n'était pas seulement un
script oublié. Les journaux ne conservent cependant pas un inventaire de chaque
requête HTTP réussie ; on ne peut pas restituer leur nombre, leurs horaires exacts
ou la requête qui aurait déclenché une règle de protection.

## Chronologie locale vérifiée

| Heure de Paris                               | Trace persistée                             | Interprétation permise                                                                               |
| -------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| 20 septembre, 15:48:18                       | `http-403`, durée 0,820 s                   | Premier 403 conservé dans les exécutions SofaScore ; refus d'une navigation HTML.                    |
| 20 septembre, 16:51:17, 17:10:01 et 17:45:00 | `http-403`                                  | Des refus de documents existaient déjà la veille.                                                    |
| 21 septembre, 11:05:01                       | `http-403`, durée 0,758 s                   | Échec très tôt dans la collecte, avant publication de nouvelles données.                             |
| 21 septembre, 11:20:03 et 11:35:04           | `http-403`, durées 0,192 s et 0,150 s       | Refus persistant de navigation.                                                                      |
| 21 septembre, 11:50:05                       | `browser-response`, HTTP 403, durée 0,747 s | Réponse refusée dans le navigateur ; l'ancien journal ne conserve pas l'URL ni le type document/XHR. |

Les entrées `cooldown active` intermédiaires ne prouvent pas une nouvelle requête
à SofaScore. De même, les anciens bilans de treize événements en 0,1–0,2 seconde
provenaient de la republication du cache, déjà corrigée dans l'audit précédent.
Ils ne prouvent pas que l'accès réseau fonctionnait à ces instants.

La date du commit n'est pas la date de déploiement de chaque modification locale.
La chronologie exclut donc l'affirmation simpliste « le commit du 21 a forcément
créé tous les 403 », mais ne démontre pas non plus qu'aucun appel API n'avait été
effectué avant le premier refus archivé.

## Pourquoi le code pouvait contribuer au blocage

Le commit antérieur ajoutait les appels d'enrichissement sans l'espacement entre
navigations. Leur 403/429 était journalisé puis ignoré pour conserver le DOM ; il
ne déclenchait pas le même délai global que le refus d'une navigation. Plusieurs
enrichissements pouvaient donc continuer après un premier refus. La correction
de reprise déjà présente dans le workspace avait ensuite partagé le budget et
le délai entre ces accès.

Autre facteur possible : le navigateur réutilisé restait auparavant sur la
dernière page entre les passages. Le JavaScript du site pouvait continuer ses
propres actualisations pendant cette attente. Le passage à `about:blank` de la
correction précédente supprime ce trafic entre deux exécutions. Le volume ancien
de ces requêtes n'a pas été enregistré. L'espacement des navigations ne compte
pas toutes les sous-requêtes naturelles déclenchées pendant une page active.

L'empreinte TLS d'une session HTTP, son contexte de cookies et une session
Chromium sont des éléments distincts : `impersonate="chrome"` ne partageait pas
automatiquement l'état du navigateur. Une règle peut aussi dépendre du chemin,
de l'IP, du rythme, de la session ou de la détection d'automatisation. La
[documentation Fastly des détections côté client](https://www.fastly.com/documentation/guides/security/bot-management/using-advanced-client-side-detections/)
documente notamment la détection de navigateurs headless. Cela explique un
mécanisme possible, sans prouver quel produit ni quelle règle SofaScore a appliqué.

L'ancien compte rendu local signalait IPv4 refusé et IPv6 accepté le 20 septembre.
C'est un indice de différence de chemin/adresse ; sans capture réseau détaillée
ni journaux du fournisseur, ce n'est pas une preuve de bannissement d'IP ni une
solution durable. Un statut 403 ne permet pas à lui seul de nommer Cloudflare,
Fastly ou Akamai, de connaître un seuil, ni d'annoncer une durée de blocage.

**Conclusion causale :** les appels directs et l'ancien trafic insuffisamment
borné sont des facteurs aggravants plausibles. Le refus touche aussi les pages
HTML. Les preuves disponibles ne permettent pas d'identifier le déclencheur
initial exact ni de garantir que supprimer l'API lèvera un blocage déjà installé.

## Témoignages : distinguer réellement les méthodes

| Source primaire consultée                                                                                                                                  | Méthode décrite et constat                                                                                                   | Portée                                                                                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Reddit — How to get around + avoid IP ban](https://www.reddit.com/r/webscraping/comments/15j5onk/how_to_get_around_avoid_ip_ban/)                         | L'auteur décrit Selenium sur `/favorites`, lecture avec `find_elements()` et blocage découvert le lendemain.                 | Exemple de lecture DOM sans appel API direct déclaré. Pas de code complet ni de capture réseau : les appels naturels du site ne sont pas exclus. |
| [Stack Overflow — Live Games, 27 mars 2024](https://stackoverflow.com/questions/78234545/is-it-possible-to-scrape-data-from-sofascore-on-live-games)       | Le code publié utilise `requests.get()` sur une URL HTML de match, puis BeautifulSoup ; un intervenant reproduit un 403.     | Exemple concret de requête de page HTML refusée sans endpoint JSON dans le code présenté. Ce n'est pas une preuve concernant Chromium.           |
| [GitHub — Pediludium, diagnostic du 12 juin 2026](https://github.com/DeoOptimoMaximo/Pediludium/blob/main/docs/15-sofascore-challenge-and-piggyback.md)    | Le mainteneur rapporte des 403 sur les documents HTML de matchs/tournois, puis sur une page d'entrée après plusieurs sondes. | Confirme un refus possible au niveau HTML, mais leur enquête inclut aussi des sondes API : ce n'est pas un protocole exclusivement DOM.          |
| [Reddit — Blocked from Sofascore, 26 novembre 2024](https://www.reddit.com/r/webscraping/comments/1h077w7/blocked_from_sofascore_error_403_forbidden_for/) | L'auteur rapporte une boucle accidentelle d'appels API, puis un accès également refusé au site dans son navigateur.          | Compatible avec l'hypothèse de l'utilisateur, mais témoignage non instrumenté ; aucune preuve d'un lien causal identique ici.                    |
| [Reddit — Selenium locally/server, 13 juin 2025](https://www.reddit.com/r/webscraping/comments/1labsk6/selenium_works_locally_but_403_on_server/)          | L'auteur précise qu'il récupère l'API via Selenium et reçoit un JSON `reason: challenge` sur serveur.                        | À exclure des exemples « DOM seul », malgré Selenium dans le titre.                                                                              |

Ces témoignages établissent que le scraping de pages n'immunise pas contre les
refus. Ils ne fournissent ni seuil sûr, ni délai universel, ni preuve que les
protections citées par les commentateurs sont celles effectivement déployées.

## Changement demandé et appliqué

- Suppression du client direct, des appels de liste/cartes/lineups/bans, de leur
  cache et de la lecture des corps JSON interceptés. Retrait de `curl-cffi` et de
  ses dépendances désormais inutiles dans le lockfile.
- Lecture conservée du DOM et de `__NEXT_DATA__` déjà présent dans le HTML.
  Les requêtes lancées par le site pour son affichage restent autorisées ;
  l'observateur réseau ne lit que les métadonnées de refus.
- Conservation des portraits observés et des archives. Le parseur laisse les
  noms sans libellé et les bans non collectés inconnus. Oracle peut toujours
  compléter un historique rapproché avec les garanties préexistantes.
- Une carte déjà acquise ne provoque plus une revisite toutes les cinq minutes
  seulement pour tenter un enrichissement désormais interdit. La revisite
  historique de six heures et la cadence live restent conservées.
- Les prochains refus conservent aussi `lastBlockUrl` sans paramètres/fragment
  et `lastBlockResourceType` dans `collector_state`. Cela permettra de distinguer
  une page HTML, une requête du site et un téléchargement de logo. Aucun cookie,
  jeton ou corps de réponse n'est ajouté aux journaux.
- Les délais persistants et `Retry-After` restent respectés. Aucun effacement de
  l'état de blocage, changement de cron, proxy ou nouvelle sonde de déblocage.

## Vérifications

- `npm run check` réussi : TypeScript, ESLint, 58 tests frontend, build, Ruff,
  mypy et 94 tests backend hors intégration.
- Suite PostgreSQL 18 isolée : 138 tests réussis au premier passage ; le dernier
  test échouait parce que le mot de passe du rôle API de la base de test ne
  correspondait pas à celui attendu par la suite. Après correction de ce seul
  environnement temporaire, ce test a été rejoué avec succès. Les 139 tests ont
  donc été validés, dont 45 intégrations ; aucune base métier n'a été réinitialisée.
- Régressions : données DOM partielles conservées, corps JSON du site jamais lu,
  XHR naturel autorisé puis nouvelles ressources coupées après refus, absence de
  revisite accélérée pour un portrait sans nom, URL de refus sans paramètres ni
  fragment persistée en base. Les tests de limites et reprise utilisent des
  réponses contrôlées.
- Image worker reconstruite et conteneur local remplacé. Vérification dans le
  conteneur actif : client direct absent, `curl_cffi` absent, aucune lecture
  `response.json()` dans le collecteur. L'échéance existante du blocage,
  **21 septembre à 12:20:06 heure de Paris**, et les deux refus consécutifs ont
  été conservés à l'identique lors du remplacement. Aucun cron modifié ni
  lancement manuel du collecteur pour tester le déblocage.
- Le conteneur PostgreSQL temporaire et son volume ont été supprimés. Restent les
  avertissements préexistants Starlette et la taille du bundle MSW. Aucun parcours
  d'interface n'a été modifié par cette demande ; aucune nouvelle validation de
  collecte complète sur le site bloqué n'est annoncée.

Aucune disponibilité future de SofaScore n'est déduite des tests hors ligne.

## Observation suivante et extension DOM — 21 septembre 2026

Après retrait des appels JSON directs, le worker a de nouveau reçu un 403 **sur le document HTML** `https://www.sofascore.com/fr/esports/lol/2026-09-21`, à 10:20:10 UTC. L’URL et le type `document` sont cette fois conservés dans `collector_state`. Le navigateur manuel a pu afficher une fiche de rencontre. Ces observations n’établissent pas le mécanisme interne du refus ni son déclencheur initial ; elles montrent que le retrait du client API ne garantit pas une reprise immédiate du worker.

La demande suivante supprime les plafonds par passage et ajoute la lecture des dix picks et des bans après chargement du DOM. La comparaison locale des portraits Riot remplace les libellés absents lorsqu’elle est fiable, avec accord explicite de l’utilisateur. Les images chargées naturellement sont exploitées en tant qu’images ; aucun corps JSON API n’est lu. Voir les [vérifications et limites](verification.md#scraping-des-picks-et-bans-sans-plafond-de-matchs--21-septembre-2026).
