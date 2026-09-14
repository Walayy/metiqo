# ADR-0001 — Collecte des pages publiques Stake sans API

- Statut : Accepté pour le périmètre technique demandé
- Date : 2026-09-08
- Décideur : propriétaire du projet, instruction explicite dans la tâche
- Remplace : choix « aucun scraper Stake » de la SFG, pour la lecture des pages publiques
- Remplacé par : aucun

## Contexte et décision

Le propriétaire demande : « Aucun accès API il faut, c'est 100% que du scraping ».
Cette instruction remplace le choix initial d'attendre une intégration API.
La collecte utilise donc Chromium et les éléments rendus des pages
`stake.bet/fr/sports/league-of-legends`, sans clé et sans transport API Stake dédié.

La précision du propriétaire du 8 septembre demande une collecte autonome en
mode réel, sans extension, et l'étude des moteurs adaptés aux protections du site.
Patchright 1.62.3 est intégré après un essai réel réussi en mode fenêtré. Ce choix
remplace celui du seul pilote Playwright standard. Le profil appartient au
collecteur et l'affichage Linux est fourni automatiquement par Xvfb.

`ODDS_PROVIDER=auto` sélectionne `stake_public` avec `APP_DATA_MODE=real`, et active la commande et
sa planification. Le squelette historique `StakeAuthorizedProvider` et ses anciens
flags restent distincts et désactivés ; aucun de ces flags n'est déclaré confirmé.
Les contrôles de diffusion commerciale et publique du projet restent applicables.

## Périmètre et conséquences

- Découverte des compétitions et matchs, puis lecture des onglets et dépliage des marchés.
- Conservation des cotes et libellés observés, des URL sources et des heures de lecture.
- Aucun accès au store JavaScript, aucune reconstruction d'historique ou de cote manquante.
- Aucun transfert de session personnelle, aucun désarmement TLS et aucune action de mise.
- Pilotage Patchright et attente des vérifications JavaScript du site ; aucun prix
  n'est publié à partir d'un document refusé ou d'un CAPTCHA non résolu.
- Les marchés hors vocabulaire du pricing sont consultables dans la capture brute.
  Les vainqueurs du match et des cartes sont aussi projetés vers l'historique existant,
  avec un statut informatif tant que les règles et identités ne sont pas validées.
- Les refus du site entraînent un état visible et une temporisation durable.

Le fonctionnement du navigateur de consultation ne prouve pas l'accès du processus
serveur. Un HTTP 403 a effectivement été constaté dans ce dernier le 8 septembre.
Les essais ultérieurs Patchright sont documentés dans un
[rapport distinct](../stake-patchright-20260908.md), sans effacer ce constat initial.

## Validation

Le [rapport de collecte](../stake-public-scraping.md) distingue la lecture publique
réelle, le rejeu déterministe dans Chromium, les tests PostgreSQL/HTTP, le packaging
et le test réseau du processus autonome.
