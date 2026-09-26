# Sources et provenance

## Correction LoLTV du 26 septembre 2026

L'incident VPS a été vérifié dans les exécutions du 26 septembre à 00:45 Paris
et leurs documents HTTP archivés. `WALKOVER` provient de la liste publique de
résultats (Solary–Saigon Warriors, score administratif 1:0) ; il reste un forfait
distinct d'une rencontre jouée. Les flux `UNSTARTED` identifiés mais sans
horodatage, équipes ni événements ne sont pas des observations live. Les
rejets de pagination périmée, identités absentes et contradictions restent
visibles, sans inventer de couverture ou de résultats. Les [preuves, règles
de reprise et limites](loltv.md#incident-du-26-septembre-2026) décrivent cette
correction. Les fixtures de test ajoutées sont synthétiques et ne remplacent
pas les fixtures esport du frontend ni les preuves conservées en production.

La durée LoLTV d’une carte live est calculée sur les événements horodatés du flux public, en retranchant les pauses publiées. Elle reste attachée à la date source de la trame, sans extrapolation locale ni nouvelle date pour un cache. La méthode et la comparaison réelle **34:15** de Pyramid–LODIS sont consignées dans [l’analyse LoLTV](loltv.md). Le rafraîchissement frontend ne crée aucune nouvelle mesure : il consulte la projection API et conserve les dernières données valides pendant une panne transitoire.

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

Depuis la décision produit du 15 septembre 2026, le scénario utilise exclusivement Stake et des relevés UTC sur plusieurs jours, comprenant des hausses et des baisses. Il ne s’agit pas d’un flux Stake : aucune cote réelle n’alimente ces fixtures. Les relevés réels restaurés le 23 septembre restent dans les tables `bookmaker_*`, séparées du scénario. Les badges de démonstration ont été retirés du produit pour conserver la même interface en modes mock et API ; cette limitation reste documentée ici et dans le README.

## Stake — audit public ponctuel du 22 septembre 2026

Sources primaires observées : [hub esport](https://stake.bet/fr/sports/esports), [filtre League of Legends](https://stake.bet/fr/sports/esports/league-of-legends), puis les liens de rencontre publiés dans cette liste. Le [rapport détaillé](stake-audit.md) inventorie 17 rencontres listées, sept fiches réellement ouvertes, 16 familles de marchés et 204 sélections distinctes dans ces fiches : 174 cotes numériques et 30 sélections désactivées. Les autres rencontres ne sont documentées qu’au niveau de leur aperçu ; l’exhaustivité du site n’est pas affirmée.

Les preuves comportent URL, horodatage UTC de lecture, DOM, arbre accessible, captures PNG et empreintes SHA-256. La période archivée va de 22:02 à 22:11 UTC le 21 septembre, soit le 22 septembre en heure de Paris. La date de lecture n’est pas un horodatage de mise à jour fourni par Stake. Les labels de seuil, de cote et de suspension sont conservés séparément ; l’unité non publiée des durées reste inconnue. Les textes éditoriaux hors périmètre sont omis avec signalement.

Le navigateur Patchright/Chromium de l’image worker existante a reçu un refus HTTP 403 au premier document esport. La navigation publique dans le navigateur Codex, accessible séparément, a ensuite été interrompue par une page Cloudflare 1015 ; aucune nouvelle navigation Stake n’a suivi dans cet audit. Aucun contournement, compte, mise ou paiement n’a été utilisé. La collecte applicative ultérieure et ses limites sont décrites dans [le guide Stake](stake-collector.md).

## Stake — données applicatives restaurées le 23 septembre 2026

### Distinction pré-match / live — 24 septembre 2026

La projection Matchs conserve séparément le dernier snapshot **par événement et phase publiée** (`bookmaker_snapshots.phase`). Les deux issues doivent exister dans ce snapshot ; aucune sélection manquante ou suspendue ne récupère le prix d’un relevé précédent. Chaque phase conserve ses horodatages. Les cotes pré-match restent consultables après le début ; les relevés live des rencontres terminées deviennent également historiques. Un événement bookmaker clos ou inconnu ne porte aucune value actuelle. Le rapprochement actif et unique reste obligatoire. Les estimations existantes étant pré-match, elles ne sont jamais associées aux prix live. Aucune nouvelle collecte ni probabilité n’est inventée pour remplir une phase absente.

### Marques des sources

Fichiers SVG locaux récupérés/vérifiés le **24 septembre 2026**, sans redessin des tracés :

- LoL : `/games/lol.svg`, source Riot déjà documentée ci-dessous.
- LoLTV : symbole `aria-label="LOLTV Logo"` du HTML public de [LoLTV](https://loltv.gg/matches), avec ajout du namespace SVG pour son utilisation en fichier autonome. `/sources/loltv.svg`, SHA-256 `1870aef38b5d91ba6dfcc61789f20447d25e07a10ad6bdf3a2a2d969c364579b`.
- Stake : tracés du [SVG archivé sur Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Stake_logo.svg), attribué à Stake, source originale stake.com, publication du 28 avril 2022. Namespace, viewBox, transformation et trois chemins conservés ; seules les métadonnées d’éditeur sont retirées. `/sources/stake.svg`, SHA-256 `0fadcfd17192c8c0ec8e5d962c61e8f0cca76f310521097a6deb6887880c26c1`. Le téléchargement direct de l’asset actuel identifié dans l’audit Stake a répondu 403 : arrêt de cette source, aucun contournement. Le fichier historique a été inspecté dans le navigateur sur Commons. Il ne garantit pas la dernière version de la marque.

Les deux marques monochromes utilisent leur silhouette SVG et la couleur du texte adaptée au thème. Oracle’s Elixir utilise une icône de données Lucide, explicitement descriptive, sans prétendre reproduire une marque officielle. Aucun asset distant n’est chargé par ces composants au runtime.

Le collecteur pré-match développé après l’audit du 22 septembre a été rétabli depuis la révision Git `7e10858`. Le dump local pris avant le retour de la base à `0012` a restitué 20 événements, 260 marchés, 760 sélections, 227 snapshots, 14 160 lectures de cotes, 31 payloads et cinq liens documentés vers des rencontres. Les enregistrements conservent leurs horodatages et preuves d’origine ; cette restauration n’est pas une nouvelle lecture du site et ne garantit aucune actualité des offres. Les données mock du frontend et le moteur de values restent séparés. Voir [le guide du collecteur](stake-collector.md) et [les preuves de collecte initiale](audits/stake/2026-09-22-pipeline/validation.json).

La demande suivante du 23 septembre étend la collecte publique aux marchés en direct, sans prise de pari. Les [captures live de Pyramid–LODIS](audits/stake/2026-09-22/README.md) du 21 septembre à 22:08 UTC montrent des sélections visibles et suspendues, sans cote, notamment dans les marchés de la carte 2 et de la carte 3. Elles prouvent la forme observée ce jour-là, pas la disponibilité actuelle de ces marchés. La migration `0016` conserve le motif et la date des cinq anciens arrêts pré-match dans `bookmaker_collection_resumptions` avant de permettre leur nouvelle lecture. Un prix reste une observation datée, pas une offre garantie entre deux passages de vingt minutes.

Un passage réel du nouveau collecteur a eu lieu le **23 septembre 2026, 19:08:18–19:13:49 UTC** : les 13 événements de la liste publique ont été collectés, dont trois en direct. Le run PostgreSQL `2fbc9710-39c4-4c5d-83f3-7febd9edcfa3` et ses snapshots/payloads conservent les horodatages et empreintes ; ses trois snapshots live contiennent 182 lectures cotées et deux suspensions sans cote. Des marchés « Gagnant » de carte sont présents dans chacun des trois directs. Aucun refus source n'a été déclaré pendant ce passage. Cette observation ponctuelle ne garantit ni la couverture du prochain direct ni la possibilité de miser à la date de lecture des données.

La vue Matchs expose ces relevés uniquement lorsque l’événement Stake dispose d’un rapprochement actif et unique vers les deux équipes de la rencontre. Elle ne retient que « Vainqueur du match » et « Vainqueur de la carte N », avec le dernier snapshot source disponible et l’horodatage propre de chaque sélection. Les issues suspendues affichent un tiret et « Suspendue » ; une sélection sans cote au dernier snapshot n’est pas remplacée par un prix historique. Les marchés de carte gardent leur numéro explicite. Une flamme de value exige en plus une estimation active pour la même rencontre, le même marché et la même équipe ; aucun taux n’est déduit des cotes. L’interface n’ouvre pas de pari.

En mode mock, quelques cotes de Matchs et une value positive sont des fixtures volontairement fictives destinées au rendu de l’interface ; d’autres rencontres n’ont aucun marché et certaines sélections sont suspendues. Elles ne reproduisent pas un flux Stake et ne sont pas des recommandations.

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

Pillow convertit les originaux PNG/JPEG/WebP/GIF de `static.lolesports.com`, ainsi que les images officielles déjà observées sur `cdn.loltv.gg`, en WebP local, au maximum 144 × 144 px. Les octets d’origine, les empreintes et les versions sont conservés. Le logo LOUD déclaré par Riot mesure 8334 × 8334 px : la limite de décodage tient compte de cet original et les conversions sont sérialisées pour borner la mémoire. Un téléchargement défaillant réutilise le cache local vérifié ; à défaut, l’identité demeure dans le catalogue sans logo plutôt que d’annuler toutes les autres mises à jour. Les URLs de logos du backend contiennent leur empreinte et sont servies par l’API ; aucune reconstruction du frontend n’est nécessaire pour les publier.

Les identités explicitement découvertes dans les rencontres LoLTV enrichissent le même référentiel : identifiant fournisseur, alias observés et URL d’image sont conservés sans écraser le nom Riot. Les qualificatifs d’équipes secondaires sont protégés afin que, par exemple, une variante de **MKOI Fénix** ne soit pas fusionnée avec **Movistar KOI**. Une collecte Riot ultérieure retient ces équipes et compétitions connues si elles sont momentanément absentes de ses pages. Cette stratégie couvre les entités effectivement exposées par les sources consultées ; elle ne garantit pas toutes les équipes LoL existantes.

Audit des emblèmes du **24 septembre 2026** : le catalogue publié sur `metiquo.com/api/v1/catalog` contenait 339 équipes, dont 43 identités LoLTV sans image locale. Leurs URLs `cdn.loltv.gg/teams` étaient conservées mais redirigeaient vers la page d’accueil lors des contrôles ponctuels, donc ne constituaient pas des images utilisables. Parmi ces 43 équipes, 31 ont un nom exact et unique avec un emblème Riot déjà local. Onze variantes de nom visuel revues dans `catalog_logos.py` associent le logo Riot de la même marque : KT Rolster Challengers/kt Challengers, Dplus Kia Challengers/DK Challengers, Gamespace Mediterranean College Esports/Gamespace M.C., Magaza Esports/MAGAZA, Team Heretics Academy/Heretics Academy, RED Canids/RED Kalunga (URL LoLTV `red-kalunga`), Cloud9/Cloud9 Kia, Team Liquid/Team Liquid Alienware, 1TAP Dino/Saigon 1TAP DINO, SN CyberCore Esports/TP.HCM SN CyberCore Esports et 9Gaming/Saigon 9Gaming Esports. Les noms et images Riot sont ceux du [catalogue public LoL Esports](https://lolesports.com/), et les noms/URLs LoLTV sont ceux de [ses pages de matchs publiques](https://loltv.gg/matches). Ces rapprochements servent uniquement l’affichage des emblèmes : aucune affiliation, rencontre ou résultat ne peut en être déduit. La dernière équipe, MVK Esports Academy, possède déjà une [image officielle Riot](https://static.lolesports.com/teams/1771230115237_Orange_Black_Logo.png) disponible en HTTP 200 ; l’API l’utilise jusqu’à ce que le worker la conserve localement. Cet audit porte sur les 339 entrées observées ce jour, pas sur toutes les équipes ou les futures publications ; une correspondance multiple ou absente conserve l’icône générique.

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

Le scénario frontend de 34 marchés se répartit désormais de J−7 à J+7 autour du jour courant de Paris, calculé au chargement du module MSW. Les affiches, horaires, probabilités et relevés restent fictifs ; le catalogue Riot sourcé du 14 septembre et ses logos ne changent pas. Le mock ajoute séparément les identités et le calendrier WSCI sourcés sur LoLTV, sans leur créer de marchés ni de value fictive. Les identifiants des opportunités comportent la date pour distinguer les rencontres de journées différentes. Les relevés des rencontres passées précèdent leur horaire de début.

La nouvelle demande du 16 septembre sépare `/matches` des opportunités. Le mock décline les identités sourcées en rencontres fictives, avec cartes, scores, objectifs, compositions et alias de joueurs entièrement fictifs (`apps/web/src/mocks/esport.ts`). Les journées J−3 et J+3 sont volontairement vides pour vérifier les dates désactivées. Le score de série dérive des cartes gagnées. Il ne s’agit pas d’un calendrier officiel ni d’un flux live ; les statistiques restent celles du scénario horodaté, même lors d’une nouvelle lecture. L’API expose seulement les rencontres stockées, sans inventer de direct ni de compositions.

Performance utilise 120 décisions et règlements fictifs répartis sur environ 60 jours, avec gains, pertes et annulations. Chaque décision fige sa cote et sa probabilité avant le match. Cet historique est indépendant des opportunités courantes et permet uniquement de tester une simulation : il ne constitue ni un historique utilisateur réel ni une validation du modèle. Le mode API reste vide tant qu’une source ne fournit pas les règlements et décisions nécessaires.

## LoLTV — 21 septembre 2026

La refonte UI/UX de Matchs utilise les mêmes données, sans nouvelle collecte. Les compteurs et l’ordre des rencontres dérivent des statuts publiés. Les vainqueurs et durées affichés dans les onglets viennent des cartes ; l’âge d’une carte utilise uniquement son `updatedAt`, et reste inconnu si ce champ manque. L’écart d’or exige cinq joueurs avec or renseigné de chaque côté ; il n’est pas extrapolé à partir d’un roster partiel. Les filtres par poste conservent les identités et statistiques d’origine. Les entrées du catalogue sont regroupées par journée et région existantes, sans inventer de relation entre ligue, groupe et phase ni de lien de diffusion.

Sources primaires : [calendrier](https://loltv.gg/matches), [résultats](https://loltv.gg/matches/results), [finale LEC G2–Movistar KOI](https://loltv.gg/match/2026-09-20-g2-esports-vs-tbd), [Skillcamp–Arctic Pandas](https://loltv.gg/match/2026-09-21-skillcamp-vs-arctic-pandas). L’analyse du HTML embarqué, du DOM chargé, de la pagination et des limites figure dans [LoLTV](loltv.md). Les échantillons réduits de tests proviennent des pages effectivement reçues le 21 septembre 2026 ; ils ne décrivent pas l’état actuel.

Les identifiants LoLTV, URLs, dates de récupération, empreintes et documents compressés accompagnent les observations immuables. Un résultat incomplet n’établit pas le format ; un camp ou ban absent reste inconnu. Le catalogue LoL Esports est conservé et les alias ne sont reliés qu’en cas de correspondance non ambiguë. Les dates Oracle sans fuseau ne sont pas converties arbitrairement : des statistiques complètes exactement identiques peuvent fournir une preuve indépendante de rapprochement, sinon les données restent séparées.

L’optimisation du 21 septembre conserve le même budget source et vise une lecture live toutes les trente secondes, avec sessions anonymes réutilisées brièvement en mémoire. Une cadence de récupération plus courte ne rend pas un flux ancien plus récent : état du flux, horodatage source et date de récupération restent séparés. Les délais mesurés et l’écart observé entre résultat du flux et métadonnées HTML sont documentés dans [l’analyse LoLTV](loltv.md).

Le 24 septembre, des pages de pagination LoLTV ont servi un HTML d'août avec un `Age` HTTP de plus de 33 jours, malgré un HTTP 200 ; les premières pages de septembre étaient fraîches. Ces pages périmées ne peuvent plus établir la couverture J−7/J+7. Les captures historiques sont chargées depuis un manifeste vérifié et ne servent qu'à découvrir des fiches à relire ; seul un détail LoLTV récent et validé est publié. La capture conservée couvre les 17–20 septembre et permet le rattrapage de ces journées sur une installation neuve. La fenêtre et son année restent dynamiques pour le fonctionnement courant, y compris en novembre. Un démarrage neuf confronté à une pagination périmée nécessite toutefois une capture couvrant ses dates ; les dernières rencontres valides demeurent en base. [Constat, empreinte et traitement](loltv.md).

Les refus observés dans Chromium empêchent actuellement de certifier le direct complet depuis le worker. Le fait qu’une page s’ouvre dans le navigateur utilisateur ne prouve pas l’accès depuis Docker. La fenêtre J−7/J+7 borne le périmètre demandé, pas une affirmation d’exhaustivité de la source.

## Rapprochement des identités — 23 septembre 2026

L’[audit PostgreSQL préalable](audits/matching/2026-09-23/audit.md) conserve un export daté des 20 événements Stake, 440 rencontres LoLTV et 462 liens sportifs, ainsi que leurs dernières preuves pré-match. Ce travail n’est pas une nouvelle collecte réseau Stake. Le [résolveur backend](match-reconciliation.md) retrouve les 12 rencontres présentes du corpus ; huit événements restent en attente.

Les [alias audités](audits/matching/2026-09-23/reviewed-aliases.json) citent les deux pages fournisseur, le corpus local et la corroboration Riot WSCI ou le logo officiel Riot identique pour LOS/LØS. Leur validité est limitée au tournoi et aux dates documentées. Ils ne modifient pas les noms du catalogue. Les heures récupérées dans des snapshots anciens restent datées à ces observations ; jamais assimilées à un nouveau relevé. Une carte Oracle brute ne prouve ni une série, ni son format, ni un calendrier futur.

Le worker de [résultats des sélections](selection-results.md) ne collecte aucune nouvelle source : il lit les snapshots LoLTV et Oracle déjà publiés, avec leurs identifiants et empreintes, puis les relie aux marchés Stake uniquement via le rapprochement actif. L'heure de fin sportive n'est pas commune et vérifiée ; le délai de 30 minutes commence donc à la première observation en base d'un résultat final cohérent. La catégorie « annulé » signifie ici qu'une carte prévue dans un marché n'a pas été jouée d'après le score final ; elle ne prétend pas connaître une décision de remboursement réelle de Stake.
