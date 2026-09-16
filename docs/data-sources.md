# Référentiel LoL et logos

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

| Jeu               | Page primaire                                       | Asset exact                                                                                                                                                           | Fichier local |
| ----------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| League of Legends | [Site Riot](https://www.leagueoflegends.com/en-us/) | [Favicon SVG déclaré dans le HTML](https://cmsassets.rgpub.io/sanity/images/dsfx7636/news_live/d3b7bd9decb1e1672dcb80be4f8bc1aa05490dc1-110x70.svg?accountingTag=LoL) | `lol.svg`     |
| Counter-Strike 2  | [Site Valve](https://www.counter-strike.net/cs2)    | [Logo compact déclaré dans la feuille CSS officielle](https://cdn.akamai.steamstatic.com/apps/csgo/images/csgo_react/global/logo_cs_sm.svg)                           | `cs2.svg`     |
| Dota 2            | [Site Valve](https://www.dota2.com/home)            | [Symbole déclaré dans la feuille CSS officielle](https://cdn.steamstatic.com/apps/dota2/images/dota_react/global/dota2_logo_symbol.png)                               | `dota2.png`   |

Ces entrées identifient des jeux dans le sélecteur. Elles ne constituent pas un catalogue de marchés ni une vérification de leur couverture de paris. CS2 et Dota 2 sont désactivés et annoncés « À venir ». Les marques et assets Valve restent la propriété de Valve.

## Référentiel backend LoL — 15 septembre 2026

La commande permanente `metiquo-worker sync-lol-catalog` découvre le registre `Query.leagues` dans le HTML public [LoL Esports](https://lolesports.com/en-US), puis consulte le filtre public de chaque slug découvert. Aucun inventaire de ligues fermé ne pilote la collecte. Les régions conservent leurs valeurs source ; les divisions, saisons, splits et tournois sont conservés lorsqu’ils sont exposés.

La collecte réelle terminée le **15 septembre 2026 à 20:31:09 UTC** a publié **35 ligues, 262 équipes et 295 URLs d’images**, après lecture de **36 pages**. Deux identités peuvent partager une URL ou les mêmes octets : le nombre d’images n’est pas le nombre d’entités. Ce bilan décrit les pages consultées, sans garantir tous les circuits, équipes ou rosters existants.

Les entités conservent les URLs de preuve, et les exécutions référencent les pages HTML compressées avec SHA-256 et date de récupération. Les affiliations distinguent une ligue d’origine déclarée (`homeLeague`) d’une participation à un tournoi ou à une rencontre. Une saison n’est reliée que si la source donne cette relation ; notamment, la présence d’une date en 2026 ne suffit pas à attribuer une saison 2026. Les périodes sourcées de participation restent accessibles même en l’absence de cette relation.

Pillow convertit les originaux PNG/JPEG/WebP/GIF de `static.lolesports.com` en WebP local, au maximum 144 × 144 px. Les octets d’origine, les empreintes et les versions sont conservés. Le logo LOUD déclaré par Riot mesure 8334 × 8334 px : la limite de décodage tient compte de cet original et les conversions sont sérialisées pour borner la mémoire. Les URLs de logos du backend contiennent leur empreinte et sont servies par l’API ; aucune reconstruction du frontend n’est nécessaire pour les publier.

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

Le scénario frontend de 34 marchés se répartit désormais de J−7 à J+7 autour du jour courant de Paris, calculé au chargement du module MSW. Les affiches, horaires, probabilités et relevés restent fictifs ; le catalogue sourcé du 14 septembre et ses logos ne changent pas. Les identifiants des opportunités comportent la date pour distinguer les rencontres de journées différentes. Les relevés des rencontres passées précèdent leur horaire de début.

La nouvelle demande du 16 septembre sépare `/matches` des opportunités. Le mock décline les identités sourcées en rencontres fictives, avec cartes, scores, objectifs, compositions et alias de joueurs entièrement fictifs (`apps/web/src/mocks/esport.ts`). Les journées J−3 et J+3 sont volontairement vides pour vérifier les dates désactivées. Le score de série dérive des cartes gagnées. Il ne s’agit pas d’un calendrier officiel ni d’un flux live ; les statistiques restent celles du scénario horodaté, même lors d’une nouvelle lecture. L’API expose seulement les rencontres stockées, sans inventer de direct ni de compositions.

Performance utilise 120 décisions et règlements fictifs répartis sur environ 60 jours, avec gains, pertes et annulations. Chaque décision fige sa cote et sa probabilité avant le match. Cet historique est indépendant des opportunités courantes et permet uniquement de tester une simulation : il ne constitue ni un historique utilisateur réel ni une validation du modèle. Le mode API reste vide tant qu’une source ne fournit pas les règlements et décisions nécessaires.

### Portraits des champions — 16 septembre 2026

Dix portraits officiels sont récupérés depuis Riot Data Dragon **16.18.1**, version retournée par `https://ddragon.leagueoflegends.com/api/versions.json` lors de cette récupération. Les noms et fichiers proviennent de `https://ddragon.leagueoflegends.com/cdn/16.18.1/data/fr_FR/champion.json`. [Documentation primaire Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon). Les URLs exactes, noms et date sont conservés dans `apps/web/src/mocks/data/champions.json` ; fichiers originaux dans `apps/web/public/champions/`. Champions : Gnar, Vi, Ahri, Jinx, Nautilus, Renekton, Sejuani, Azir, Kai’Sa et Rakan. Aucune couverture de tous les champions ou actualité automatique n’est annoncée. Ces images identifient les champions d’une composition fictive, sans assertion sur leurs choix par des joueurs réels. Les assets League of Legends restent la propriété de Riot Games.
