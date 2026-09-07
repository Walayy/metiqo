# Gate P7 et début de l'historique financier

Le système commence son historique financier au moment où des cotes autorisées sont réellement collectées et horodatées. Les résultats Oracle's Elixir permettent d'évaluer un modèle statistique et de régler une décision ; ils ne permettent pas de reconstituer des prix bookmaker absents. Un bon backtest statistique ne constitue donc pas un backtest financier.

Les métriques financières utilisent exclusivement le ledger avec son snapshot de cote d'entrée exact. Les captures sans preuve temporelle exploitable ne produisent pas de ROI. Une clôture manquante ne devient pas un CLV estimé. Les signaux, décisions, règlements et rapports publiés sont immuables ; une correction laisse les pertes et les rapports précédents visibles dans l'audit.

Après le démarrage de la collecte, `make paper-settle` vérifie les résultats OE, et `make paper-report CURRENCY=EUR JSON=1` matérialise le bilan de la devise. Le dashboard lit ce bilan et annonce son heure de calcul. Le rapport décrit la méthode, les effectifs, les intervalles disponibles, les opportunités non prises, les mouvements de cote et les corrections. Voir [les conventions financières](paper-financial-metrics.md) et [le ledger](paper-ledger.md).

## Preuve technique reproductible

```console
make paper-gate OUTPUT=data/paper-gate-example.json
make test-paper
make check
pnpm exec playwright test tests/e2e/paper-trading.spec.ts tests/e2e/real-paper.spec.ts
```

`TEST_DATABASE_URL` doit désigner l'instance PostgreSQL de test avec droit de créer une base. Le script `demo_paper_gate.py` crée sa propre base vide, exécute les migrations et le parcours API réel avec les fixtures contrôlées, puis supprime cette base. Il n'effectue aucune mise et ne contacte aucun bookmaker.

Le parcours capture des cotes synthétiques via le vrai import manuel, résout les mappings, produit une prédiction et un signal audité, crée la décision paper via l'API, conserve une attente de résultat, puis règle une perte depuis la publication OE de fixture. La dernière cote pré-match est exposée comme proxy. Le rapport et ses empreintes sont vérifiés ; le résultat fourni à la main est refusé et les DTO mock/réel sont comparés.

[L'exemple généré](examples/paper-gate-fixture.json) conserve les prix, timestamps, identifiants et empreintes issus de cette exécution. Il porte `fixture: true` et `financialPerformanceValidated: false`. Son entrée à `8`, sa clôture à `4` et sa perte de `10` démontrent le raccord des preuves et les formules. **Il ne constitue ni une performance live ni un historique financier réel.** Les mesures financières en conditions réelles restent non validées tant que le système ne dispose pas d'une collecte effective après démarrage.

Le parcours intégré utilise le modèle game winner et une série BO1. Les moteurs de règlement de séries sont testés sur leurs formats, mais le gate d'entrée continue de refuser l'assimilation d'une probabilité de game à une probabilité de série BO3. Les validations externes, les droits des sources et les gates de lancement public/commercial restent séparés de cette preuve technique.
