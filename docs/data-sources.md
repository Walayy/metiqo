# Référentiel LoL et logos

## Nouveau refus SofaScore après le « go » — 21 septembre 2026

Le [diagnostic du 403 de 15:46:40](sofascore-403-2026-09-21-1546.md) s'appuie sur le code installé, les journaux et le checkpoint PostgreSQL : huit journées lues, aucune fiche de match ouverte dans ce cycle, aucun appel API JSON direct ajouté par le worker. Le navigateur personnel est également refusé d'après l'utilisateur. Une restriction liée à la connexion/IP est plausible, sans preuve de la règle serveur ni décompte exhaustif des requêtes naturelles du site. Les retours publics Reddit/GitHub et leurs limites sont cités dans le rapport. Le worker a été arrêté pour l'analyse ; le défaut de persistance du refus est corrigé et vérifié avec Chromium sans réseau, sans nouvelle collecte ni déploiement de cette correction.

## Session SofaScore persistante et cache renforcé — 21 septembre 2026

Les durées ont ensuite été réduites à la demande de l'utilisateur : journées courante/futures/passées après 3 minutes/15 minutes/1 heure ; fiches live/proches/programmées après 2 minutes/3 minutes/15 minutes ; résultats avec/sans cartes après 1 heure/5 minutes. Ce sont des délais de cache avant éligibilité au prochain passage, sans changement du cron ni du délai de refus. Les pauses après lecture et le profil persistant sont conservés. Le worker reste arrêté jusqu'au « go » explicite.

La correction suivante remplace les anciennes cadences décrites dans les audits ci-dessous. Un seul profil Chromium est conservé sur disque, avec cookies et cache HTTP actifs ; aucun routage global ne désactive le cache. Le worker n'ajoute aucun appel API JSON et continue à lire uniquement le DOM, le JSON SSR du HTML et les images rendues. Les pages connues sont relues selon les échéances du [guide des collecteurs](collectors.md#session-persistante-et-cache-renforcé--21-septembre-2026), avec pause après lecture et déduplication par identifiant de rencontre. Les cartes terminées d'une série live ne sont plus récupérées à chaque actualisation ; leur ancienne provenance reste conservée en base. Un cache réutilisé ne devient pas un nouveau relevé.

Sources de vérification : code local, tests avec données synthétiques, PostgreSQL temporaire et Chromium isolé avec `--network none` et serveur HTTP sur loopback. Le test vérifie la persistance du cookie et du cache après fermeture/réouverture du navigateur, ainsi que la fermeture de page et l'arrêt du cycle au premier refus simulé. Une requête naturelle déjà partie avant le traitement de l'événement réseau ne peut pas être annulée rétroactivement. Aucune collecte SofaScore réelle ni relance du worker de l'application : elles attendent le « go » explicite de l'utilisateur. Ces tests ne prouvent pas la levée du blocage côté source.

## Diagnostic des 403 et passage au scraping seul — 21 septembre 2026

Le [refus de 13:22:54 après redémarrage](sofascore-403-2026-09-21-1322.md) touche une page HTML après 15 journées et 18 fiches parcourues. Le code installé ne contient plus le client JSON direct. La chronologie provient du checkpoint PostgreSQL, pas d'une capture exhaustive du réseau. Un test sur serveur local dans le conteneur confirme que le routage actuel désactive le cache HTTP ; la documentation Playwright et les limites de cette preuve sont conservées dans le rapport. Aucun accès de diagnostic supplémentaire à SofaScore n'a été effectué.

Analyse du code versionné, du code effectivement installé dans le conteneur worker et des tables locales `ingestion_runs` / `collector_state`, sans nouvelle sonde SofaScore. Le premier 403 conservé date du 20 septembre à 13:48:18 UTC ; les anciens refus `http-403` proviennent de navigations HTML. Les appels directs existaient aussi pour l’enrichissement, mais aucune trace exhaustive par requête ne permet d’attribuer l’origine du blocage à ce seul canal. Les témoignages Reddit, GitHub et Stack Overflow sont distingués selon leur méthode réelle dans le [rapport avec sources et limites](sofascore-403-diagnosis.md). Ils ne constituent pas des garanties de couverture ni un diagnostic de l’infrastructure SofaScore.

## Audit de reprise SofaScore — 21 septembre 2026

