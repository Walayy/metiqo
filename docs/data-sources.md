# Référentiel LoL et logos

Collecte : **14 septembre 2026**. Source primaire : [LoL Esports, Riot Games](https://lolesports.com/en-US).

## Collecte et provenance

Les compteurs de l’interface sont libellés « équipes rattachées » : ils décrivent la ligue d’origine enregistrée dans le référentiel. Pour les compétitions internationales, l’interface indique « Participants non renseignés » ; elle ne déduit pas leurs participants des affiliations domestiques. Les traductions françaises des régions sont des libellés de présentation ; les identifiants et valeurs source sont conservés.

- Le menu public « All Leagues » expose les liens filtrés vers 35 compétitions de League of Legends. TFT est exclu du produit.
- Le script `scripts/sync-catalog.mjs` lit la page d’accueil et les 32 liens de filtres régionaux/internationaux. Il extrait le JSON transporté dans le HTML, sans exécuter les scripts du site.
- Les objets `Team` avec `homeLeague` sont prioritaires. Les équipes supplémentaires proviennent des `EventMatch` et de leurs `MatchTeam` identifiés.
- Une rencontre domestique est prioritaire sur un événement international pour attribuer la ligue d’origine d’une équipe. Cette inférence ne certifie pas un statut actif ni la totalité du roster 2026.
- La liste des sources est reproduite dans le script. Le résultat brut transitoire est dans `.cache/`, ignoré par Git. Le snapshot utilisable est versionné dans `apps/web/src/mocks/data/catalog.json`.
- Chaque entité conserve `sourceImage`, l’URL d’origine exacte du CDN officiel `static.lolesports.com`. Les logos ne sont ni inventés, ni recolorés. Les logos de ligues sont affichés en monochrome par filtre CSS pour la navigation, et conservent leur asset original sourcé.
- Sharp convertit les images en WebP, limite leur taille à 144 × 144 px, préserve leur transparence et évite l’agrandissement. Les fichiers servis par le navigateur sont locaux.

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

## Marques et droits

Les marques, noms et logos appartiennent à Riot Games, aux organisateurs et aux équipes concernés. Leur présence dans un site public n’équivaut pas à une licence commerciale générale. Le prototype local les utilise comme identifiants descriptifs et documente leur provenance ; les droits et conditions devront être vérifiés avant une exploitation publique du produit.
