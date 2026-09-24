# Audit du rapprochement des rencontres Stake ↔ LoLTV / Oracle

**Mise à jour du 23 septembre 2026 :** cet audit initial est historique. Le [nouvel audit de la base restaurée](audits/matching/2026-09-23/audit.md) précède désormais le [mécanisme de rapprochement implémenté](match-reconciliation.md), avec journal, alias sourcés et réévaluation automatique. Les constats ci-dessous décrivent l'état antérieur, pas le code actuel.

**23 septembre 2026 — audit préalable à l'implémentation.** Périmètre : rencontres League of Legends, côté backend seulement. Le corpus vérifiable est l'[inventaire Stake du 22 septembre](audits/stake/2026-09-22/events.json), ses [captures horodatées](audits/stake/2026-09-22/README.md), les contrats et le code des collecteurs LoLTV et Oracle. Une nouvelle lecture directe du calendrier Stake a été refusée par l'outil de consultation (`robots.txt`) ; le worker avait reçu HTTP 403 et la session navigateur de l'audit précédent s'était terminée sur 1015. Aucun contournement ni affirmation sur le calendrier actuel n'en découle.

## Constat source

- Les 17 lignes archivées portent un identifiant numérique dans l'URL. Cet identifiant est celui **de l'événement Stake**, pas celui de LoLTV, d'Oracle, du widget Oddin ou d'un marché. Les 17 ID de l'inventaire sont distincts. Dix fiches n'ont pas pu être ouvertes ; les libellés de la liste restent une preuve de liste uniquement.
- 15 lignes ont une cote numérique au marché vainqueur de la liste et deux sont suspendues. « Parier maintenant » n'est pas testé : une cote affichée signale une offre observée, pas la possibilité effective de valider un pari. La collecte des cotes, cuts et marchés reste hors de cette livraison.
- La fiche et la liste peuvent abréger différemment les concurrents (`Movistar KOI Academy`, `KOI Academy`, `Movistar KOI.A` ; `chenchen5` / `chenchen53`). Les qualificatifs `Academy`, `Challengers`, `Junior`, etc. changent l'identité et ne sont jamais supprimés pour forcer un lien.
- Le calendrier donne une heure locale affichée sans fuseau publié dans les éléments relevés ; l'environnement de capture était réglé sur `Europe/Paris`. La date de collecte et le fuseau du navigateur ne transforment pas cette heure en horaire officiel Stake. Le direct `Pyramid IV Esports – LODIS` ne publiait pas d'heure dans la liste.
- Stake peut publier un événement hors de la fenêtre LoLTV J−7/J+7. Le CSV Oracle donne des **cartes historiques**, non un calendrier futur ni nécessairement une clé de série. L'absence d'une rencontre en base n'est donc pas une erreur de rapprochement.
- [Les règles publiques Stake](https://stake.com/policies/sportsbook) prévoient, lors d'un chronobreak LoL, la reprise de l'offre live avec **un nouvel ID de match**. Plusieurs ID Stake peuvent donc se rattacher à une même série sportive, tout en restant deux événements de bookmaker distincts.

## Audit du code existant

`match_source_links` conserve déjà une clé `(provider, source_id)` unique et relie LoLTV / Oracle aux rencontres internes. `resolve_match` travaille surtout lors de la création LoLTV : il exige des équipes reconnues, mais permet une proximité de six heures et ne conserve aucun événement Stake non résolu. `StakeSource` est volontairement inactif. Les cartes Oracle sont projetées sur des rencontres déjà connues ; un CSV brut seul n'est pas une preuve suffisante d'identité de série. Aucune table ne permet aujourd'hui d'auditer « observé chez Stake, absent chez LoLTV », d'attendre une arrivée future, puis de réessayer le lien.

## Contrat de rapprochement retenu

1. Conserver **tous les événements observés** indépendamment de la présence d'une rencontre interne, avec ID fournisseur, jeu, URL, deux noms dans leur ordre, compétition, horaire et qualité de l'horaire, état d'offre observé, date de lecture et empreinte. Conserver les observations successives immuables. Une absence ultérieure du listing n'efface pas l'événement.
2. Résoudre une série seulement parmi les rencontres soutenues par LoLTV ou par une projection Oracle effectivement établie. Une équipe cataloguée sans rencontre ne suffit pas. Le sens gauche/droite peut être inversé ; les deux identités doivent toutefois être démontrées, sans fusion d'académie avec équipe première.
3. Exiger une compétition concordante (nom ou alias sourcé, avec saison distincte) et un horaire concordant. Une heure affichée dans un navigateur sert de preuve de **coïncidence d'horloge locale**, jamais d'horodatage Stake vérifié. Une heure absente ne permet aucun lien automatique, même en direct, sauf identifiant intersource explicitement partagé et vérifié. La fenêtre temporelle étroite et l'unicité parmi tous les candidats empêchent de fusionner deux rematches.
4. Si zéro candidat : `pending`. Si plusieurs candidats ou des indices contradictoires : `ambiguous` / `conflict`, sans lien exploitable. Un nouvel ID Stake, un report d'horaire ou un changement de nom est réévalué à partir des observations et journalisé ; aucun lien sur simple proximité textuelle.
5. Réexaminer les événements en attente après chaque publication LoLTV et à l'import de nouvelles observations Stake. Les événements hors fenêtre restent présents sans créer de fausse rencontre. Le résultat est indépendant de l'ordre d'arrivée des sources.
6. Un lien associe l'**événement** Stake à la série interne. Il ne garantit ni identité de marché, ni carte, ni cut, ni cote, ni règle de règlement. Les ID de marché et de sélection restent inconnus dans les preuves actuelles.

## Cas de validation indispensables

| Cas | Résultat attendu |
| --- | --- |
| ID Stake déjà lié et observation identique | lien stable, aucune observation dupliquée |
| Événement Stake deux mois avant le calendrier LoLTV | `pending`, puis lien à l'arrivée de la rencontre |
| Rematch même paire, même tournoi, horaire proche | aucun lien si deux candidats plausibles |
| Côté Stake inversé | lien possible si identités, compétition et heure concordent |
| Équipe `Academy` / première équipe ; `Challengers` / première équipe | aucun lien croisé |
| Année de saison différente, même marque de ligue | aucun lien |
| Heure absente, ou zone non documentée | `pending` |
| Nouvel ID Stake après chronobreak | deux identités source distinctes, éventuellement une même série |
| Relevé tardif contredisant un lien | suspendre le lien exploitable et conserver la preuve antérieure |

La « perfection » signifie ici **zéro association non démontrée dans les cas couverts**, pas 100 % de rappel sur une source qui refuse l'accès ou ne publie pas tous les identifiants. Le nombre de vrais matchs Stake aujourd'hui, le taux de liaison live et l'exhaustivité face à LoLTV / Oracle ne peuvent pas être certifiés avec le corpus disponible.
