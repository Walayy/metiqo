# Audit préalable du rapprochement — 23 septembre 2026

Audit effectué avant l'implémentation, sur PostgreSQL local en révision `0014`.
Les exports `before.json` (17:41:39 UTC) et `last-prematch-evidence.json`
conservent les identités et les dernières preuves pré-match, sans authentification.
Ils ne constituent pas une nouvelle collecte des sites.

## Résultats constatés

- 20 événements Stake, 440 rencontres LoLTV, 462 liens sportifs dont 22 projections
  Oracle. Aucun identifiant d'événement commun Stake/LoLTV n'est publié.
- Cinq liens Stake restaurés existent en base, mais leur ancien moteur n'existe
  plus. Leurs références `canonicalSeriesId` / `competitionMappingIds` ne sont plus
  vérifiables : conserver leur état comme historique, puis recalculer les preuves.
- Douze événements ont une rencontre LoLTV concordante dans cet export. Huit n'en
  ont pas : deux Tyler1, LES Promotion, Cloud9/Liquid et quatre promotions futures.
  Une absence dans cette base ne prouve pas une absence chez le fournisseur.
- Trois identités demandent une correspondance documentée, limitée au tournoi :
  Keyd Academy / Vivo Keyd Stars Academy, CFO Academy / CTBC Flying Oyster Academy,
  KOI Academy / Movistar KOI Fénix. LOS / LØS demande aussi une preuve d'identité.
  Un remplacement universel Academy = Fénix serait incorrect (plusieurs équipes
  de développement peuvent appartenir à la même organisation).
- Les noms du tournoi WSCI placent l'année à des positions différentes. LCS et
  CBLOL ajoutent « Playoffs », EMEA « LCQ ». Le libellé LoLTV moins détaillé ne
  contredit pas une phase connue ; deux phases ou saisons explicites différentes
  doivent au contraire bloquer le lien. Le nom de ligue parent seul perd la saison.
- `848607` a perdu son heure dans `bookmaker_events` après une lecture de liste
  live. Ses 15 snapshots pré-match conservent tous 17:00 UTC le 23 septembre.
  La preuve complète peut être récupérée, sans inventer l'heure depuis la liste.
- Oracle stocke des cartes et non une clé de série universelle. Le CSV sans fuseau
  ne prouve pas une heure UTC. La projection existante utilise les statistiques
  exactes ou un horaire vérifié ; sa sélection du plus proche sur ±36 heures est
  trop permissive en présence de rematches et doit être durcie.
- Les classes `SourceFixture` sont un ancien échafaudage sans tables migrées ni
  producteur actif. Créer une deuxième identité Stake dans ces tables dupliquerait
  `bookmaker_events`, les snapshots et les marchés déjà utilisés.

## Décisions avant codage

1. Garder `matches.id` comme identité de série et `bookmaker_events.id` comme
   identité distincte du bookmaker. Plusieurs événements Stake peuvent pointer
   vers une série ; jamais déduire un marché ou une sélection de ce seul lien.
2. Construire un résolveur déterministe sans score flou, seuil de similarité ou
   préférence pour le candidat le plus proche. Exiger deux équipes, une compétition
   compatible et un horaire UTC ; conserver tous les candidats dans ±30 minutes.
   Plusieurs candidats restent ambigus. Deux orientations possibles restent ambiguës.
3. Préserver les qualificatifs d'équipe. Les équivalences non triviales sont des
   données révisables avec provenance, identifiant cible fournisseur, tournoi et
   intervalle de validité ; aucune exception nominative dans le code du résolveur.
4. Journaliser les changements d'identité et de décision, y compris A→B→A.
   Réévaluer aussi les liens existants ; retirer atomiquement un lien exploitable
   devenu ambigu ou contradictoire. Ne jamais transférer silencieusement un lien
   d'une série à une autre après une contradiction.
5. Conserver toutes les découvertes Stake avant la collecte des marchés, même en
   cas d'échec ou de budget épuisé. Préserver les derniers champs renseignés lors
   d'une lecture partielle ; ne pas présenter ces champs comme relus à cet instant.
6. Réexaminer les événements après publication Stake, LoLTV et Oracle. Une rencontre
   à deux mois reste en attente puis se résout à son arrivée. Ajouter une commande
   locale de diagnostic à blanc et une commande de reprise sans réseau.
7. Préserver les données brutes Oracle. Une carte brute non rattachable à une série
   ne devient pas une série inventée. Les liens Oracle existants sont exposés dans
   la preuve du lien Stake, avec leurs identifiants de cartes.

## Vérification des variantes

Les noms et horaires Stake/LoLTV figurent dans les exports. Le
[tableau publié par Riot pour WSCI 2026](https://lolesports.com/en-US/results/117127352507559759/stage/117127385836228518)
corrobore les identités d'académies. La
[publication de Movistar du 15 septembre](https://movistaresports.com/movistar-koi-fenix-se-clasifica-al-wsic-2026/)
identifie Fénix comme son représentant WSCI. Ces preuves, le tournoi, l'adversaire
et l'heure concordants permettent une correspondance auditée limitée à ce tournoi,
pas une équivalence mondiale de tous les libellés KOI. Aucun contournement Stake,
aucune connexion bookmaker et aucun pari n'ont été effectués.

## Validation prévue

Rejouer les 20 événements réels ; tester retards d'arrivée, mois futurs, ordre
inversé, académies, collisions de noms/codes, rematches, saisons/phases divergentes,
fuseau absent, reports contradictoires, révocation d'alias, observations hors ordre,
répétitions A→B→A, concurrence et droits SQL. Vérifier les migrations et le cycle
complet en PostgreSQL isolé, puis lancer `npm run check`. Aucun parcours frontend
n'est modifié.
