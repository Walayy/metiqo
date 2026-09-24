# Résultats des sélections Stake

Le worker `settlement-worker` traite toutes les minutes, sans réseau, les sélections
Stake qui ont eu au moins une cote ouverte et dont le marché est exactement
« Vainqueur du match » ou « Map/Carte N Gagnant/Vainqueur ». Il n'existe pas de
table de paris placés : ces statuts décrivent les **sélections historiques**, sans
mise, paiement ou promesse de règlement par Stake.

Le lien actif `bookmaker_match_links` doit être confirmé par
`bookmaker_match_resolutions.status = linked`. Les deux sélections du marché doivent
correspondre, de manière unique, aux deux équipes de la décision de rapprochement.
Une sélection inconnue, une équipe ambiguë, un marché partiel ou tout autre type
de marché reste sans conclusion. Les noms d'équipe ne sont jamais déduits de
l'ordre des boutons ni d'une ressemblance partielle.

Le match doit avoir un format BO1/BO3/BO5 sourcé et un snapshot `finished` en base.
Le score final doit atteindre le nombre de victoires requis, et les cartes publiées
ne doivent pas le contredire. LoLTV est utilisé en premier. Oracle est utilisé
si LoLTV manque le résultat du match ou d'une carte, avec projection Oracle
complète et format vérifié ; une contradiction entre les deux sources suspend la
conclusion. Une carte explicitement absente du score final est `void` (remboursée
dans ce modèle) ; une carte attendue mais sans vainqueur publié reste `pending`.
Si une observation LoLTV non concluante est plus récente que la dernière preuve
Oracle, le secours Oracle attend une nouvelle preuve au lieu de conserver un
résultat devenu potentiellement périmé.

Faute d'heure de fin sportive fiable commune aux sources, le délai de 30 minutes
commence à la **première observation en base** du résultat final cohérent. C'est
une borne prudente : le traitement peut donc survenir plus tard que 30 minutes
après la fin réelle. Toute correction du résultat ou régression de statut relance
le délai. Le résultat courant est dans `bookmaker_selection_results` (`pending`,
`won`, `lost`, `void`) ; `bookmaker_selection_result_decisions` est un journal
immuable des changements, avec empreinte et snapshot source. Une révocation du
lien remet le résultat à `pending` sans effacer la décision précédente.

`GET /api/v1/matches` transmet le statut courant de chaque sélection Stake
rapprochée avec ses relevés pré-match et live. L’interface regroupe les deux
phases sous un seul marché et affiche gagnée, perdue ou annulée uniquement
pour les statuts conclus en base. `pending` reste en attente ; les cotes
historiques restent datées et ne constituent pas une offre actuelle.

La migration `0017` crée les tables, les droits SQL et la planification
`settle-selections` (`* * * * *`). Le service Docker dédié s'exécute avec le rôle
SQL worker. Exécution manuelle :

```powershell
uv run --frozen alembic upgrade head
uv run --frozen metiquo-worker settle-selections
```

Dans Docker, `docker compose --env-file .env.docker -f compose.yaml -f compose.api.yaml up -d --build settlement-worker` démarre le service. Il apparaît
dans « Scripts » et peut y être mis en pause ou lancé manuellement.
La table ne prend aucune décision sur les autres catégories, cuts, règlements
spéciaux ou annulations décidées par le bookmaker.
