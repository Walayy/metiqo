# Recette du MVP personnel

La recette relie les 22 critères de la SFG §31 aux cas exécutés dans une CI complète
sur le commit exact de release. Elle ne transforme pas une compilation, une liste
de tests ou un ancien rapport en preuve d'exécution. Les correspondances sont
explicites dans `infra/scripts/acceptance.py` et apparaissent avec les noms des
cas effectivement trouvés dans le rapport final.

## Exécuter la recette

Depuis un checkout propre, publier la branche et lancer le workflow `CI` avec
`critical_fault=true`. Vérifier sa fin et son refus, puis lancer le même workflow
avec `critical_fault=false` sur le même commit. Après succès de la CI normale :

```powershell
make acceptance CI_RUN=<identifiant-du-run-vert> NEGATIVE_CI_RUN=<identifiant-du-run-rouge>
```

La commande requiert le CLI GitHub connecté au dépôt. Elle lit directement les
deux runs, vérifie leurs SHA et les jobs obligatoires, puis télécharge les deux
artefacts du run vert. Le SHA-256 de chaque archive doit correspondre au digest
retourné par GitHub ; un chemin sortant du dossier d'extraction est refusé. Les
rapports JUnit doivent contenir les suites complètes sans doublon, exclusion,
échec ou erreur. Une disparition d'un cas requis fait échouer son critère.

Les preuves de sécurité, performance et démarrage doivent être vertes et porter
sur le même commit. Les identifiants des cinq images scannées doivent correspondre
au dernier build de la recette. La revue visuelle de QA-006 reste liée aux fichiers source et
aux deux captures inspectées par leurs empreintes. Une modification de ces
éléments exige une nouvelle revue ; elle ne reçoit aucun PASS implicite.

Les fichiers `report.json` et `report.md` sont écrits dans un nouveau dossier
`data/acceptance/`. Le JSON contient les commandes, versions mesurées, URLs de
runs, digests GitHub, empreintes et cas de test pour chaque critère. Un échec
d'accès ou une preuve invalide produit un rapport en échec, avec 22 FAIL et un
code de sortie non nul. Aucun test sauté n'est assimilé à un succès.

## Démarrage effectivement exercé

Le job runtime appelle `infra.scripts.startup_acceptance` avant les tests et les
mesures ; le scan final porte ainsi sur les mêmes images. Ce script crée un nom
de projet Compose aléatoire, vérifie l'absence
initiale de conteneurs, volumes et réseaux portant ce nom, puis lance la seule
commande utilisateur `make mock-demo`. Celle-ci vérifie les scénarios, construit
et démarre Compose, puis applique les migrations.

La recette exige quatre services sains, une readiness positive, sept pages
accessibles et la réponse de conformité personnelle avec deux portes NO-GO et
Stake désactivé. Elle utilise exclusivement les ports loopback 3000/8000 et refuse
une collision avec un service déjà présent. La fin supprime seulement son projet
et ses volumes neufs, puis vérifie leur disparition. Les logs et versions des
conteneurs accompagnent la preuve ; aucune donnée d'un autre projet n'est
effacée. Pour rejouer cet exercice séparément, fermer les serveurs de test qui
occupent ces ports puis lancer :

```powershell
uv run --frozen python -m infra.scripts.startup_acceptance
```

## Portée et archivage

La recette porte sur le MVP personnel, les fixtures identifiées et les services
réels nécessaires à l'exécution : PostgreSQL, worker, volumes, chiffrement,
restauration, API et navigateur. Les modèles et cotes synthétiques prouvent les
comportements testés ; ils ne constituent aucune validation financière ni licence
des sources. Les portes publiques et commerciales restent à NO-GO.

Les 22 critères doivent passer pour déclarer cette release personnelle terminée.
Archiver le rapport avec le SHA testé et les preuves téléchargées ; les artefacts
GitHub du workflow expirent après trente jours. Un commit documentaire ultérieur
peut référencer la release vérifiée mais ne doit pas être présenté comme ayant
reçu ses propres tests. P10 et P11 restent hors de cette recette.
