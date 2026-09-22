# Sources et provenance

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

Depuis la décision produit du 15 septembre 2026, le scénario utilise exclusivement Stake et des relevés UTC sur plusieurs jours, comprenant des hausses et des baisses. Il ne s’agit pas d’un flux Stake : aucune cote réelle n’alimente ces fixtures. L’audit documentaire du 22 septembre décrit séparément des cotes publiques observées, sans import applicatif. Les badges de démonstration ont été retirés du produit pour conserver la même interface en modes mock et API ; cette limitation reste documentée ici et dans le README.

## Stake — audit public ponctuel du 22 septembre 2026

Sources primaires observées : [hub esport](https://stake.bet/fr/sports/esports), [filtre League of Legends](https://stake.bet/fr/sports/esports/league-of-legends), puis les liens de rencontre publiés dans cette liste. Le [rapport détaillé](stake-audit.md) inventorie 17 rencontres listées, sept fiches réellement ouvertes, 16 familles de marchés et 204 sélections distinctes dans ces fiches : 174 cotes numériques et 30 sélections désactivées. Les autres rencontres ne sont documentées qu’au niveau de leur aperçu ; l’exhaustivité du site n’est pas affirmée.

Les preuves comportent URL, horodatage UTC de lecture, DOM, arbre accessible, captures PNG et empreintes SHA-256. La période archivée va de 22:02 à 22:11 UTC le 21 septembre, soit le 22 septembre en heure de Paris. La date de lecture n’est pas un horodatage de mise à jour fourni par Stake. Les labels de seuil, de cote et de suspension sont conservés séparément ; l’unité non publiée des durées reste inconnue. Les textes éditoriaux hors périmètre sont omis avec signalement.

Le navigateur Patchright/Chromium de l’image worker existante a reçu un refus HTTP 403 au premier document esport. La navigation publique dans le navigateur Codex, accessible séparément, a ensuite été interrompue par une page Cloudflare 1015 ; aucune nouvelle navigation Stake n’a suivi. Aucun contournement, compte, mise ou paiement n’a été utilisé. La faisabilité du collecteur permanent n’est pas validée ; `StakeSource` demeure désactivé et les relevés restent exclusivement documentaires.

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

Les refus observés dans Chromium empêchent actuellement de certifier le direct complet depuis le worker. Le fait qu’une page s’ouvre dans le navigateur utilisateur ne prouve pas l’accès depuis Docker. La fenêtre J−7/J+7 borne le périmètre demandé, pas une affirmation d’exhaustivité de la source.
