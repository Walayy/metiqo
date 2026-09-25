# Rapprochement Stake ↔ LoLTV ↔ Oracle

Implémentation backend du 23 septembre 2026, corrigée le 25 septembre pour les
reports d'horaire et précédée de
[l'audit PostgreSQL](audits/matching/2026-09-23/audit.md). Aucun changement frontend,
fixture, authentification, moteur de values ou règle de marché.

## Identités et preuves

`matches.id` est la clé de série sportive. `bookmaker_events.id` conserve l'identité
Stake indépendante, même quand la rencontre est absente. Le jeu et le fournisseur
font partie de l'identité ; leurs identifiants ne sont jamais comparés comme s'ils
appartenaient au même espace.

Le résolveur `fixture_identity.py` exige :

- deux équipes identifiées par ID du même fournisseur, nom/alias observé exact,
  ou correspondance auditée ; casse, accents, ponctuation et les mots génériques
  Team/Esports/Gaming/Club sont normalisés, sans rapprochement flou ni sous-chaîne ;
- la même compétition, en conservant années, éditions, divisions et phases connues.
  L'année peut changer de position dans le libellé. Une phase absente ne contredit
  pas une phase publiée ; deux phases explicites différentes bloquent le lien ;
- un horaire Stake avec fuseau. Un premier lien exige un écart maximal de 30 minutes
  avec l'horaire actuel **ou un horaire antérieur observé pour le même identifiant
  Stake, la même paire et la même compétition**. Ce seuil sert uniquement à trouver
  un premier candidat ; il n'impose pas une concordance permanente des calendriers ;
- une seule rencontre et une seule orientation possibles parmi **tous** les
  candidats plausibles. Le plus proche n'est jamais choisi pour lever un doute.

Les codes courts ne sont pas devinés à partir des noms. Academy, Junior,
Challengers, B, II et les autres qualificatifs restent présents. Les noms inconnus
et placeholders ne deviennent pas des identités.

Les candidats viennent des rencontres LoLTV ou des séries déjà établies avec
Oracle. Les noms originaux de tournoi LoLTV priment sur la marque parent du catalogue.
L'index temporel `ix_matches_starts_at` et des fenêtres SQL fusionnées couvrent
l'horaire actuel et les horaires Stake observés. Le match déjà lié est également
chargé par son ID, même si son horaire sportif est désormais éloigné. Les décisions
citent les observations immuables utilisées et distinguent `current-schedule`,
`observed-schedule` et `retained-identity`.

## États et réévaluation

| État | Signification | Lien exploitable |
| --- | --- | --- |
| `linked` | Une identité démontrée | Oui |
| `pending` | Rencontre absente ou preuves insuffisantes | Non |
| `ambiguous` | Plusieurs rencontres/orientations plausibles | Non |
| `conflict` | Preuves contradictoires ou ancien lien devenu invalide | Non |

Un événement à deux mois reste enregistré sans créer une rencontre fictive. Chaque
publication Stake, LoLTV ou Oracle réévalue les données pertinentes, y compris les
liens antérieurs. Une contradiction retire le lien actif dans la même transaction
et conserve son historique. Une correction peut rétablir la même série ; un événement
déjà rattaché ne migre jamais silencieusement vers une autre série. Son identifiant
sportif, les deux équipes et le tournoi sont revérifiés à chaque passage ; la durée
d'un report ne retire plus ce lien. Une revanche compatible près du nouvel horaire,
un changement d'adversaire ou de compétition, une contradiction d'alias ou une
preuve devenue insuffisante le suspend. Les anciens horaires observés ne servent
plus à proposer une autre rencontre après l'établissement d'un lien : une erreur
temporaire d'horaire ne doit pas rendre une revanche ancienne plausible indéfiniment.

Les écritures d'identité sont sérialisées par verrou transactionnel PostgreSQL,
avant les verrous de lignes/catalogue. La transaction publie les données et leur
résolution ensemble. Les commandes de diagnostic ne contactent aucun fournisseur.

Les découvertes Stake sont enregistrées page par page avant de parcourir les marchés,
y compris si une pagination ou un détail échoue ensuite. Une lecture partielle ne
remplace pas une identité complète par des champs vides ou abrégés. Une observation
ancienne est conservée, mais ne rembobine pas l'état courant. Un arrêt de collecte
n'empêche pas d'auditer l'identité déjà acquise.

Pour les données restaurées ayant perdu leur horaire, le résolveur peut retrouver
celui du dernier snapshot complet **si la paire ordonnée et la compétition n'ont
pas changé**. L'ID du snapshot, son empreinte et sa date figurent dans la décision :
ce n'est jamais annoncé comme une nouvelle lecture.

## Alias révisables

`match_identity_aliases` stocke des correspondances limitées au fournisseur, au jeu,
au libellé source, à la clé de compétition et à un intervalle `[début, fin[`.
La cible est un ID d'équipe fournisseur, pas un nom approximatif. Deux cibles
contradictoires pour le même contexte bloquent le lien.

Les [quatre correspondances initiales](audits/matching/2026-09-23/reviewed-aliases.json)
documentent Keyd Academy, CFO Academy, KOI Academy au WSCI 2026, et LOS au CBLOL
audité. Les preuves contiennent les pages source, l'export daté et le raisonnement
de revue. Le cas KOI reste limité à ce tournoi : Academy n'est pas un synonyme
universel de Fénix. LOS/LØS est aussi corroboré par le même logo Riot dans le catalogue.
Les nouveaux alias s'ajoutent comme données, sans modifier le résolveur.

Un import est idempotent par empreinte du document de chaque alias. Il ne réactive
pas un alias révoqué. Un alias incorrect peut être révoqué ; tous les liens sont
immédiatement réévalués. Le catalogue et ses noms affichés ne sont pas modifiés.

## Oracle et les cartes

Oracle est une source de cartes historiques, pas un calendrier futur. Un CSV brut
seul n'est pas une identité de série et aucun BO n'est déduit du nombre de lignes.
La chaîne utilisable est `bookmaker_match_links.match_id` → `match_source_links`
(provider `oracles-elixir`) → `source_names.games`, avec les preuves de projection.
Un lien Stake peut être établi avant qu'Oracle publie ses cartes ; ces références
Oracle sont ajoutées à sa justification lors de leur publication.

La projection Oracle privilégie les signatures exactes de cartes terminées
(équipes, numéro, vainqueur, dix champions/postes/KDA), même lorsqu'un fuseau est
disponible. Une signature contradictoire interdit le recours à l'heure seule.
À défaut, elle exige des équipes et une ligue concordantes, une heure vérifiée et
**un unique candidat** : la carte doit commencer entre 30 minutes avant et 8 heures
après la série. Ces bornes conservatrices peuvent laisser des cas exceptionnellement
retardés non liés. L'ancienne préférence du plus proche dans ±36 heures est supprimée.

## Schéma et exploitation

La migration `0015` ajoute le journal d'observations d'événements, les alias, l'état
de résolution, le journal de décisions et la vue `bookmaker_matching_status`.
`bookmaker_match_links` contient uniquement les liens actuellement démontrés.
Les cinq anciens liens restaurés sont archivés dans le journal avant réévaluation.
Les anciens modèles non migrés `SourceFixture*`, sans données ni producteur, sont
retirés pour éviter une seconde identité Stake concurrente.

Les observations d'identité consécutives identiques sont dédupliquées ; A→B→A est
conservé. Les décisions sont ajoutées lorsque leur preuve change. Les triggers SQL
interdisent UPDATE/DELETE des deux journaux. L'API a uniquement SELECT sur ces données ;
le worker peut gérer les liens et révoquer un alias, sans toucher aux comptes utilisateurs.

Après configuration de `METIQUO_DATABASE_URL` avec le rôle approprié :

```powershell
# Rôle administrateur SQL : migration additive.
uv run --frozen alembic upgrade head

# Rôle worker : diagnostic, sans écriture ni réseau.
uv run --frozen metiquo-worker reconcile-matches --dry-run

# Import initial, puis réévaluation atomique. Pas nécessaire aux relances suivantes.
uv run --frozen metiquo-worker import-match-aliases docs/audits/matching/2026-09-23/reviewed-aliases.json

# Reprise du rapprochement de tout le stock, sans collecte réseau.
uv run --frozen metiquo-worker reconcile-matches
uv run --frozen metiquo-worker revoke-match-alias <empreinte>
```

Aucune nouvelle variable d'environnement, dépendance ou planification : les
collecteurs autorisés déclenchent la réévaluation lors de leur publication. Après
une mise à jour du code local, reconstruire le worker Docker et redémarrer le worker
Stake natif pour charger le nouveau mécanisme. Exécuter ensuite une fois
`reconcile-matches --dry-run`, contrôler les décisions proposées, puis
`reconcile-matches` pour restaurer les liens suspendus uniquement par un report
d'horaire. Les commandes ci-dessus ne font aucun pari.

```sql
SELECT source_id, competition_name, status, match_id,
       evidence->>'reason' reason, participant_mapping
FROM bookmaker_matching_status ORDER BY starts_at, source_id;

-- Base pour les futurs marchés : le lien événement/série et les participants
-- sont disponibles, mais aucune sémantique de cut ou de règlement n'est déduite.
SELECT q.event_source_id, l.match_id, l.evidence->'participants' participants,
       q.market_id, q.selection_id, q.scope, q.period, q.line, q.odds, q.observed_at
FROM bookmaker_current_quotes q
JOIN bookmaker_match_links l ON l.event_id=q.event_id;
```

## Couverture constatée

Le corpus du 23 septembre contient 20 événements Stake ; les 12 rencontres LoLTV
présentes attendues sont retrouvées. Huit événements restent en attente : deux
Tyler1, LES Promotion, Cloud9/Team Liquid et quatre promotions futures.
« Pending » ne distingue pas magiquement une rencontre inexistante d'une source
pas encore collectée. Une offre visible au dernier relevé ne prouve pas qu'elle
est encore disponible maintenant ni qu'un pari serait accepté.

Depuis la migration `0017`, seules les sélections des marchés « Vainqueur du match »
et « Vainqueur de la carte N » sont interprétées par le
[worker de résultats](selection-results.md). Les autres catégories, cuts et règles
de règlement restent un travail ultérieur. La qualité du corpus audité est testée ; une garantie universelle de
100 % malgré des champs inconnus, erreurs de source ou nouveaux alias ne l'est pas.
