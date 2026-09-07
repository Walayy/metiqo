# Sécurité du MVP

## Exposition et AUTH_MODE

La configuration initiale autorise `AUTH_MODE=disabled` uniquement avec
`APP_PUBLISH_HOST=127.0.0.1` et `APP_PUBLIC_ORIGIN=http://localhost:3000`.
Les autres adresses loopback IPv4/IPv6 sont acceptées. Les interfaces génériques
`0.0.0.0` et `::`, les adresses publiques, link-local et de réseau partagé, ainsi
que les noms DNS arbitraires, sont refusés sans authentification.

Une adresse privée nécessite un réseau explicitement déclaré, par exemple :

```text
AUTH_MODE=disabled
APP_PUBLISH_HOST=192.168.10.4
APP_PUBLIC_ORIGIN=http://192.168.10.4:3000
AUTH_PRIVATE_NETWORKS=["192.168.10.0/24"]
```

Les réseaux déclarés doivent être des sous-réseaux de `10.0.0.0/8`,
`172.16.0.0/12`, `192.168.0.0/16` ou `fc00::/7`. La configuration refuse une plage
globale ou réservée. L'adresse de publication et celle de l'origine navigateur
doivent toutes deux être locales ou appartenir à un réseau déclaré. Aucun test
DNS ne permet de déclarer implicitement un hostname privé. L'origine doit être
une origine HTTP/HTTPS, sans identifiants, chemin, query ni fragment.

Compose utilise `APP_PUBLISH_HOST` pour les ports API, web et gateway et transmet
cette même valeur à la validation Python. Une configuration invalide empêche le
démarrage de l'API et du worker ; les dépendances de santé empêchent le démarrage
normal du web et du gateway. Les sockets internes des conteneurs continuent
d'écouter sur leur réseau Docker ; cette adresse interne est distincte de la
publication sur l'hôte. Le gateway livré est configuré pour localhost : un
changement d'origine nécessite également sa configuration TLS correspondante.

Hors Compose, appliquer la même adresse de publication au serveur ou reverse proxy
effectivement démarré. Une redirection de ports/NAT ou un tunnel externe n'est pas
détectable par la configuration applicative ; il doit être déclaré avec l'origine
et l'adresse d'exposition correspondantes. Ne pas conserver une déclaration
loopback pour une application rendue accessible depuis un réseau public.

`AUTH_MODE=owner` est la voie prévue pour l'exposition réseau authentifiée. Au
commit SEC-001, l'API refuse encore ce mode avec `AUTH_OWNER_UNAVAILABLE` : il ne
faut pas annoncer une protection active avant le raccordement des sessions par
SEC-002. Cette restriction est volontairement fermée en cas d'absence du service.

Les tests couvrent la configuration, sa réévaluation par la fabrique API, le
refus d'un vrai démarrage du serveur API et la correspondance entre adresses publiées
et paramètres validés dans Compose.
