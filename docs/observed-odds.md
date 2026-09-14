# Consultation des cotes observées

L’onglet « Historique des vainqueurs » de `/odds` consulte `GET /api/v1/odds/quotes`. Les données proviennent du schéma
`odds`, y compris les événements à venir sans correspondance Oracle's Elixir.
Ce parcours ne crée ni résultat canonique, ni prédiction, ni opportunité de value.
L’onglet principal utilise désormais le [scraping public Stake](stake-public-scraping.md),
sans clé ni accès direct à une API Stake.

## Import d'un relevé

La commande opérateur suivante exige une base réelle migrée,
`APP_DATA_MODE=real`, `ODDS_PROVIDER=disabled` et un `OBJECT_STORE_ROOT` local :

```console
uv run --frozen oe odds-import --provider stake-observed --format json --file tests/fixtures/odds/stake-observed-20260908.json --json
```

Le fichier d'exemple est un relevé historique figé, décrit dans
[sa provenance](../tests/fixtures/odds/README.md). Cette commande ne contacte pas
Stake. Pour importer d'autres observations, le contrat CSV/JSON est décrit dans
[l'import manuel](manual-odds-import.md). Les octets sont limités à 10 Mio, validés
avant publication, archivés par SHA-256 dans `OBJECT_STORE_ROOT/odds`, puis
les événements du document sont publiés dans une transaction unique.

Le résultat JSON indique les événements, observations ajoutées, doublons et
référence du fichier archivé. Un rejeu exact ne crée aucun doublon. Un document
invalide ne publie aucune ligne. En cas d'échec PostgreSQL, l'objet source peut
rester archivé, mais la transaction ne publie pas une partie du document.

## Affichage et fraîcheur

L'API sélectionne la dernière observation par sélection, selon sa capture et non
sa date d'import. Elle accepte `provider`, `startsFrom`, `startsTo`, `offset` et
`limit` (1 à 100). Les dates de filtre exigent un fuseau. Les totaux sont conservés
même pour une page au-delà du dernier résultat.

Chaque réponse contient les participants, le début, le marché, la période, la
cote décimale, l'heure d'observation, son âge, l'état du marché et du fournisseur,
ainsi que le caractère informatif du relevé. Une observation plus ancienne que
`ODDS_MAX_AGE_SECONDS` ou sa surcharge fournisseur est périmée. Réimporter un
ancien fichier ne rajeunit pas les cotes ni le dernier succès de la source.

En mode mock, cette collection est vide avec `meta.dataMode=mock` : elle ne lit
jamais les cotes réelles. Les autres parcours de démonstration restent disponibles.

## Validation

```console
uv run --frozen pytest tests/integration/test_observed_odds.py tests/integration/test_odds_capture_history.py -q
```

`TEST_DATABASE_URL` doit pointer vers une base PostgreSQL de test jetable : les
fixtures d'intégration remettent cette base à zéro. Les tests vérifient l'import
des observations réelles enregistrées, le rejeu, la conservation du fichier,
la pagination, les dates, la fraîcheur, le rollback multi-événement et le refus
d'un identifiant immuable réutilisé avec un contenu différent.

La capture horodate désormais la réception après le retour du fournisseur.
Une réponse normale reçue après un délai réseau n'est plus rejetée comme future.
Un horodatage réellement postérieur à la réception reste refusé.

Pour isoler un build de vérification de l'interface déjà démarrée,
`METIQUO_NEXT_DIST_DIR` peut désigner un répertoire sous `apps/web` ; le chemin
par défaut reste `.next`.

## État vérifié le 8 septembre 2026

- Consultation réelle des pages Stake dans le navigateur : deux matchs à venir,
  14 sélections relevées, avec provenance dans la fixture.
- Exécution de `oe odds-import` sur PostgreSQL migré : deux événements et
  14 observations ajoutées ; rejeu exact : aucune nouvelle observation.
- Appel HTTP de `/api/v1/odds/quotes?limit=100` : statut 200, 14 sélections,
  `dataMode=real`, fraîcheur périmée après expiration du délai de 90 secondes.
- Tests : 492 tests Python hors infrastructure et 14 tests PostgreSQL réussis.
  Le test d'isolation mock/réel, ignoré sans base dans la première suite, est
  exécuté et réussi dans la seconde. Les tests Python hors infrastructure ont
  été lancés depuis un répertoire isolé du `.env` local, avec une copie du fichier
  `config/security-policy.json` requis par un test de sous-processus.
- Contrat OpenAPI, mypy, TypeScript, lint et build de production vérifiés.

La validation de l'écran dans un navigateur reste incomplète : la revue
automatique d'approbation a refusé le démarrage de l'instance web de vérification,
y compris avec une écoute limitée à `127.0.0.1`, en indiquant un blocage de
politique sans autre motif détaillé. L'ancienne instance locale ne contient pas
la nouvelle route. Les tests de composants couvrent l'affichage des relevés,
l'état vide, la reprise après erreur et la pagination, mais ne remplacent pas
cette validation navigateur.

La collecte automatique a depuis été implémentée par scraping des pages publiques,
conformément à la demande explicite du propriétaire. Les anciens blocages liés à
une clé ou à la documentation API ne sont plus des prérequis. Consulter le
[rapport du scraper](stake-public-scraping.md) pour les tests actuels et le refus
HTTP 403 constaté depuis le processus local.