Sources consultées : journaux `ingestion_runs` locaux, dernières données brutes SofaScore conservées dans `match_snapshots` (catégorie LoL et `tournament.uniqueTournament`), identités et logos du catalogue local ; page [Oracle’s Elixir — Downloads](https://oracleselixir.com/tools/downloads) et bundle public `main.d7f4bb57.js`. Aucun nouveau téléchargement massif SofaScore pendant le refus. La page Oracle annonce une publication quotidienne ; elle ne confirme pas le fuseau des dates CSV observées. Les dates sans fuseau vérifié restent donc exclues du rapprochement automatique.

Avant réparation : 59 ligues enregistrées, 52 logos locaux et sept images absentes, dont une ancienne identité Dota 2 exclue du calendrier LoL. Cette mesure n’est pas une exhaustivité mondiale. Les slugs officiels et le parent de tournoi observé servent à retrouver un logo existant ; aucune URL de logo n’est fabriquée. Une icône Lucide générique indique l’absence sans emprunter l’identité d’une autre ligue. Détails : [audit et limites](sofascore-resilience-audit.md).

Après retraitement local sans téléchargement : 56 logos sur les 58 compétitions LoL exposées. Les quatre corrections concernent LIT Playoffs, Playoffs/WSCI, LFL Promotion et LCK Challengers League Playoffs. La version `a173a66b-71f0-442e-a8e4-288a19e92c50` conserve les preuves d’origine et décrit ce retraitement. Prime League 1st Division Playoffs et LPLOL Playoffs restent sans correspondance de logo vérifiée.

## Vérification du 21 septembre 2026

Audit documenté dans [review-v1-ajout-live.md](review-v1-ajout-live.md). Collectes effectuées dans une base PostgreSQL isolée : LoL Esports, 37 pages / 36 ligues / 265 équipes / 299 URLs de logos ; Oracle, archive de 23 196 970 octets et 117 912 lignes validées pour 2014 + 2026 ; Data Dragon 16.18.1, 173 portraits récupérés dans un dossier temporaire. Ces chiffres décrivent cet essai, sans garantir l’exhaustivité.

L’essai SofaScore de cette date a répondu `403`, y compris sur le réseau Docker dual-stack : la disponibilité constatée le 20 septembre n’est pas une garantie. Les données déjà stockées ont permis de vérifier le contrat API sur 74 rencontres LoL, après exclusion d’une recommandation Dota 2. Les preuves originales restent conservées. Une entrée de ban répétée dans la source est dédupliquée ; elle ne doit pas invalider le flux entier.

Les côtés bleu/rouge ne sont pas déduits de l’ordre home/away. Un avantage d’éliminations ne prouve pas une victoire : la [règle de Riot](https://www.leagueoflegends.com/en-us/how-to-play/) repose sur la destruction du Nexus. La convention de fuseau des dates Oracle sans offset n’a pas été vérifiée lors de cet audit : leur import brut continue, leur rapprochement temporel exige une configuration explicite vérifiée.

## Identité Metiquo fournie le 16 septembre 2026

Le pack de marque a été fourni directement par le propriétaire du projet, séparément des identités esport. La source native 1254 × 1254 et le manifeste SHA-256 des exports utilisés sont conservés sous `assets/brand/`. Les variantes claire/sombre gardent le symbole, son dégradé turquoise et son halo d’origine. L’interface utilise WebP sans perte avec repli PNG ; favicon ICO et icône Apple PNG viennent aussi du pack. Aucun redessin, agrandissement de la source ni service externe n’intervient. Voir [le guide de l’identité](../assets/brand/README.md).

## Référentiel esport

Collecte : **14 septembre 2026**. Source primaire : [LoL Esports, Riot Games](https://lolesports.com/en-US).

## Collecte et provenance

Les compteurs de l’interface sont libellés « équipes rattachées » : ils décrivent la ligue d’origine enregistrée dans le référentiel. Pour les compétitions internationales, l’interface indique « Participants non renseignés » ; elle ne déduit pas leurs participants des affiliations domestiques. Les traductions françaises des régions sont des libellés de présentation ; les identifiants et valeurs source sont conservés.

- Le menu public « All Leagues » expose les liens filtrés vers 35 compétitions de League of Legends. TFT est exclu du produit.
- Le script historique `scripts/sync-catalog.mjs` lisait la page d’accueil et les 32 liens de filtres régionaux/internationaux. Il extrayait le JSON transporté dans le HTML, sans exécuter les scripts du site. Il a été remplacé le 15 septembre 2026 par le collecteur backend décrit ci-dessous ; le snapshot frontend reste inchangé.
- Les objets `Team` avec `homeLeague` sont prioritaires. Les équipes supplémentaires proviennent des `EventMatch` et de leurs `MatchTeam` identifiés.
- Une rencontre domestique est prioritaire sur un événement international pour attribuer la ligue d’origine d’une équipe. Cette inférence ne certifie pas un statut actif ni la totalité du roster 2026.
- La liste des sources est reproduite dans le script. Le résultat brut transitoire est dans `.cache/`, ignoré par Git. Le snapshot utilisable est versionné dans `apps/web/src/mocks/data/catalog.json`.
- Chaque entité conserve `sourceImage`, l’URL d’origine exacte du CDN officiel `static.lolesports.com`. Les logos ne sont ni inventés, ni recolorés. Les logos de ligues sont affichés en monochrome par filtre CSS pour la navigation, et conservent leur asset original sourcé.
- Sharp a converti les images du snapshot frontend en WebP, limitées à 144 × 144 px, avec transparence préservée et sans agrandissement. La nouvelle collecte backend utilise Pillow ; les assets historiques du frontend ne sont pas réécrits.

## Sources de vérification contextuelle

- [Retour des LCS et du CBLOL en 2026](https://lolesports.com/en-US/news/lcs-and-cblol-return).
- [Manuel officiel de la saison 2026](https://lolesports.com/en-SG/season/115547545029543948/handbook).
- [Présentation de la saison LCP 2026](https://lolesports.com/en-PH/news/lcp-2026-season-primer).
- [Ligues et rencontres LFL publiées par Riot](https://lolesports.com/en-US/leagues/first_stand,lfl,msi,worlds).

## Limites explicites

35 compétitions et 262 équipes sont référencées. Le catalogue reflète les sources consultées : il n’est pas présenté comme l’inventaire universel des ligues amateurs, locales, universitaires ou fermées. Les données ne sont pas automatiquement actualisées à l’exécution. Les sponsors et logos peuvent évoluer après cette date. Les pages de matchs peuvent inclure des équipes historiques ou invitées.

L’application permet des identifiants de ligues et d’équipes arbitraires. Le backend devra fournir un référentiel versionné avec dates de validité, provenance par enregistrement et affiliations par saison. Il devra distinguer couverture des identités et disponibilité effective des marchés.

Les 34 matchs/marchés de démonstration, dates, formats, cotes, probabilités et courbes sont **créés pour le prototype**. Aucun calendrier ni pricing réel n’est affirmé. Les noms de bookmakers sont illustratifs, sans lien de transaction ni affiliation.

Depuis la décision produit du 15 septembre 2026, le scénario utilise exclusivement Stake et des relevés UTC sur plusieurs jours, comprenant des hausses et des baisses. Il ne s’agit pas d’un flux Stake : aucune cote réelle n’a été récupérée. Les badges de démonstration ont été retirés du produit pour conserver la même interface en modes mock et API ; cette limitation reste documentée ici et dans le README.

## Logos des jeux

Récupérés le **15 septembre 2026**, conservés sans modification dans `apps/web/public/games/`. Les formats d’affichage ont des dimensions réservées et un repli textuel accessible.

| Jeu               | Page primaire                                       | Asset exact                                                                                                                                                           | Fichier local  |
| ----------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| League of Legends | [Site Riot](https://www.leagueoflegends.com/en-us/) | [Favicon SVG déclaré dans le HTML](https://cmsassets.rgpub.io/sanity/images/dsfx7636/news_live/d3b7bd9decb1e1672dcb80be4f8bc1aa05490dc1-110x70.svg?accountingTag=LoL) | `lol.svg`      |
| Counter-Strike 2  | [Site Valve](https://www.counter-strike.net/cs2)    | [Logo compact déclaré dans la feuille CSS officielle](https://cdn.akamai.steamstatic.com/apps/csgo/images/csgo_react/global/logo_cs_sm.svg)                           | `cs2.svg`      |
| Dota 2            | [Site Valve](https://www.dota2.com/home)            | [Symbole déclaré dans la feuille CSS officielle](https://cdn.steamstatic.com/apps/dota2/images/dota_react/global/dota2_logo_symbol.svg)                               | `dota2.svg`    |
| VALORANT          | [Site Riot Games](https://playvalorant.com/en-us/)  | [Pack officiel VALORANT](https://playvalorant.com/en-us/news/game-updates/valorant-asset-kit/)                                                                        | `valorant.png` |

Ces entrées identifient des jeux dans le sélecteur. Elles ne constituent pas un catalogue de marchés ni une vérification de leur couverture de paris. CS2 et Dota 2 sont désactivés et annoncés « À venir ». Les marques et assets Valve restent la propriété de Valve.

Les icônes de postes LoL affichées dans les compositions reprennent les assets de position issus du client LoL, conservés localement sous `apps/web/public/roles/` (`top`, `jungle`, `middle`, `bottom`, `utility`). Ils servent uniquement à identifier le rôle affiché par le contrat ; CommunityDragon n’est pas une source de données de rencontre et Riot Games n’endosse pas le projet.

## Référentiel backend LoL — 15 septembre 2026

La commande permanente `metiquo-worker sync-lol-catalog` découvre le registre `Query.leagues` dans le HTML public [LoL Esports](https://lolesports.com/en-US), puis consulte le filtre public de chaque slug découvert. Aucun inventaire de ligues fermé ne pilote la collecte. Les régions conservent leurs valeurs source ; les divisions, saisons, splits et tournois sont conservés lorsqu’ils sont exposés.

La collecte réelle terminée le **15 septembre 2026 à 20:31:09 UTC** a publié **35 ligues, 262 équipes et 295 URLs d’images**, après lecture de **36 pages**. Deux identités peuvent partager une URL ou les mêmes octets : le nombre d’images n’est pas le nombre d’entités. Ce bilan décrit les pages consultées, sans garantir tous les circuits, équipes ou rosters existants.

Les entités conservent les URLs de preuve, et les exécutions référencent les pages HTML compressées avec SHA-256 et date de récupération. Les affiliations distinguent une ligue d’origine déclarée (`homeLeague`) d’une participation à un tournoi ou à une rencontre. Une saison n’est reliée que si la source donne cette relation ; notamment, la présence d’une date en 2026 ne suffit pas à attribuer une saison 2026. Les périodes sourcées de participation restent accessibles même en l’absence de cette relation.

Pillow convertit les originaux PNG/JPEG/WebP/GIF de `static.lolesports.com`, ainsi que les images officielles déjà observées sur `img.sofascore.com`, en WebP local, au maximum 144 × 144 px. Les octets d’origine, les empreintes et les versions sont conservés. Le logo LOUD déclaré par Riot mesure 8334 × 8334 px : la limite de décodage tient compte de cet original et les conversions sont sérialisées pour borner la mémoire. Un téléchargement défaillant réutilise le cache local vérifié ; à défaut, l’identité demeure dans le catalogue sans logo plutôt que d’annuler toutes les autres mises à jour. Les URLs de logos du backend contiennent leur empreinte et sont servies par l’API ; aucune reconstruction du frontend n’est nécessaire pour les publier.

Les identités explicitement découvertes dans les rencontres SofaScore enrichissent le même référentiel : identifiant fournisseur, alias observés et URL d’image sont conservés sans écraser le nom Riot. Les qualificatifs d’équipes secondaires sont protégés afin que, par exemple, une variante de **MKOI Fénix** ne soit pas fusionnée avec **Movistar KOI**. Une collecte Riot ultérieure retient ces équipes et compétitions connues si elles sont momentanément absentes de ses pages. Cette stratégie couvre les entités effectivement exposées par les sources consultées ; elle ne garantit pas toutes les équipes LoL existantes.

Le contrat historique du catalogue impose un rattachement unique. Le backend expose donc aussi `leagueAssignment` et les relations détaillées pour distinguer son regroupement par participation d’une ligue d’origine réellement sourcée. Le frontend reste sur son snapshot du 14 septembre, sans modification de l’UI/UX. Voir [le guide des collecteurs](collectors.md) pour la publication atomique, les contrôles et les limites.

## Oracle’s Elixir — collecte backend

Depuis la mise en place des deux commandes explicites, la collecte s’appelle `sync-oracles-elixir` ; `collect` reste compatible. `--latest` découvre la dernière année et permet une planification qui ne fige pas l’année en cours. L’import conserve la même source et la même validation, sans deuxième collecteur.

Nouvelle collecte complète réussie le **15 septembre 2026 à 20:25:14 UTC** : treize années récupérées, douze empreintes inchangées et une nouvelle version du fichier 2026, contenant **104 712 lignes**. Le contenu source peut évoluer entre deux exécutions ; ces nombres sont un constat daté. La sélection Drive attend maintenant l’état sélectionné de chaque ligne avant de demander l’archive.

Consultée le **15 septembre 2026** : [page officielle des téléchargements](https://oracleselixir.com/tools/downloads), qui référence le dossier [OE Public Match Data](https://drive.google.com/drive/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH). Les **13 CSV annuels visibles, de 2014 à 2026, ont été récupérés intégralement par export ZIP groupé anonyme**, malgré les réponses de quota sur les liens individuels. Validation terminée à 16:49 UTC : 848 628 282 octets et 1 223 472 lignes, avec contrôles du checksum des archives, des CRC et de la structure CSV. Les fichiers 2014 et 2026 ont été obtenus identiques dans deux exports distincts.

Cette récupération ne certifie pas l’exhaustivité des compétitions ni l’exactitude des statistiques. Le CSV 2026 contient 1 512 lignes déclarées `partial` et des saisons `year=2027` avec des dates en 2026 ; l’année de fichier et le champ de saison restent distincts dans le stockage. Le backend conserve maintenant les CSV par SHA-256 et toutes leurs colonnes en JSONB, avec un identifiant de version et une date de récupération. Le frontend reste inchangé en mode mock et ne consomme pas ces statistiques.

L’[audit détaillé](oracles-elixir-audit.md) conserve les identifiants, résultats datés, références Google et limites des méthodes évaluées. Ses scripts et téléchargements temporaires ont été supprimés. La demande suivante a autorisé l’implémentation du worker permanent, décrite dans le [guide backend](backend.md). Les dernières vérifications et versions actives sont exposées par `/api/v1/sources/oracles-elixir/datasets` ; un échec conserve les dernières données valides et son état est visible. La disponibilité future de Google et l’actualité des données ne sont pas garanties.

## Données de compte et emails — 15 septembre 2026

Les emails de compte sont saisis par l’utilisateur et vérifiés par un code SMTP ; ils ne proviennent pas des fixtures esport. `admin@metiquo.fr` est l’adresse administrateur explicitement demandée, provisionnée en migration et soumise à la même vérification email. Les codes et sessions sont générés aléatoirement par l’API, avec seulement des empreintes en base.

Mailpit v1.31.1 ([images officielles](https://mailpit.axllent.org/docs/install/docker/), [SMTP](https://mailpit.axllent.org/docs/configuration/smtp/)) capture les messages localement, sans livraison externe. Documentation consultée le 15 septembre 2026. La possession d’un code dans cet environnement vérifie le parcours local, pas la propriété d’une boîte mail externe. La sécurité de session s’appuie sur les recommandations [OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) ; détail dans [authentication.md](authentication.md).

## Administration et raccourcis de ligues — 16 septembre 2026

Les logos des raccourcis LCK, LPL, LEC, LFL et CBLOL utilisent les fichiers locaux du catalogue déjà sourcé ; aucune nouvelle identité, URL ou couverture n’est prétendue. Les comptes, planifications, heartbeat et historiques Admin proviennent exclusivement de PostgreSQL et du worker réel. L’historique Admin commence avec cette fonctionnalité ; les anciennes collectes restent dans les endpoints source.

Le calcul des échéances utilise [croniter](https://github.com/pallets-eco/croniter) et les fuseaux IANA via `zoneinfo`/`tzdata`, documentation consultée le 16 septembre 2026. Ce sont des horaires de collecte configurés par l’administrateur, pas un calendrier de compétitions.

## Marques et droits

Les marques, noms et logos appartiennent à Riot Games, aux organisateurs et aux équipes concernés. Leur présence dans un site public n’équivaut pas à une licence commerciale générale. Le prototype local les utilise comme identifiants descriptifs et documente leur provenance ; les droits et conditions devront être vérifiés avant une exploitation publique du produit.

## Calendrier et performance — 16 septembre 2026

Le scénario frontend de 34 marchés se répartit désormais de J−7 à J+7 autour du jour courant de Paris, calculé au chargement du module MSW. Les affiches, horaires, probabilités et relevés restent fictifs ; le catalogue Riot sourcé du 14 septembre et ses logos ne changent pas. Le mock ajoute séparément les identités et le calendrier WSCI sourcés sur SofaScore, sans leur créer de marchés ni de value fictive. Les identifiants des opportunités comportent la date pour distinguer les rencontres de journées différentes. Les relevés des rencontres passées précèdent leur horaire de début.

La nouvelle demande du 16 septembre sépare `/matches` des opportunités. Le mock décline les identités sourcées en rencontres fictives, avec cartes, scores, objectifs, compositions et alias de joueurs entièrement fictifs (`apps/web/src/mocks/esport.ts`). Les journées J−3 et J+3 sont volontairement vides pour vérifier les dates désactivées. Le score de série dérive des cartes gagnées. Il ne s’agit pas d’un calendrier officiel ni d’un flux live ; les statistiques restent celles du scénario horodaté, même lors d’une nouvelle lecture. L’API expose seulement les rencontres stockées, sans inventer de direct ni de compositions.

Performance utilise 120 décisions et règlements fictifs répartis sur environ 60 jours, avec gains, pertes et annulations. Chaque décision fige sa cote et sa probabilité avant le match. Cet historique est indépendant des opportunités courantes et permet uniquement de tester une simulation : il ne constitue ni un historique utilisateur réel ni une validation du modèle. Le mode API reste vide tant qu’une source ne fournit pas les règlements et décisions nécessaires.

## Rencontres LoL rendues — SofaScore — 20 septembre 2026

Le worker observe les pages publiques rendues de la fenêtre J−7 à J+7 ([exemple de journée](https://www.sofascore.com/fr/esports/lol/2026-09-21)), puis ouvre les fiches de rencontre découvertes. La date de récupération est l’horodatage `observedAt` du relevé conservé. Le tournoi [World Star Challengers Invitational 2026](https://www.sofascore.com/esports/tournament/lol/world-star-challengers-invitational/37525) a été vérifié le 20 septembre : ses rencontres, dont KT Rolster Challengers – Bilibili Gaming Junior, sont exposées sous cette compétition et non sous LCK CL.

La collecte utilise Patchright et le DOM/HTML rendu, ainsi que le JSON SSR `__NEXT_DATA__` public présent dans la page. Le réseau `ingestion` est dual-stack afin que Chromium puisse utiliser la connectivité IPv6 de l’hôte ; le chemin IPv4 a retourné `403` lors de la validation du 20 septembre 2026, contre `200` pour le même navigateur par IPv6. À la demande suivante du 21 septembre, les appels API directs de lineups/bans et la lecture des réponses JSON interceptées sont supprimés ; `curl-cffi` est retiré du worker et du lockfile. Le site conserve ses propres requêtes de chargement, mais seules les données du DOM et du JSON SSR embarqué sont exploitées. Aucun accès à Stake n’est réalisé par le worker. Les liens sont dédupliqués par identifiant de rencontre ; les pages de journée sont mises en cache cinq minutes, les matchs terminés ayant déjà des cartes sont revisités après six heures, sans accélération pour des libellés absents, et les matchs live connus restent prioritaires avec un intervalle minimal d’une minute. Chaque navigation est séparée par un délai aléatoire borné ; un `403` ou `429` déclenche un arrêt temporaire du collecteur au lieu d’une nouvelle tentative en boucle. Le script `sync-sofascore-matches` est prévu toutes les minutes afin de suivre les directs sans ouvrir toutes les fiches en rafale, tandis que les échéances sont modifiables dans Admin.

La provenance est conservée dans `match_source_links` et chaque état immuable dans `match_snapshots`. Le matching réutilise d’abord un lien SofaScore connu, puis combine équipes normalisées (accents, ponctuation, alias/code/slug), sens de l’affiche, proximité de l’horaire et ligue. `last_seen_at` avance à chaque observation, y compris lorsque le snapshot est dédupliqué car son payload n’a pas changé ; c’est ce timestamp qui alimente l’heure « Relevé à » de l’interface. Un score insuffisant ou une collision interdit la fusion avec un autre fournisseur, mais ne supprime pas un événement possédant son propre identifiant SofaScore stable. Les suffixes de phase ne servent qu'à reprendre l'identité visuelle d'une ligue de base au nom exact ; une participation observée ne crée pas d’affiliation historique supposée.

Le worker parcourt les onglets rendus `Carte`/`Game` en français ou en anglais. Une carte terminée est publiée pendant que la série continue dès que SofaScore expose ses deux camps et cinq joueurs : niveaux, K/D/A, CS, or, tours, dragons, barons et inhibiteurs sont conservés, de même que les images officielles de champions. Le parseur attend le panneau de carte sélectionné et conserve les portraits rendus des picks et des bans, par équipe. Les noms absents du DOM sont rapprochés des portraits Riot locaux uniquement si les images sont quasi identiques et sans ambiguïté. Les autres noms restent inconnus, sans supprimer les portraits ni les bans. Les bans auparavant complétés via API ne sont plus récupérés par cette voie. Les observations historiques restent immuables et peuvent encore contenir ces anciens compléments sourcés. La durée, le Héraut ou les larves restent inconnus lorsqu’ils ne sont pas publiés, et l’interface indique « Bans non publiés » pour une équipe lorsqu’aucun de ses bans n’est disponible. Pour les matchs terminés, Oracle’s Elixir reste la source historique complémentaire. La lecture API prend le statut et le score du dernier relevé SofaScore, et conserve séparément chaque carte compatible déjà publiée, sans déduire le score total d’un sous-ensemble de cartes. Aucun champ n’est complété par un zéro ou une statistique fictive. Les sources ne constituent ni un calendrier officiel exhaustif, ni une prédiction, ni une preuve de résultat lorsque la page ne l’expose pas.

### Portraits des champions — 19 septembre 2026

Affichage revu le 21 septembre : les bans publiés deviennent des portraits circulaires regroupés selon les identifiants des deux équipes, dans l’ordre gauche/droite de la série. Un nom inconnu reste « Champion non identifié » dans le détail accessible ; une équipe sans bans publiés affiche « Bans non publiés ». Les statistiques comparées réutilisent les mêmes relevés et calculs existants, sans compléter les champs absents. La validation visuelle utilise uniquement les données déjà enregistrées en local ; elle ne déclenche aucune collecte SofaScore.

Le catalogue complet des **173 portraits officiels** est récupéré depuis Riot Data Dragon **16.18.1**, version retournée par `https://ddragon.leagueoflegends.com/api/versions.json` lors de la dernière synchronisation. Les noms et fichiers proviennent de `https://ddragon.leagueoflegends.com/cdn/16.18.1/data/fr_FR/champion.json`. [Documentation primaire Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon). La commande `npm run data:champions:sync` vérifie la version courante, télécharge les portraits manquants ou modifiés, puis publie atomiquement le manifeste. Les URLs exactes, noms, version et date sont conservés dans `apps/web/src/domain/data/champions.json` ; fichiers originaux dans `apps/web/public/champions/`. Le front réutilise ce manifeste pour les noms Oracle’s Elixir et les données SofaScore, avec repli accessible si une identité n’est pas résolue. Ces images identifient les champions d’une composition sourcée, sans assertion sur leurs choix par des joueurs réels. Les assets League of Legends restent la propriété de Riot Games.

### Identification locale des portraits — 21 septembre 2026

Page vérifiée : [Team Liquid – FlyQuest, carte 1](https://www.sofascore.com/esports/match/flyquest-team-liquid/cDVcswFVc#id:17091782,tab:games). Le DOM rend dix portraits de joueurs et deux groupes de cinq bans, avec des libellés génériques ou vides. Aucun nom de champion n’était présent dans les éléments rendus inspectés. Sur dix images déjà chargées, exportées pour une vérification hors ligne, neuf correspondent quasi exactement au catalogue Riot 16.18.1 et une reste sans correspondance fiable. Ce résultat porte sur cet échantillon, sans extrapolation à toutes les rencontres. Les fixtures et leurs URLs/empreintes sont dans `tests/backend/fixtures/sofascore-portraits/`. Les correspondances historiques image/nom contradictoires de la base ne sont pas utilisées comme référentiel.

La comparaison utilise des pixels RGB réduits à 32 × 32 : écart moyen absolu maximal de 3/255 et séparation minimale de 12/255 avec le second candidat. Le référentiel embarqué contient 173 portraits, leurs noms, source, version, date et empreinte originale. Il est construit uniquement depuis les assets Riot déjà présents. Les octets `image/*` reçus par le navigateur depuis `img.sofascore.com` sont conservés avec leur empreinte ; les corps JSON des endpoints API ne sont jamais exploités. Les images conservent leurs ayants droit respectifs. Aucun appel à Riot n’est déclenché pendant un passage SofaScore.
