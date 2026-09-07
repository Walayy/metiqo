# Accessibilité — QA-003

<!-- cspell:words Échap -->

Les parcours critiques utilisent les contrôles HTML et les composants accessibles du shell : lien d'évitement, champs nommés, tableaux sémantiques, navigation mobile avec retour du focus, menu de thème et boutons d'action. Les résultats des filtres et les changements de cote sont annoncés poliment ; la cote attachée au signal reste affichée lorsque l'observation évolue. Les graphiques possèdent une description et un résumé textuel visible. Les grades, variations et erreurs comportent du texte ou des signes en plus de leur couleur.

La suite `keyboard-accessibility.spec.ts` utilise réellement Tab, Entrée, Échap et les flèches, sans positionner le focus par script ni cliquer sur les contrôles du parcours. Chaque étape vérifie que le contrôle est visible devant le contenu fixe et possède un indicateur de focus. Elle couvre le filtre, l'ouverture du signal, la création et le règlement fictifs, la synchronisation mock, la revue de mapping, l'alias daté, l'entraînement et son erreur. Les parcours de mutation sont rejoués sur desktop et mobile ; ils ne constituent pas une opération financière réelle.

Le catalogue mock expose une seule revue immuable. Les parcours de mapping rejouent sa même approbation canonique avec la même clé d'idempotence, y compris dans la suite historique, après avoir contrôlé la sélection d'un autre candidat au clavier. Cette réutilisation ne change pas la validation du serveur réel.

## Contrôles automatisés

```powershell
pnpm exec playwright test tests/e2e/keyboard-accessibility.spec.ts tests/e2e/accessibility.spec.ts
pnpm test:e2e
$env:TEST_DATABASE_URL='postgresql+psycopg://metiquo:metiquo@127.0.0.1:55436/metiquo?connect_timeout=5'
$env:RUN_OWNER_BROWSER='1'
uv run --frozen python -m pytest tests/integration/test_owner_browser.py -q
```

L'exercice Owner nécessite une base PostgreSQL de test dédiée et les ports 8000/3000 libres. Il migre la base, crée un compte de fixture par la CLI puis construit Next et vérifie les deux parcours clavier dans Chromium : mauvais mot de passe, connexion, session protégée et déconnexion. Les deux tests Owner ignorés par la suite mock ne comptent pas comme exécutés ; seul cet exercice séparé les prouve.

Axe vérifie neuf pages critiques dans les deux thèmes, à 1 440 × 960 et 390 × 844 pixels, soit 36 analyses. Les confirmations et erreurs d'entraînement en thème sombre font l'objet d'analyses supplémentaires. Les tests ne désactivent aucune règle WCAG A/AA sélectionnée. Ils contrôlent aussi le retour aux filtres par l'historique, les annonces de cote et la navigation mobile.

## Checklist clavier manuelle

La vérification ci-dessous a été effectuée dans le navigateur intégré, avec les touches et une inspection de l'arbre d'accessibilité et du rendu. Les autres chaînes complètes sont exercées par les tests clavier décrits ci-dessus. Aucun lecteur d'écran vocal externe n'a été utilisé ; la preuve des annonces porte sur les régions accessibles exposées et leurs mises à jour.

| Parcours inspecté            | Manipulation et observation                                                   | Résultat                                                                                          |
| ---------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Entrée dans le contenu       | Tab jusqu'au lien d'évitement, Entrée puis tabulations jusqu'au filtre Équipe | Lien utilisable, champ nommé et focus visible                                                     |
| Filtrage desktop sombre      | Saisie de « Aurore 02 », Entrée, inspection de la page filtrée                | Un résultat ; le focus reste dans le champ et son contour cyan est visible                        |
| Menu mobile                  | À 390 × 844, ouvrir avec Entrée, Shift+Tab, Échap                             | Focus initial sur Fermer, passage au dernier lien Paramètres, retour sur Ouvrir                   |
| Navigation vers un événement | Ouvrir le menu, choisir Événements, puis ouvrir Aurore 02 au clavier          | Menu refermé et fiche accessible                                                                  |
| Compréhension du graphe      | Inspection du titre accessible, de la description et du résumé visible        | Nombre de snapshots, première/dernière cote, minimum, maximum et variation sont exprimés en texte |
| Sens des données             | Inspection du signal, de la cote, du grade et de l'EV                         | Prix et valeurs signées accompagnent les styles ; les liens d'action possèdent un nom             |

Pour reproduire la revue complète, prolonger ces étapes avec les chaînes automatisées : création/règlement paper, revue/alias, synchronisation/entraînement, changement de thème et connexion/déconnexion Owner. Le helper refuse un contrôle inaccessible par tabulations ou masqué sous le chrome fixe.

## Corrections et preuves

Le filtre était remonté à chaque changement d'URL, ce qui perdait le focus après Entrée. Il conserve désormais son nœud ; les valeurs sont resynchronisées lors d'un effacement ou d'un retour dans l'historique. La vérification de l'effacement a également détecté un grade conservé à tort par la remise à zéro native du formulaire ; la synchronisation explicite couvre les champs et les listes de choix. Les régions de résultat et de cote ont des noms distincts et des annonces atomiques polies. Les messages d'entraînement utilisent des couleurs adaptées au thème sombre : le contrôle initial mesurait un contraste de 3,56:1 pour la confirmation, sous les 4,5:1 requis.

Les résultats, versions et empreintes des sources sont archivés dans `docs/evidence/qa-003/report.json`. La vérification concerne Chromium et les scénarios documentés ; les régions ARIA ne remplacent pas une campagne multi-lecteurs d'écran. Les états de panne réseau font l'objet du gate QA-004.
