# Metiquo — instructions communes

Préparation du **14 septembre 2026**, sans code applicatif. Lire ce fichier puis les seuls skills utiles au travail. Consigner les nouvelles preuves dans le skill concerné, sans rapport doublonné ni système multi-agents.

## Périmètre

Application personnelle française : **rencontres → analyse → simulation → résultat**. LoL uniquement ; **`stake.bet` exclusivement pour les cotes**, Oracle’s Elixir exclusivement pour les données sportives. Aucun pari automatique, fournisseur tiers de cotes, API payante, abonnement ou gestion multi-utilisateurs.

V1 limitée au **vainqueur de la partie 1, avant la série**, pour **toutes les compétitions de League of Legends**, sans priorité ni restriction à LEC/LCK : LCS, LEC, LCK, LPL, CBLOL, LFL et toute autre ligue ou tournoi, y compris ligues régionales, académies, qualifications et rencontres internationales/interrégionales. Cette liste est illustrative, pas une liste fermée ni une preuve de couverture actuelle des sources. Exclure les autres parties. Exiger le marché explicitement identifié de la partie : ne jamais remplacer une cote de partie par « vainqueur du match », même en BO1.

Découvrir les compétitions réellement publiées par les deux sources, sans filtre géographique ou de niveau imposé. Distinguer périmètre souhaité, présence chez chaque source, capacité de suivi et qualification du modèle par compétition. Une compétition reste dans le périmètre même si ses données ou son marché manquent : signaler la limite observée sans fabriquer de données ni changer de fournisseur. Les équipes premières et leurs académies gardent des identités distinctes.

## État réel et préalable

**Aucune collecte autonome n'est validée.** Stake.bet a été consulté, mais le marché exact n'a pas été extrait. Le téléchargement et la lecture d'un CSV courant d'Oracle’s Elixir n'ont pas été réalisés. Les essais locaux ont rencontré des restrictions réseau. Aucun modèle n'a été entraîné ni évalué ici.

Compléter d'abord les validations des sources, y compris les conditions d'accès, sans construire déjà l'application. Ne pas inventer d'endpoint, sélecteur, fichier actuel ou résultat d'essai. Les méthodes de collecte ci-dessous sont **conditionnelles** ; aucune substitution silencieuse n'est admise.

Réduire les refus évitables et rechercher des accès autorisés stables ; **aucune absence permanente de 403/429/CAPTCHA/503 ne peut être garantie**. Une intervention humaine régulière ne satisfait pas l'autonomie demandée. Les blocages et leurs causes doivent rester visibles.

## Stack proposée

| Élément | Choix et besoin |
|---|---|
| Exécution | Python **3.13.15** ; un processus, modules simples. |
| Web | FastAPI **0.141.1**, Uvicorn **0.52.4**, Jinja2 **3.1.6** ; HTML serveur, CSS/JavaScript locaux, sans compilation front. |
| Données | **Une SQLite locale** via `sqlite3`, SQL explicite ; fichiers sources immuables sur disque. |
| Planification | Deux tâches bornées dans le serveur, sans service supplémentaire. |
| Stake, conditionnel | Playwright **1.62.0** et son Chromium ; un seul canal d'extraction à qualifier. |
| Oracle, conditionnel | HTTPX **0.28.1** + Beautiful Soup **4.15.0**, `html.parser`. gdown étudié, non retenu. |
| Modèle / tests | Elo en bibliothèque standard ; pytest **9.1.1** et Playwright pour le parcours. |

Versions, prérequis et réserves sont sourcés dans les skills. La combinaison n'a pas été installée/testée ici. Verrouiller les versions réellement qualifiées et leurs dépendances transitives. Aucun ORM, Redis, framework front ou outil « stealth » ajouté par anticipation.

## Invariants

Valider les données avant promotion ; conserver la dernière version valide. Distinguer dernière tentative, dernier succès, publication et date des matchs. Stocker les instants en UTC, afficher Europe/Paris avec fuseau.

Les cotes ne fabriquent jamais l'estimation indépendante. Identité ambiguë, données insuffisantes, état inconnu ou cote périmée empêchent une opportunité ; un modèle non qualifié reste expérimental. Les photographies de simulations ne changent pas rétroactivement. Une estimation n'est pas une certitude.

Préserver un parcours court, accessible et responsive, avec thèmes complets et SVG/logos contrôlés. Tester d'abord calculs, chronologie, cohérence, idempotence et parcours. Accès local par défaut, sans exposition publique non protégée.

## Instructions spécialisées

- [Collecte Stake.bet](.agents/skills/collecte-stake/SKILL.md) : preuves, marché exact, méthode et validation restante.
- [Collecte Oracle’s Elixir](.agents/skills/collecte-oracle/SKILL.md) : Drive, téléchargement, schéma et corrections.
- [Modèle et simulations](.agents/skills/modele-simulations/SKILL.md) : probabilités, qualification, comparaison et bilan.
- [Interface](.agents/skills/interface/SKILL.md) : trois vues, composants, thèmes, logos et accessibilité.
- [Implémentation et vérification](.agents/skills/implementation-verification/SKILL.md) : stockage, sécurité, politique réseau commune et recette.
