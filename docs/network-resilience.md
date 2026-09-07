# Résilience réseau — QA-004

Une actualisation indisponible conserve la dernière lecture autorisée et affiche un avertissement avec une action de reprise. Les neuf pages critiques sont couvertes : opportunités, événements, fiche événement, signal, modèles, données, administration, paper trading et décision paper. Les tests vérifient que les nœuds affichant les données restent montés pendant l'erreur et après la reprise. Les panneaux opérationnels et financiers sont également exercés avec leurs contrats de transport réels synthétiques, dont une perte et un ROI négatif ; ces fixtures ne sont pas des mesures financières de production. L'annonce hors ligne occupe l'espace du badge du shell pour éviter de déplacer la page ; les captures desktop/mobile ont été inspectées et archivées avec le rapport.

## Limites et comportements

| Frontière                         | Comportement vérifié                                                                                                                                                                                                                   |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Requête navigateur                | Délai de 15 secondes combiné au signal d'annulation de l'appelant ; annulation également effective si le transport ne répond jamais                                                                                                    |
| Lecture récupérable               | Au plus une nouvelle tentative automatique ; bouton Réessayer après échec ; dernière lecture conservée avec avertissement                                                                                                              |
| Réponse 400, 401, 403, 404 ou 410 | Aucun résultat antérieur réutilisé pour cette lecture ; pas de nouvelle tentative automatique                                                                                                                                          |
| Décision paper absente            | Un 404/410 indique une ressource introuvable ; un 503 propose une reprise et ne prétend pas que la décision a été supprimée                                                                                                            |
| Écriture                          | Aucun POST rejoué automatiquement ; le corps d'erreur reste disponible pour expliquer le refus métier                                                                                                                                  |
| Connexion hors ligne              | État visible ; les requêtes ne restent pas suspendues indéfiniment dans la file du navigateur ; actualisation des lectures périmées à la reconnexion                                                                                   |
| Session Owner                     | Refus explicite de session : contenu privé retiré et cache métier supprimé. Vérification Owner indisponible : accès suspendu jusqu'à reprise. Le mode local sans authentification déjà confirmé conserve sa lecture avec avertissement |
| Pool API PostgreSQL               | Attente de connexion de deux secondes, attente de pool de deux secondes, requête SQL limitée à huit secondes et verrou à trois secondes ; connexion inactive interrompue remplacée lors de son prochain usage                          |
| Erreur PostgreSQL transitoire     | Réponse 503 au format Problem Details, trace et Retry-After ; aucun SQL ou détail du pilote exposé, aucune transaction rejouée automatiquement                                                                                         |
| Timeout Oracle's Elixir           | Échec de run structuré, snapshot courant et octets validés conservés ; lecture dégradée avec allow-stale et refus avec require-fresh                                                                                                   |

Les limites SQL concernent le processus HTTP. Les travaux longs restent destinés au worker. Le proxy Next possède aussi son propre délai de dix secondes ; la borne navigateur couvre notamment une coupure entre le navigateur et ce proxy. Ces limites s'appliquent à chaque requête et ne constituent pas une garantie de durée globale d'un parcours comportant plusieurs lectures.

Une lecture conservée n'est pas une nouvelle confirmation de fraîcheur. Les grades et les prédictions restent attachés à leurs snapshots ; les contrôles métier du serveur décident si une nouvelle action est admissible. Une permission refusée ne se transforme jamais en accès au cache antérieur.

## Exercices reproductibles

```powershell
pnpm exec playwright test tests/e2e/network-resilience.spec.ts
pnpm test:e2e
pnpm test:components
$env:TEST_DATABASE_URL='postgresql+psycopg://metiquo:metiquo@127.0.0.1:55436/metiquo?connect_timeout=5'
uv run --frozen python -m pytest tests/integration/test_network_resilience.py -q
$env:RUN_OWNER_BROWSER='1'
uv run --frozen python -m pytest tests/integration/test_owner_browser.py -q
```

La base doit être réservée aux tests : les migrations sont remises à zéro avant chaque exercice. L'exercice Owner exige aussi les ports 8000/3000 libres. Les suites PostgreSQL ne sont pas lancées simultanément sur la même base.

Le scénario PostgreSQL provoque réellement une annulation de requête par statement_timeout puis vérifie la réponse HTTP, la lecture suivante identique et le pointeur du snapshot. Un autre scénario termine uniquement la connexion inactive créée par le test, puis vérifie le remplacement de cette connexion. Le scénario provider ingère d'abord un CSV de fixture validé dans le stockage objet, injecte un timeout dans le client du transport public, vérifie le code du run et relit les octets avec leur manifeste. Il isole la classification du timeout de la sélection du miroir ; les cas de quota, quarantaine et reprise sur miroir possèdent leurs exercices d'ingestion existants.

Les états de refus de session et les métriques réelles synthétiques du navigateur ne simulent pas une persistance financière. La session Owner fait l'objet d'un exercice séparé avec son compte et ses cookies réellement persistés sur PostgreSQL. Les preuves et leurs empreintes sont archivées dans `docs/evidence/qa-004/report.json`.
