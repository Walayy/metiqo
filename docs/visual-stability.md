# Stabilité visuelle — QA-002

Le scénario vérifie les neuf pages critiques à 1 440 × 960 et 390 × 844 pixels : opportunités, événements, fiche événement, fiche signal, modèles, données, administration, paper trading et détail d'une décision paper. Les réponses API sont retardées de 750 ms, y compris la vérification de session. Le navigateur observe les décalages depuis le premier rendu ; aucun décalage causé par une entrée utilisateur récente n'entre dans la somme. Le seuil est strictement inférieur à 0,05 pour chaque page.

Deux contrats de transport synthétiques exposent les six cartes d'exploitation et les seize métriques financières en mode réel. Leur réponse reste retenue jusqu'à la capture de deux images de chargement. La différence de hauteur entre chargement et résultat doit rester au plus de quatre pixels, même sous la zone visible. Ces valeurs de test ne constituent aucune validation financière ou mesure de production.

La suite refuse aussi les erreurs de console, avertissements et erreurs de page, ainsi que tout débordement horizontal global. Elle contrôle le thème sauvegardé à chaque image peinte, avec une préférence système opposée ; les deux thèmes sont vérifiés. Le changement de préférence de mouvement arrête immédiatement les animations de chargement. Le graphe de cotes reste monté et conserve ses dimensions pendant une actualisation lente au retour du réseau.

## Exécution

```powershell
pnpm install --frozen-lockfile
uv sync --frozen
pnpm exec playwright install chromium
pnpm exec playwright test tests/e2e/visual-stability.spec.ts tests/e2e/accessibility.spec.ts
pnpm test:e2e
```

Playwright construit et démarre le frontend de production et l'API mock, ou utilise les serveurs locaux déjà disponibles. Les fixtures mock restent isolées des données réelles. Le parcours Owner possède son exercice PostgreSQL séparé ; il n'est pas considéré comme exécuté lorsqu'il est ignoré dans la suite mock.

Les références sous `tests/e2e/*-snapshots/` distinguent Windows et Linux. Leur mise à jour exige une inspection des nouvelles captures puis une exécution de comparaison sans `--update-snapshots`. Les images des panneaux excluent uniquement les éléments fixes du shell pour éviter qu'ils recouvrent une capture plus haute que l'écran. Les mesures CLS et de dimensions utilisent la page sans cette modification ; les captures de pages complètes conservent le shell.

L'exercice Linux utilise l'image officielle Playwright 1.62.1 Noble, digest `sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`, avec Playwright 1.62.1 et axe 4.13.0. Son navigateur accède aux mêmes builds API/Next locaux via `host.docker.internal`. La CI exécute aussi le serveur et le build sous Linux ; seule cette dernière prouve l'ensemble du déploiement sur Linux.

## Corrections vérifiées

Le conteneur de `RemoteDataBoundary` conserve son identité, ses attributs et ses dimensions pendant le premier chargement. Les libellés et grilles des cartes d'exploitation et de finance restent en place ; les valeurs passent de squelettes à un résultat ou à une absence explicitement indiquée. Les emplacements de métadonnées réservent la hauteur nécessaire aux retours à la ligne sur mobile. Le catalogue des sources réserve aussi sa hauteur selon la largeur d'écran.

Les premières mesures ont révélé un CLS de 0,163 sur la page mobile des données et des agrandissements de 612 pixels pour l'exploitation mobile et 2 076 pixels pour les métriques financières mobiles. Le résultat final atteint au plus 0,0239 sur les deux navigateurs, avec une différence de hauteur nulle pour les quatre panneaux. La suite complète Windows passe avec 70 tests et un parcours Owner réservé ; les comparaisons finales passent avec 27 tests Windows et 33 tests Linux, sans régénération d'images. Les références sont versionnées avec les tests et leurs empreintes accompagnent les résultats dans `docs/evidence/qa-002/report.json`.

Le contrôle TypeScript inclut désormais les tests navigateur ; il refuse notamment les options de capture non reconnues au lieu de laisser Playwright les ignorer. Le navigateur observé est Chromium 151.0.7922.34 sur les deux systèmes. Les versions des lanceurs locaux sont conservées dans le rapport et ne remplacent pas les versions verrouillées des images de production. Les tests de schéma, de calcul et de persistance restent couverts par leurs suites respectives ; cette preuve concerne le rendu et les interactions décrites ci-dessus.
