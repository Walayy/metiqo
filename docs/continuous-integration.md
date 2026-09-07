# Gate de release du MVP

Le workflow `CI` exécute les contrôles du dépôt avec Node, Python, pnpm et uv
verrouillés. Les actions GitHub sont référencées par leur commit complet. Il
n'utilise aucun secret de production. Les mots de passe des bases et du compte
Owner sont des fixtures locales aux runners.

## Contrôles obligatoires

| Job                   | Preuve requise                                                                                                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Qualité               | Cutoff anti-fuite, formats, lint, types stricts, contrats générés, tests Python et composants.                                                                                                                                                   |
| Migrations PostgreSQL | Images construites depuis un commit propre, scans, toute la suite Python sur PostgreSQL réel, Owner dans Chromium, sentinelles du bundle, reprise, atomicité, sauvegardes et restauration, permissions et TLS vérifié, mesures des lectures SQL. |
| Interface Playwright  | Parcours mock, captures comparées, clavier, thèmes et fautes réseau ; aucun test sélectionné n'est sauté.                                                                                                                                        |
| Build Docker          | Confirme le résultat du job qui a effectivement construit, scanné et exercé les images ; conserve le nom déjà exigé par la protection de branche.                                                                                                |
| Gate MVP              | Refuse tout résultat manquant, échoué, annulé ou sauté parmi les trois jobs d'exécution.                                                                                                                                                         |

Les intégrations facultatives d'un `make check` développeur deviennent obligatoires
dans le job PostgreSQL. Celui-ci fournit toutes les images, la base jetable, le
scanner de secrets et les outils de chiffrement. Il active `RUN_OWNER_BROWSER=1`
et `RUN_BUNDLE_SECRET_SCAN=1`. Son rapport JUnit doit contenir des tests exécutés,
sans erreur, échec ou exclusion. Le job navigateur exclut uniquement les deux
cas Owner, exécutés séparément contre la vraie base par la suite Python.

Un échec de migration, d'ingestion, de règlement paper, de déterminisme ou de
cutoff fait échouer une commande obligatoire. Aucun `continue-on-error` ne
transforme ce résultat en succès. Les données de capacité et les modèles des
fixtures ne constituent aucune validation financière.

## Exercice négatif

Le lancement manuel du workflow accepte `critical_fault=true`. Cette option
modifie uniquement le checkout éphémère du job Qualité : les deux gardes de cutoff
acceptent à tort une observation exactement à l'instant de décision. La vraie
suite anti-fuite doit alors échouer. Les jobs coûteux sont sautés et le gate final
doit être rouge. Cette exécution est une preuve de refus, jamais une release.

Le script refuse son utilisation directe hors GitHub Actions. Son test local
copie les modules dans un répertoire temporaire, injecte la même faute et exécute
la suite anti-fuite réelle. Les sources de travail restent identiques.

## Artefacts et provenance

Les rapports navigateur et runtime sont conservés trente jours, y compris après
un échec. Ils contiennent les rapports JUnit, les captures et traces Playwright,
les rapports de sécurité avec empreintes des images et les mesures API. Une
release archive les artefacts du run exact avec le SHA testé et son URL ; le
résultat d'un ancien commit ne vaut pas pour un nouveau commit.

Deux correspondances Gitleaks du rapport QA-004 sont des SHA-256 recalculés :
le journal OpenAPI et le fichier du composant Owner. Leur règle exige le chemin
exact du rapport et l'une des deux valeurs exactes. Un test vérifie qu'elle ne
masque ni une autre valeur dans ce fichier ni la même valeur sous un autre chemin.
Les rapports de vulnérabilités ne bénéficient d'aucune exception.

`infra/scripts/build_images.py --require-clean` interdit une image présentée comme
issue d'un commit alors que le checkout est modifié. Les images Python exposent
le commit complet par le label OCI de révision et `APP_CODE_COMMIT`. Le runbook
décrit le comportement de l'entraînement en l'absence de cette provenance.

L'exercice de restauration hebdomadaire utilise le même Dockerfile PostgreSQL que
la release et refuse lui aussi tout test sauté. Il reste indépendant de la CI de
chaque changement.
